import os
import re
from typing import Callable, Optional, List, Dict, Any, Tuple
import pymupdf as fitz
from translator_gemini import GeminiTranslator


class PDFTranslator:
    def __init__(self, translator: GeminiTranslator):
        self.translator = translator
        windir = os.environ.get("WINDIR", r"C:\Windows")
        self.font_paths = {
            "regular": os.path.join(windir, "Fonts", "arial.ttf"),
            "bold": os.path.join(windir, "Fonts", "arialbd.ttf"),
            "italic": os.path.join(windir, "Fonts", "ariali.ttf"),
            "bold_italic": os.path.join(windir, "Fonts", "arialbi.ttf")
        }
        self.registered_fonts = {}
        for style, path in self.font_paths.items():
            if os.path.exists(path):
                self.registered_fonts[style] = path

    def _get_font_file_and_name(self, is_bold: bool, is_italic: bool) -> Tuple[Optional[str], str]:
        if is_bold and is_italic and "bold_italic" in self.registered_fonts:
            return self.registered_fonts["bold_italic"], "Arial-BoldItalic"
        elif is_bold and "bold" in self.registered_fonts:
            return self.registered_fonts["bold"], "Arial-Bold"
        elif is_italic and "italic" in self.registered_fonts:
            return self.registered_fonts["italic"], "Arial-Italic"
        elif "regular" in self.registered_fonts:
            return self.registered_fonts["regular"], "Arial"
        return None, "helv"

    def _is_translatable(self, text: str) -> bool:
        clean = text.replace('\u200b', '').strip()
        if not clean or len(clean) <= 1:
            return False
        # Do not translate standalone numbers, scores, pure dates, pure codes
        if re.fullmatch(r'[\d\s.,/:;+\-*–—()%=#$€£&|\\\[\]]+', clean):
            return False
        if re.match(r'^(https?://|www\.)', clean, re.I):
            return False
        if '@' in clean and '.' in clean:
            return False
        # If contains letters
        if any(c.isalpha() for c in clean):
            return True
        return False

    def _get_vertical_divider_lines(self, page: fitz.Page) -> List[Dict[str, float]]:
        """Extracts vertical divider lines with exact Y coordinates to prevent cross-column bleed."""
        v_lines = []
        for d in page.get_drawings():
            r = fitz.Rect(d["rect"])
            if r.width <= 3.5 and r.height >= 15.0:
                v_lines.append({"x": round(r.x0, 1), "y0": r.y0, "y1": r.y1})
        return v_lines

    def _extract_page_units(self, page: fitz.Page) -> List[Dict[str, Any]]:
        page_dict = page.get_text("dict")
        page_w = page.rect.width
        page_h = page.rect.height
        units: List[Dict[str, Any]] = []

        for b in page_dict.get("blocks", []):
            if b.get("type") != 0:
                continue

            lines = b.get("lines", [])
            if not lines:
                continue

            sorted_lines = sorted(lines, key=lambda l: (round(l["bbox"][1] / 3) * 3, l["bbox"][0]))

            # Group lines into horizontal rows by vertical midpoint
            rows = []
            for l in sorted_lines:
                # Filter out 1pt / tiny screen-reader ghost spans
                valid_spans = [s for s in l.get("spans", []) if s.get("size", 10.0) >= 3.5 and s.get("text", "").strip()]
                if not valid_spans:
                    continue
                y_mid = (l["bbox"][1] + l["bbox"][3]) / 2.0
                placed = False
                for r in rows:
                    r_y_mid = (r[0]["bbox"][1] + r[0]["bbox"][3]) / 2.0
                    if abs(y_mid - r_y_mid) <= 4.0:
                        r.append(l)
                        placed = True
                        break
                if not placed:
                    rows.append([l])

            idx = 0
            while idx < len(rows):
                r = rows[idx]
                if len(r) > 1:
                    # Multi-column table row: preserve each cell independently
                    row_sorted = sorted(r, key=lambda x: x["bbox"][0])
                    for cell_idx, l in enumerate(row_sorted):
                        spans = [s for s in l.get("spans", []) if s.get("text", "").strip() and s.get("size", 10.0) >= 3.5]
                        if not spans:
                            continue

                        # Check if spans have mixed styling
                        has_mixed = any(
                            ((s.get("flags", 0) & 16 != 0) != (spans[0].get("flags", 0) & 16 != 0)) or
                            (s.get("color", 0) != spans[0].get("color", 0))
                            for s in spans
                        )
                        if has_mixed:
                            for s in spans:
                                t = s.get("text", "").replace('\u200b', '').strip()
                                if not t:
                                    continue
                                is_b = (s.get("flags", 0) & 16 != 0) or ("bold" in s.get("font", "").lower())
                                is_it = (s.get("flags", 0) & 2 != 0) or ("italic" in s.get("font", "").lower())
                                c_int = s.get("color", 0)
                                units.append({
                                    "rect": fitz.Rect(s["bbox"]),
                                    "origin": fitz.Point(s["origin"]),
                                    "text": t,
                                    "fontsize": s.get("size", 10.0),
                                    "is_bold": is_b,
                                    "is_italic": is_it,
                                    "color": (((c_int >> 16) & 255) / 255.0, ((c_int >> 8) & 255) / 255.0, (c_int & 255) / 255.0),
                                    "align": 0,
                                    "translatable": self._is_translatable(t),
                                    "row_id": f"row_{idx}_{cell_idx}"
                                })
                        else:
                            full_t = "".join(s.get("text", "") for s in spans).replace('\u200b', '').strip()
                            if full_t:
                                s0 = spans[0]
                                is_b = (s0.get("flags", 0) & 16 != 0) or ("bold" in s0.get("font", "").lower())
                                is_it = (s0.get("flags", 0) & 2 != 0) or ("italic" in s0.get("font", "").lower())
                                c_int = s0.get("color", 0)
                                units.append({
                                    "rect": fitz.Rect(l["bbox"]),
                                    "origin": fitz.Point(s0["origin"]),
                                    "text": full_t,
                                    "fontsize": s0.get("size", 10.0),
                                    "is_bold": is_b,
                                    "is_italic": is_it,
                                    "color": (((c_int >> 16) & 255) / 255.0, ((c_int >> 8) & 255) / 255.0, (c_int & 255) / 255.0),
                                    "align": 0,
                                    "translatable": self._is_translatable(full_t),
                                    "row_id": f"row_{idx}_{cell_idx}"
                                })
                    idx += 1
                else:
                    # Single line row
                    l = r[0]
                    spans = [s for s in l.get("spans", []) if s.get("text", "").strip() and s.get("size", 10.0) >= 3.5]
                    if not spans:
                        idx += 1
                        continue

                    full_t = "".join(s.get("text", "") for s in spans).replace('\u200b', '').strip()
                    s0 = spans[0]
                    is_b = (s0.get("flags", 0) & 16 != 0) or ("bold" in s0.get("font", "").lower())
                    is_it = (s0.get("flags", 0) & 2 != 0) or ("italic" in s0.get("font", "").lower())
                    c_int = s0.get("color", 0)
                    l_rect = fitz.Rect(l["bbox"])

                    # Check for mixed styling within single line
                    has_mixed = any(
                        ((s.get("flags", 0) & 16 != 0) != is_b) or
                        (s.get("color", 0) != c_int)
                        for s in spans
                    )

                    if has_mixed:
                        for s_i, s in enumerate(spans):
                            t = s.get("text", "").replace('\u200b', '').strip()
                            if t:
                                is_sb = (s.get("flags", 0) & 16 != 0) or ("bold" in s.get("font", "").lower())
                                is_sit = (s.get("flags", 0) & 2 != 0) or ("italic" in s.get("font", "").lower())
                                sc_int = s.get("color", 0)
                                units.append({
                                    "rect": fitz.Rect(s["bbox"]),
                                    "origin": fitz.Point(s["origin"]),
                                    "text": t,
                                    "fontsize": s.get("size", 10.0),
                                    "is_bold": is_sb,
                                    "is_italic": is_sit,
                                    "color": (((sc_int >> 16) & 255) / 255.0, ((sc_int >> 8) & 255) / 255.0, (sc_int & 255) / 255.0),
                                    "align": 0,
                                    "translatable": self._is_translatable(t),
                                    "line_seq": (idx, s_i, len(spans))
                                })
                        idx += 1
                    else:
                        is_bullet = full_t.startswith(("-", "•", "*", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."))
                        rect = l_rect
                        text = full_t

                        # Multi-line continuation: only if next line is NOT a new bullet and has identical styling
                        next_idx = idx + 1
                        while next_idx < len(rows) and len(rows[next_idx]) == 1:
                            nl = rows[next_idx][0]
                            nspans = [s for s in nl.get("spans", []) if s.get("text", "").strip() and s.get("size", 10.0) >= 3.5]
                            if not nspans:
                                next_idx += 1
                                continue
                            ntxt = "".join(s.get("text", "") for s in nspans).replace('\u200b', '').strip()
                            n_is_bullet = ntxt.startswith(("-", "•", "*", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."))
                            if n_is_bullet:
                                break  # NEVER merge separate bullets!

                            gap = nl["bbox"][1] - rect.y1
                            ns0 = nspans[0]
                            n_is_b = (ns0.get("flags", 0) & 16 != 0) or ("bold" in ns0.get("font", "").lower())
                            if -2.0 <= gap <= s0.get("size", 10.0) * 1.8 and n_is_b == is_b and ns0.get("color", 0) == c_int:
                                rect = fitz.Rect(min(rect.x0, nl["bbox"][0]), rect.y0, max(rect.x1, nl["bbox"][2]), nl["bbox"][3])
                                text += " " + ntxt
                                next_idx += 1
                            else:
                                break

                        center_x = (rect.x0 + rect.x1) / 2.0
                        is_centered = (rect.x0 > 80.0) and (page_w - rect.x1 > 80.0) and (abs(center_x - page_w / 2.0) < 25.0)

                        units.append({
                            "rect": rect,
                            "origin": fitz.Point(s0["origin"]),
                            "text": text,
                            "fontsize": s0.get("size", 10.0),
                            "is_bold": is_b,
                            "is_italic": is_it,
                            "color": (((c_int >> 16) & 255) / 255.0, ((c_int >> 8) & 255) / 255.0, (c_int & 255) / 255.0),
                            "align": 1 if is_centered else 0,
                            "translatable": self._is_translatable(text)
                        })
                        idx = next_idx

        return units

    def translate_pdf(
        self,
        input_pdf_path: str,
        output_pdf_path: str,
        source_lang: str,
        target_lang: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> str:
        doc = fitz.open(input_pdf_path)
        total_pages = len(doc)

        if progress_callback:
            progress_callback(0.0, f"Opened PDF with {total_pages} page(s)...")

        for page_idx in range(total_pages):
            if cancel_check and cancel_check():
                doc.close()
                raise InterruptedError("Operation cancelled by user.")

            page = doc[page_idx]
            page_num = page_idx + 1

            if progress_callback:
                progress_callback(
                    (page_idx / total_pages),
                    f"Page {page_num}/{total_pages}: Extracting layout and styles..."
                )

            all_page_units = self._extract_page_units(page)
            translatable_units = [u for u in all_page_units if u["translatable"]]

            if not translatable_units:
                continue

            if cancel_check and cancel_check():
                doc.close()
                raise InterruptedError("Operation cancelled by user.")

            if progress_callback:
                progress_callback(
                    ((page_idx + 0.3) / total_pages),
                    f"Page {page_num}/{total_pages}: Translating {len(translatable_units)} item(s) with Gemini..."
                )

            texts_to_translate = [u["text"] for u in translatable_units]
            translated_texts = self.translator.translate_batch(
                texts_to_translate, source_lang, target_lang
            )

            if cancel_check and cancel_check():
                doc.close()
                raise InterruptedError("Operation cancelled by user.")

            if progress_callback:
                progress_callback(
                    ((page_idx + 0.7) / total_pages),
                    f"Page {page_num}/{total_pages}: Rendering translated text with preserved styles..."
                )

            # Detect vertical graphic lines as hard barriers (e.g. SAT divider at x=162.3)
            vertical_lines = self._get_vertical_divider_lines(page)

            # 1. Redact ONLY translatable text bounding boxes, stopping clean before untranslated values
            for u in translatable_units:
                redact_rect = fitz.Rect(u["rect"])
                # Ensure redaction never clips stationary numbers/values on the same row
                for other in all_page_units:
                    if not other["translatable"]:
                        o_rect = other["rect"]
                        if max(redact_rect.y0, o_rect.y0) < min(redact_rect.y1, o_rect.y1) - 1.0:
                            if o_rect.x0 > redact_rect.x0 and o_rect.x0 < redact_rect.x1 + 4.0:
                                redact_rect.x1 = min(redact_rect.x1, o_rect.x0 - 2.0)
                page.add_redact_annot(redact_rect, fill=None)

            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

            # Track rendered rightmost bounds for sequential spans on the same line
            line_offsets: Dict[int, float] = {}

            # 2. Insert translated text with exact font variant and obstacle-aware bounding
            page_w = page.rect.width
            page_h = page.rect.height

            for u, trans_text in zip(translatable_units, translated_texts):
                rect = u["rect"]
                orig_text = u["text"]
                base_fontsize = u["fontsize"]
                color = u["color"]
                align = u.get("align", 0)
                is_bold = u.get("is_bold", False)
                is_italic = u.get("is_italic", False)

                fontfile, fontname = self._get_font_file_and_name(is_bold, is_italic)

                start_x0 = rect.x0
                line_seq = u.get("line_seq")
                if line_seq:
                    row_idx, s_idx, total_s = line_seq
                    if s_idx > 0 and row_idx in line_offsets:
                        start_x0 = max(start_x0, line_offsets[row_idx] + 3.0)

                # Obstacle-Aware Expansion: text obstacles + vertical line obstacles
                right_barriers = []
                # (a) Check text obstacles (both translatable and untranslatable)
                for other in all_page_units:
                    if other is u:
                        continue
                    o_rect = other["rect"]
                    if max(rect.y0, o_rect.y0) < min(rect.y1, o_rect.y1) - 1.0:
                        if o_rect.x0 >= start_x0 + 4.0:
                            right_barriers.append(o_rect.x0)

                # (b) Check vertical graphic divider lines with Y-overlap
                for vl in vertical_lines:
                    if vl["x"] > start_x0 + 5.0 and vl["x"] < page_w - 20.0:
                        if max(rect.y0, vl["y0"]) < min(rect.y1, vl["y1"]) + 3.0:
                            right_barriers.append(vl["x"])

                if align == 0:
                    if right_barriers:
                        nearest_barrier = min(right_barriers)
                        max_x1 = max(rect.x1, nearest_barrier - 3.5)
                    else:
                        max_x1 = max(rect.x1, min(page_w - 36.0, start_x0 + 520.0))
                else:
                    max_x1 = rect.x1

                # Exact Baseline Calculation: Derive top_y from origin.y and font ascender
                # This guarantees 0.0pt vertical baseline shift and 0.0pt horizontal shift
                font = fitz.Font(fontfile=fontfile) if fontfile else fitz.Font(fontname="helv")
                ascender = font.ascender
                descender = font.descender
                origin_y = u["origin"].y

                # Normalize colon spacing (e.g. 'Accountant ID:NOT' -> 'Accountant ID: NOT')
                clean_text = re.sub(r'(:)([A-Za-z0-9])', r'\1 \2', trans_text)

                # Scaling loop with width AND height fitting: prioritize exact base_fontsize
                curr_size = base_fontsize
                min_fontsize = max(5.0, base_fontsize * 0.70)

                success = False
                while curr_size >= min_fontsize:
                    # Mathematically align textbox top edge to font ascender so baseline matches origin_y with 0.0pt shift
                    top_y = origin_y - ascender * curr_size
                    # Allow sufficient downward room for descent or multi-line wrap without artificial top shift
                    bottom_y = min(page_h, max(rect.y1 + 4.0, origin_y - descender * curr_size + 4.0))

                    box_x0 = rect.x0 if align == 1 else start_x0
                    box_x1 = rect.x1 if align == 1 else max(start_x0 + 10.0, max_x1)

                    exp_rect = fitz.Rect(box_x0, top_y, box_x1, bottom_y)

                    kwargs = {
                        "fontsize": curr_size,
                        "color": color,
                        "align": align
                    }
                    if fontfile:
                        kwargs["fontfile"] = fontfile
                        kwargs["fontname"] = fontname
                    else:
                        kwargs["fontname"] = "helv"

                    res = page.insert_textbox(exp_rect, clean_text, **kwargs)
                    if res >= 0:
                        success = True
                        break
                    curr_size -= 0.5

                if not success:
                    # If still didn't fit, scale down to 4.5pt
                    while curr_size >= 4.5:
                        top_y = origin_y - ascender * curr_size
                        bottom_y = min(page_h, max(rect.y1 + 4.0, origin_y - descender * curr_size + 4.0))
                        box_x0 = rect.x0 if align == 1 else start_x0
                        box_x1 = rect.x1 if align == 1 else max(start_x0 + 10.0, max_x1)
                        exp_rect = fitz.Rect(box_x0, top_y, box_x1, bottom_y)

                        kwargs = {
                            "fontsize": curr_size,
                            "color": color,
                            "align": align
                        }
                        if fontfile:
                            kwargs["fontfile"] = fontfile
                            kwargs["fontname"] = fontname
                        else:
                            kwargs["fontname"] = "helv"

                        res = page.insert_textbox(exp_rect, clean_text, **kwargs)
                        if res >= 0:
                            success = True
                            break
                        curr_size -= 0.5

                if not success:
                    # Fallback single line insert at exact original baseline
                    kwargs = {
                        "fontsize": max(4.5, curr_size),
                        "color": color
                    }
                    if fontfile:
                        kwargs["fontfile"] = fontfile
                        kwargs["fontname"] = fontname
                    else:
                        kwargs["fontname"] = "helv"
                    page.insert_text(fitz.Point(start_x0, origin_y), clean_text, **kwargs)

                # Record rightward extent for sequential spans
                if line_seq:
                    row_idx, s_idx, total_s = line_seq
                    try:
                        measured_w = fitz.Font(fontfile=fontfile).text_length(trans_text, fontsize=curr_size) if fontfile else len(trans_text) * (curr_size * 0.55)
                        line_offsets[row_idx] = start_x0 + measured_w
                    except Exception:
                        line_offsets[row_idx] = exp_rect.x1

        if cancel_check and cancel_check():
            doc.close()
            raise InterruptedError("Operation cancelled by user.")

        if progress_callback:
            progress_callback(0.95, "Saving translated PDF...")

        doc.save(output_pdf_path, garbage=4, deflate=True)
        doc.close()

        if progress_callback:
            progress_callback(1.0, "Translation finished successfully!")

        return output_pdf_path
