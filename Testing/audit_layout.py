import os
import sys
from pathlib import Path
import pymupdf as fitz

# Ensure utf-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).parent.parent
ORIG_DIR = ROOT_DIR / "Testing" / "Original Documents"
TRANS_DIR = ROOT_DIR / "Testing" / "Translated Documents"
AUDIT_DIR = ROOT_DIR / "Testing" / "Audit Results"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

def audit_document(fname: str) -> dict:
    stem = Path(fname).stem
    orig_path = ORIG_DIR / fname
    trans_path = TRANS_DIR / f"{stem}_traducido.pdf"

    result = {
        "file": fname,
        "exists": False,
        "page_match": False,
        "orig_pages": 0,
        "trans_pages": 0,
        "translator_induced_jumps": [],
        "overflow_issues": [],
        "text_extracted": False
    }

    if not trans_path.exists():
        return result

    result["exists"] = True
    orig_doc = fitz.open(orig_path)
    trans_doc = fitz.open(trans_path)

    result["orig_pages"] = len(orig_doc)
    result["trans_pages"] = len(trans_doc)
    result["page_match"] = (len(orig_doc) == len(trans_doc))

    has_text = False
    for p_idx in range(len(trans_doc)):
        p_orig = orig_doc[p_idx]
        p_trans = trans_doc[p_idx]
        text = p_trans.get_text().strip()
        if text:
            has_text = True

        p_width = p_trans.rect.width
        p_height = p_trans.rect.height

        # Compare block font behavior between original and translated
        orig_dict = p_orig.get_text("dict")
        trans_dict = p_trans.get_text("dict")

        orig_blocks = [b for b in orig_dict.get("blocks", []) if b.get("type") == 0]
        trans_blocks = [b for b in trans_dict.get("blocks", []) if b.get("type") == 0]

        # Check for translator-induced font shrinking within paragraphs that were originally uniform
        for tb in trans_blocks:
            t_lines = tb.get("lines", [])
            if len(t_lines) > 1:
                t_sizes = []
                for l in t_lines:
                    spans = [s for s in l.get("spans", []) if s.get("text", "").strip()]
                    if spans:
                        t_sizes.append(sum(s.get("size", 10.0) for s in spans) / len(spans))

                if len(t_sizes) > 1:
                    t_diff = max(t_sizes) - min(t_sizes)
                    if t_diff > 1.8:  # Noticeable jump
                        t_rect = fitz.Rect(tb["bbox"])
                        orig_matching = [ob for ob in orig_blocks if fitz.Rect(ob["bbox"]).intersects(t_rect)]
                        orig_was_uniform = False
                        for ob in orig_matching:
                            o_lines = ob.get("lines", [])
                            o_sizes = []
                            for ol in o_lines:
                                ospans = [s for s in ol.get("spans", []) if s.get("text", "").strip()]
                                if ospans:
                                    o_sizes.append(sum(s.get("size", 10.0) for s in ospans) / len(ospans))
                            if len(o_sizes) > 1 and (max(o_sizes) - min(o_sizes)) < 0.5:
                                orig_was_uniform = True
                                break

                        if orig_was_uniform:
                            t_text = " ".join("".join(s.get("text", "") for s in l.get("spans", [])) for l in t_lines)
                            result["translator_induced_jumps"].append({
                                "page": p_idx + 1,
                                "sizes": [round(s, 1) for s in t_sizes],
                                "diff": round(t_diff, 1),
                                "snippet": t_text[:50]
                            })

            # Check bounding box overflow outside printable bounds
            bbox = tb.get("bbox", (0, 0, 0, 0))
            if bbox[0] < -2.0 or bbox[2] > p_width + 5.0 or bbox[1] < -2.0 or bbox[3] > p_height + 5.0:
                result["overflow_issues"].append({
                    "page": p_idx + 1,
                    "bbox": [round(x, 1) for x in bbox]
                })

        # Generate side-by-side comparison thumbnail for Page 1
        if p_idx == 0:
            try:
                pix_orig = p_orig.get_pixmap(dpi=120)
                pix_trans = p_trans.get_pixmap(dpi=120)

                w_orig, h_orig = pix_orig.width, pix_orig.height
                w_trans, h_trans = pix_trans.width, pix_trans.height
                total_w = w_orig + w_trans + 20
                total_h = max(h_orig, h_trans)

                comp_doc = fitz.open()
                comp_page = comp_doc.new_page(width=total_w, height=total_h)

                rect_orig = fitz.Rect(0, 0, w_orig, h_orig)
                rect_trans = fitz.Rect(w_orig + 20, 0, w_orig + 20 + w_trans, h_trans)

                comp_page.insert_image(rect_orig, pixmap=pix_orig)
                comp_page.insert_image(rect_trans, pixmap=pix_trans)

                out_thumb = AUDIT_DIR / f"{stem}_comparison.png"
                pix_comp = comp_page.get_pixmap()
                pix_comp.save(str(out_thumb))
                comp_doc.close()
            except Exception:
                pass

    result["text_extracted"] = has_text
    orig_doc.close()
    trans_doc.close()
    return result

def main():
    print("=" * 70)
    print("       LAYOUT, FONT-SIZE & FORMAT INCONGRUITY AUDIT")
    print("=" * 70)

    files = sorted([f for f in os.listdir(ORIG_DIR) if f.endswith(".pdf")])
    if not files:
        print("[ERROR] No files found in Original Documents.")
        return

    all_passed = True

    for fname in files:
        res = audit_document(fname)
        print(f"\nDocument: {fname}")

        if not res["exists"]:
            print("  Status: [FAILED - File not translated yet]")
            all_passed = False
            continue

        # Page Count Check
        if res["page_match"]:
            print(f"  Pages:  [PASS] {res['trans_pages']} page(s) (matches original)")
        else:
            print(f"  Pages:  [FLAG] Mismatch! Orig={res['orig_pages']}, Trans={res['trans_pages']}")
            all_passed = False

        # Text Extraction Check
        if res["text_extracted"]:
            print("  Text:   [PASS] Content successfully extracted and rendered")
        else:
            print("  Text:   [FLAG] No text detected in translated output!")
            all_passed = False

        # Translator-induced font size jumps
        if not res["translator_induced_jumps"]:
            print("  Fonts:  [PASS] Zero translator-induced font jumps (uniform line-composition preserved)")
        else:
            print(f"  Fonts:  [FLAG] Found {len(res['translator_induced_jumps'])} unintended font size jumps:")
            for inc in res["translator_induced_jumps"][:3]:
                print(f"          - Page {inc['page']}: line sizes={inc['sizes']} (diff={inc['diff']}pt) in {repr(inc['snippet'])}")
            all_passed = False

        # Text overflow outside page bounds
        if not res["overflow_issues"]:
            print("  Bounds: [PASS] All text boxes remain strictly within page bounds")
        else:
            print(f"  Bounds: [FLAG] Text overflow detected on {len(res['overflow_issues'])} block(s)")
            all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print(f"AUDIT RESULT: ALL {len(files)} DOCUMENTS PASSED WITH ZERO INCONGRUITIES!")
    else:
        print("AUDIT RESULT: REVIEW FLAGGED ITEMS ABOVE")
    print(f"Side-by-side comparison renders saved to: {AUDIT_DIR}")
    print("=" * 70)

if __name__ == "__main__":
    main()
