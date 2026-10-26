# Document Translator — Universal Layout-Preserving AI Translator

A high-fidelity, desktop document translation suite powered by **Google Gemini Flash** (`gemini-2.5-flash` / `gemini-3.5-flash-lite`). Engineered for complex forms, official certificates, academic transcripts, tax tables, and office documents with exact typographic baseline preservation, obstacle-aware bounding boxes, and zero layout drift.

![Platform](https://img.shields.io/badge/Platform-Windows-0078D6)
![Python](https://img.shields.io/badge/Python-3.10+-007ACC)
![License](https://img.shields.io/badge/License-MIT-74C400)

---

## Key Features

- **Exact Baseline Typographic Preservation:**
  - Derives exact text baseline coordinates (`origin.y`) from font ascender metrics, eliminating the vertical and horizontal drift common in PDF text replacement tools.
  - Automatically loads system TrueType fonts (Arial, Times New Roman) with full Unicode and diacritic coverage (English, Spanish, Vietnamese, etc.).
- **Obstacle-Aware Geometric Layout:**
  - Scans nearby text blocks and vector graphic dividing lines dynamically.
  - Automatically constrains bounding boxes to prevent overlapping table barriers, adjacent numeric columns, or stationary labels.
  - Supports sequential line spans (`line_seq`) so labels and values follow contiguously without collisions.
- **Multi-Format Document Support:**
  - **PDF (`.pdf`):** In-place vector redaction and sub-pixel text replacement via PyMuPDF. Preserves background artwork, seals, signatures, diagrams, and vector lines.
  - **Word (`.docx`):** Preserves XML runs, paragraph alignments, headings, and table cell formatting.
  - **PowerPoint (`.pptx`):** Traverses slides, shapes, tables, and notes preserving layout cards.
  - **Excel (`.xlsx`):** Preserves spreadsheet cells, formulas, headers, and sheet structures.
- **Batch Translation Queue & Desktop GUI:**
  - Modern dark-themed UI built with CustomTkinter.
  - Sequential processing queue with per-document and per-page progress indicators.
  - Local API key persistence in `.env`.
- **Standalone Windows Executable Support:**
  - Bundled standalone launcher script (`run.bat`) that self-bootstraps an isolated virtual environment.
  - Ready for compilation to a native `.exe` with customized multi-resolution desktop icon.

---

## Tech Stack & Prerequisites

- **Python 3.10+** (tested on Python 3.11 / Windows 10 & 11)
- **PyMuPDF (`fitz`)**: High-performance vector PDF rendering and redaction.
- **Google GenAI SDK (`google-genai`)**: Next-generation Gemini Flash API integration.
- **CustomTkinter**: Modern desktop GUI framework.
- **python-docx**, **python-pptx**, **openpyxl**: Office document processing engines.
- **Pillow**: Icon generation and layout audit imaging.

---

## Quick Start & Installation

### Option A: Automatic Setup (Windows)
Simply run the included batch launcher:
```bat
run.bat
```
`run.bat` automatically checks for Python, provisions an isolated virtual environment (`.venv`), installs all requirements, and boots the GUI.

### Option B: Manual Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/adriangbustos/DocTranslator.git
   cd DocTranslator
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your Gemini API Key:**
   Copy `.env.example` to `.env` and insert your API key:
   ```env
   GEMINI_API_KEY=AIzaSy...
   ```
   *(Alternatively, you can enter and save your key directly inside the desktop GUI).*

5. **Launch the application:**
   ```bash
   python gui.py
   ```

---

## Project Structure

```
DocTranslator/
├── gui.py                  # CustomTkinter Desktop GUI & batch queue manager
├── pdf_engine.py           # Typographic vector layout & baseline PDF engine
├── office_engine.py        # Word (.docx), PowerPoint (.pptx), Excel (.xlsx) engine
├── translator_gemini.py    # Google Gemini Flash client with rate-limiting & prompts
├── requirements.txt        # Production Python dependencies
├── run.bat                 # One-click Windows virtual environment bootstrapper
├── app_icon.ico            # Multi-resolution application icon
├── .env.example            # Environment configuration template
├── .gitignore              # Strict leak prevention and build ignore rules
└── Testing/
    ├── audit_layout.py     # Side-by-side visual difference & metric auditor
    └── run_batch_test.py   # Multi-document automated test suite
```

---

## Batch Testing & Layout Auditor

To run automated layout verification tests on multiple sample files:
```bash
python Testing/run_batch_test.py
```
To generate side-by-side visual layout audits:
```bash
python Testing/audit_layout.py
```

---

## Security & Data Privacy

- **Zero Document Telemetry:** Documents are processed strictly in local memory and through direct, encrypted TLS calls to your configured Google Gemini API endpoint.
- **Strict Git Hygiene:** All input PDFs, translated outputs, temporary `.agents/` scratch files, virtual environments, and `.env` credentials are excluded by default in `.gitignore`.

---

## License

This project is licensed under the [MIT License](LICENSE).
