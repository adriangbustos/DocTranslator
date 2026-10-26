import os
import re
from typing import Callable, Optional, List
import docx
import pptx
import openpyxl
from translator_gemini import GeminiTranslator

class OfficeTranslator:
    def __init__(self, gemini_translator: GeminiTranslator):
        self.translator = gemini_translator

    def _translate_tagged_runs(self, runs, source_lang: str, target_lang: str):
        """Translates paragraph runs while preserving bold, italic, color, and font."""
        if not runs:
            return

        # Check if only one run or identical formatting
        non_empty_runs = [r for r in runs if r.text and r.text.strip()]
        if not non_empty_runs:
            return

        if len(non_empty_runs) == 1:
            translated = self.translator.translate_batch(
                [non_empty_runs[0].text], source_lang, target_lang
            )[0]
            non_empty_runs[0].text = translated
            return

        # Multi-run paragraph: wrap in tags <r0>...</r0>
        tagged_text = ""
        for idx, r in enumerate(runs):
            if r.text:
                tagged_text += f"<r{idx}>{r.text}</r{idx}>"

        prompt = (
            f"Translate from {source_lang} to {target_lang}. "
            f"Crucial: preserve all <rX>...</rX> XML tags exactly where they belong in the translated sentence so run-level styles are maintained:\n"
            f"{tagged_text}"
        )
        
        translated_tagged = self.translator._call_api(prompt).strip()

        # Extract tags
        pattern = re.compile(r"<r(\d+)>(.*?)</r\1>", re.DOTALL)
        matches = pattern.findall(translated_tagged)

        if matches:
            tag_map = {int(idx): txt for idx, txt in matches}
            for idx, r in enumerate(runs):
                if idx in tag_map:
                    r.text = tag_map[idx]
                else:
                    r.text = ""
        else:
            # Fallback if model dropped tags: put full text in first non-empty run
            raw_clean = re.sub(r"</?r\d+>", "", translated_tagged)
            non_empty_runs[0].text = raw_clean
            for r in non_empty_runs[1:]:
                r.text = ""

    def translate_docx(
        self,
        input_path: str,
        output_path: str,
        source_lang: str,
        target_lang: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> str:
        doc = docx.Document(input_path)
        all_paragraphs = list(doc.paragraphs)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    all_paragraphs.extend(cell.paragraphs)

        total_paras = len(all_paragraphs)
        for idx, p in enumerate(all_paragraphs):
            if cancel_check and cancel_check():
                raise InterruptedError("Operation cancelled by user.")
            if progress_callback and total_paras > 0:
                progress_callback(
                    idx / total_paras,
                    f"Word Doc: Translating paragraph {idx+1}/{total_paras}..."
                )
            self._translate_tagged_runs(p.runs, source_lang, target_lang)

        doc.save(output_path)
        if progress_callback:
            progress_callback(1.0, "Word document translation complete!")
        return output_path

    def translate_pptx(
        self,
        input_path: str,
        output_path: str,
        source_lang: str,
        target_lang: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> str:
        prs = pptx.Presentation(input_path)
        total_slides = len(prs.slides)

        for s_idx, slide in enumerate(prs.slides):
            if cancel_check and cancel_check():
                raise InterruptedError("Operation cancelled by user.")
            if progress_callback:
                progress_callback(
                    s_idx / max(1, total_slides),
                    f"PowerPoint: Translating slide {s_idx+1}/{total_slides}..."
                )

            for shape in slide.shapes:
                if shape.has_text_frame:
                    for p in shape.text_frame.paragraphs:
                        self._translate_tagged_runs(p.runs, source_lang, target_lang)

                if shape.has_table:
                    for row in shape.table.rows:
                        for cell in row.cells:
                            for p in cell.text_frame.paragraphs:
                                self._translate_tagged_runs(p.runs, source_lang, target_lang)

        prs.save(output_path)
        if progress_callback:
            progress_callback(1.0, "PowerPoint translation complete!")
        return output_path

    def translate_xlsx(
        self,
        input_path: str,
        output_path: str,
        source_lang: str,
        target_lang: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> str:
        wb = openpyxl.load_workbook(input_path)
        sheets = wb.sheetnames

        for s_idx, name in enumerate(sheets):
            if cancel_check and cancel_check():
                raise InterruptedError("Operation cancelled by user.")
            ws = wb[name]
            if progress_callback:
                progress_callback(
                    s_idx / len(sheets),
                    f"Excel: Translating sheet '{name}'..."
                )

            text_cells = []
            for row in ws.iter_rows():
                for cell in row:
                    val = cell.value
                    if isinstance(val, str) and val.strip() and not val.startswith("="):
                        text_cells.append(cell)

            if text_cells:
                texts = [c.value for c in text_cells]
                # Batch in groups of 30 to avoid prompt size limits
                batch_size = 30
                for b_start in range(0, len(texts), batch_size):
                    if cancel_check and cancel_check():
                        raise InterruptedError("Operation cancelled by user.")
                    batch_texts = texts[b_start : b_start + batch_size]
                    translated = self.translator.translate_batch(batch_texts, source_lang, target_lang)
                    for c, trans in zip(text_cells[b_start : b_start + batch_size], translated):
                        c.value = trans

        wb.save(output_path)
        if progress_callback:
            progress_callback(1.0, "Excel translation complete!")
        return output_path
