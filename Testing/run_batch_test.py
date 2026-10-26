import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure utf-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from translator_gemini import GeminiTranslator
from pdf_engine import PDFTranslator

load_dotenv(ROOT_DIR / ".env")
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    print("[ERROR] GEMINI_API_KEY not found in .env!")
    sys.exit(1)

ORIG_DIR = ROOT_DIR / "Testing" / "Original Documents"
TRANS_DIR = ROOT_DIR / "Testing" / "Translated Documents"
TRANS_DIR.mkdir(parents=True, exist_ok=True)

# Document language mapping
DOC_CONFIGS = {
    "Graduation Certificate.pdf": {"source": "English", "target": "Spanish"},
    "High School Diploma.pdf":    {"source": "English", "target": "Spanish"},
    "Medicine .pdf":              {"source": "Vietnamese", "target": "Spanish"},
    "Medicine 2.pdf":             {"source": "Vietnamese", "target": "Spanish"},
    "Medicine 3.pdf":             {"source": "Vietnamese", "target": "Spanish"},
    "SAT.pdf":                     {"source": "English", "target": "Spanish"},
    "TOEFL.pdf":                   {"source": "English", "target": "Spanish"},
    "CAR2026236754202610040920.pdf": {"source": "Spanish", "target": "English"},
    "Declaracion_872999519851 2025.pdf": {"source": "Spanish", "target": "English"},
}

def main():
    print("=" * 65)
    print("      MULTI-DOCUMENT BATCH TRANSLATOR (ADAPTIVE GEOMETRY)")
    print("=" * 65)

    gt = GeminiTranslator(API_KEY, model_name="gemini-3.5-flash-lite", min_interval=1.5)
    pt = PDFTranslator(gt)

    files = sorted([f for f in os.listdir(ORIG_DIR) if f.endswith(".pdf")])
    total = len(files)
    print(f"Found {total} PDF documents to process in: {ORIG_DIR}\n")

    for idx, fname in enumerate(files, 1):
        in_path = ORIG_DIR / fname
        stem = Path(fname).stem
        out_path = TRANS_DIR / f"{stem}_traducido.pdf"

        cfg = DOC_CONFIGS.get(fname, {"source": "Auto Detect", "target": "Spanish"})
        src_lang = cfg["source"]
        tgt_lang = cfg["target"]

        print(f"[{idx}/{total}] Processing: {fname}")
        print(f"       Language: {src_lang} -> {tgt_lang}")

        def progress(ratio, msg):
            pct = int(ratio * 100)
            print(f"       [{pct:3d}%] {msg}")

        try:
            pt.translate_pdf(
                str(in_path),
                str(out_path),
                source_lang=src_lang,
                target_lang=tgt_lang,
                progress_callback=progress
            )
            print(f"       [DONE] Output saved: {out_path.name}\n")
        except Exception as e:
            print(f"       [ERROR] Failed to translate {fname}: {e}\n")

    print("=" * 65)
    print("Batch processing completed!")
    print(f"Translated documents directory: {TRANS_DIR}")
    print("=" * 65)

if __name__ == "__main__":
    main()
