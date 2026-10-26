import os
import sys
import threading
import subprocess
from pathlib import Path
from typing import List, Dict
import customtkinter as ctk
from tkinter import filedialog, messagebox
from dotenv import load_dotenv, set_key

from translator_gemini import GeminiTranslator
from pdf_engine import PDFTranslator
from office_engine import OfficeTranslator

ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class DocTranslatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Document Translator (Batch Queue) — Gemini Flash")
        self.geometry("860x820")
        self.minsize(800, 720)

        # Set application window icon
        icon_path = Path(__file__).parent / "app_icon.ico"
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            icon_path = Path(sys._MEIPASS) / "app_icon.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

        self.saved_api_key = os.getenv("GEMINI_API_KEY", "")
        self.queue: List[Dict] = []
        self.is_translating = False
        self.cancel_requested = False
        self.last_output_dir = None

        self._build_ui()

    def _build_ui(self):
        # 1. Header Frame
        header_frame = ctk.CTkFrame(self, corner_radius=10)
        header_frame.pack(fill="x", padx=16, pady=(12, 6))

        title_label = ctk.CTkLabel(
            header_frame,
            text="Document Translator — Batch Queue",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title_label.pack(anchor="w", padx=14, pady=(8, 2))

        sub_label = ctk.CTkLabel(
            header_frame,
            text="Upload multiple PDFs or Office documents • Sequential Queue • Arial Layout Preservation",
            font=ctk.CTkFont(size=12),
            text_color="gray70"
        )
        sub_label.pack(anchor="w", padx=14, pady=(0, 8))

        # 2. API Key Section
        api_frame = ctk.CTkFrame(self, corner_radius=10)
        api_frame.pack(fill="x", padx=16, pady=4)

        ctk.CTkLabel(
            api_frame,
            text="Gemini API Key:",
            font=ctk.CTkFont(size=12, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(6, 2))

        self.api_entry = ctk.CTkEntry(
            api_frame,
            placeholder_text="Enter your Gemini API key (AIzaSy...)",
            show="*",
            width=560
        )
        self.api_entry.grid(row=1, column=0, sticky="ew", padx=(14, 6), pady=(0, 6))
        if self.saved_api_key:
            self.api_entry.insert(0, self.saved_api_key)

        self.show_key_var = ctk.BooleanVar(value=False)
        self.toggle_key_btn = ctk.CTkButton(
            api_frame,
            text="Show",
            width=60,
            command=self._toggle_key_visibility
        )
        self.toggle_key_btn.grid(row=1, column=1, padx=4, pady=(0, 6))

        self.save_key_btn = ctk.CTkButton(
            api_frame,
            text="Save Key",
            width=80,
            command=self._save_api_key
        )
        self.save_key_btn.grid(row=1, column=2, padx=(4, 14), pady=(0, 6))
        api_frame.grid_columnconfigure(0, weight=1)

        # 3. Settings Bar (Languages, Model, Pacing)
        opts_frame = ctk.CTkFrame(self, corner_radius=10)
        opts_frame.pack(fill="x", padx=16, pady=4)

        # Source Language
        ctk.CTkLabel(opts_frame, text="Source Language:", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(6, 2)
        )
        self.src_lang_menu = ctk.CTkOptionMenu(
            opts_frame,
            values=["Auto Detect", "English", "Spanish", "Vietnamese", "French", "German", "Japanese", "Chinese", "Korean", "Portuguese"],
            width=180
        )
        self.src_lang_menu.set("Auto Detect")
        self.src_lang_menu.grid(row=1, column=0, padx=(14, 8), pady=(0, 6), sticky="w")

        # Target Language
        ctk.CTkLabel(opts_frame, text="Target Language:", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=1, sticky="w", padx=10, pady=(6, 2)
        )
        self.tgt_lang_menu = ctk.CTkOptionMenu(
            opts_frame,
            values=["Spanish", "English", "Vietnamese", "French", "German", "Japanese", "Chinese", "Korean", "Portuguese"],
            width=180
        )
        self.tgt_lang_menu.set("Spanish")
        self.tgt_lang_menu.grid(row=1, column=1, padx=8, pady=(0, 6), sticky="w")

        # Model Selection
        ctk.CTkLabel(opts_frame, text="Gemini Model:", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=2, sticky="w", padx=10, pady=(6, 2)
        )
        self.model_menu = ctk.CTkOptionMenu(
            opts_frame,
            values=["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemma-4-31b-it", "gemini-flash-latest"],
            width=180
        )
        self.model_menu.set("gemini-3.5-flash-lite")
        self.model_menu.grid(row=1, column=2, padx=8, pady=(0, 6), sticky="w")

        # API Rate Pacing
        ctk.CTkLabel(opts_frame, text="Rate Pacing:", font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=3, sticky="w", padx=10, pady=(6, 2)
        )
        self.pacing_menu = ctk.CTkOptionMenu(
            opts_frame,
            values=["Safe (2.5s)", "Fast (1.0s)", "Relaxed (4.0s)"],
            width=170
        )
        self.pacing_menu.set("Safe (2.5s)")
        self.pacing_menu.grid(row=1, column=3, padx=(8, 14), pady=(0, 6), sticky="w")

        # 4. Export Path Selection Frame
        export_frame = ctk.CTkFrame(self, corner_radius=10)
        export_frame.pack(fill="x", padx=16, pady=4)

        ctk.CTkLabel(
            export_frame,
            text="Export Folder (Where translated files are saved):",
            font=ctk.CTkFont(size=12, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(6, 2))

        self.export_path_entry = ctk.CTkEntry(
            export_frame,
            placeholder_text="Default: Same folder as original file (Leave empty or browse)",
            width=580
        )
        self.export_path_entry.grid(row=1, column=0, sticky="ew", padx=(14, 8), pady=(0, 8))

        self.browse_export_btn = ctk.CTkButton(
            export_frame,
            text="Browse Folder",
            width=130,
            command=self._browse_export_folder
        )
        self.browse_export_btn.grid(row=1, column=1, padx=(0, 14), pady=(0, 8))
        export_frame.grid_columnconfigure(0, weight=1)

        # 5. Document Queue Section
        queue_frame = ctk.CTkFrame(self, corner_radius=10)
        queue_frame.pack(fill="both", expand=True, padx=16, pady=4)

        top_queue_bar = ctk.CTkFrame(queue_frame, fg_color="transparent")
        top_queue_bar.pack(fill="x", padx=14, pady=(8, 4))

        self.queue_count_label = ctk.CTkLabel(
            top_queue_bar,
            text="Document Queue (0 files ready):",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.queue_count_label.pack(side="left")

        self.clear_btn = ctk.CTkButton(
            top_queue_bar,
            text="Clear Queue",
            width=90,
            fg_color="#A83232",
            hover_color="#802424",
            command=self._clear_queue
        )
        self.clear_btn.pack(side="right", padx=(6, 0))

        self.add_files_btn = ctk.CTkButton(
            top_queue_bar,
            text="+ Add Documents (Select Multiple)",
            width=210,
            command=self._browse_files
        )
        self.add_files_btn.pack(side="right")

        # Scrollable Frame for Queue Items
        self.queue_scroll = ctk.CTkScrollableFrame(queue_frame, height=130)
        self.queue_scroll.pack(fill="both", expand=True, padx=14, pady=(4, 8))

        # 6. Progress and Status (Bottom)
        bottom_frame = ctk.CTkFrame(self, corner_radius=10)
        bottom_frame.pack(fill="x", padx=16, pady=(4, 12))

        # Action Buttons: Start and Cancel
        action_bar = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        action_bar.pack(fill="x", padx=14, pady=(8, 6))

        self.start_btn = ctk.CTkButton(
            action_bar,
            text="Start Batch Translation",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=38,
            command=self._start_batch_thread
        )
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.cancel_btn = ctk.CTkButton(
            action_bar,
            text="Cancel",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=38,
            width=120,
            fg_color="#A83232",
            hover_color="#802424",
            state="disabled",
            command=self._request_cancel
        )
        self.cancel_btn.pack(side="right", padx=(6, 0))

        # Total Batch Progress
        self.batch_prog_label = ctk.CTkLabel(
            bottom_frame,
            text="Total Progress: 0/0 files",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w"
        )
        self.batch_prog_label.pack(fill="x", padx=14, pady=(2, 0))

        self.total_progress_bar = ctk.CTkProgressBar(bottom_frame)
        self.total_progress_bar.pack(fill="x", padx=14, pady=(2, 6))
        self.total_progress_bar.set(0.0)

        # Current File Progress
        self.file_prog_label = ctk.CTkLabel(
            bottom_frame,
            text="Status: Ready. Add documents above.",
            font=ctk.CTkFont(size=12),
            text_color="gray80",
            anchor="w"
        )
        self.file_prog_label.pack(fill="x", padx=14, pady=(0, 2))

        self.file_progress_bar = ctk.CTkProgressBar(bottom_frame)
        self.file_progress_bar.pack(fill="x", padx=14, pady=(2, 6))
        self.file_progress_bar.set(0.0)

        # Output buttons
        btn_bar = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        btn_bar.pack(fill="x", padx=14, pady=(0, 8))

        self.open_folder_btn = ctk.CTkButton(
            btn_bar,
            text="Open Output Folder",
            state="disabled",
            command=self._open_output_folder
        )
        self.open_folder_btn.pack(side="left", fill="x", expand=True)

    def _toggle_key_visibility(self):
        if self.show_key_var.get():
            self.api_entry.configure(show="*")
            self.toggle_key_btn.configure(text="Show")
            self.show_key_var.set(False)
        else:
            self.api_entry.configure(show="")
            self.toggle_key_btn.configure(text="Hide")
            self.show_key_var.set(True)

    def _save_api_key(self):
        key = self.api_entry.get().strip()
        if not key:
            messagebox.showwarning("Empty Key", "Please enter a valid Gemini API key.")
            return

        ENV_PATH.touch(exist_ok=True)
        set_key(str(ENV_PATH), "GEMINI_API_KEY", key)
        self.saved_api_key = key
        messagebox.showinfo("Saved", "Gemini API Key saved to local configuration.")

    def _browse_export_folder(self):
        folder = filedialog.askdirectory(title="Select Destination Folder for Translated Files")
        if folder:
            self.export_path_entry.delete(0, "end")
            self.export_path_entry.insert(0, folder)
            self.last_output_dir = folder

    def _browse_files(self):
        filetypes = [
            ("All Supported Documents", "*.pdf;*.docx;*.pptx;*.xlsx"),
            ("PDF Documents (*.pdf)", "*.pdf"),
            ("Word Documents (*.docx)", "*.docx"),
            ("PowerPoint Presentations (*.pptx)", "*.pptx"),
            ("Excel Spreadsheets (*.xlsx)", "*.xlsx")
        ]
        filenames = filedialog.askopenfilenames(
            title="Select Documents for Translation Queue (Hold Ctrl/Shift for Multiple)",
            filetypes=filetypes
        )
        if filenames:
            for f in filenames:
                if any(item["path"] == f for item in self.queue):
                    continue
                self.queue.append({
                    "path": f,
                    "name": Path(f).name,
                    "status": "Waiting in queue"
                })
            self._refresh_queue_ui()

    def _clear_queue(self):
        if self.is_translating:
            messagebox.showwarning("Busy", "Cannot clear queue while translation is in progress.")
            return
        self.queue.clear()
        self._refresh_queue_ui()

    def _refresh_queue_ui(self):
        for widget in self.queue_scroll.winfo_children():
            widget.destroy()

        self.queue_count_label.configure(text=f"Document Queue ({len(self.queue)} files ready):")

        if not self.queue:
            empty_lbl = ctk.CTkLabel(
                self.queue_scroll,
                text="No documents queued. Click '+ Add Documents' to queue PDFs.",
                text_color="gray60"
            )
            empty_lbl.pack(pady=20)
            return

        for idx, item in enumerate(self.queue):
            row = ctk.CTkFrame(self.queue_scroll, fg_color="gray20", corner_radius=6)
            row.pack(fill="x", pady=2, padx=4)

            num_lbl = ctk.CTkLabel(row, text=f"#{idx+1}", width=35, font=ctk.CTkFont(weight="bold"))
            num_lbl.pack(side="left", padx=(8, 4), pady=6)

            name_lbl = ctk.CTkLabel(row, text=item["name"], anchor="w")
            name_lbl.pack(side="left", fill="x", expand=True, padx=4, pady=6)

            status_lbl = ctk.CTkLabel(
                row,
                text=item["status"],
                width=170,
                anchor="e",
                font=ctk.CTkFont(size=11),
                text_color=self._get_status_color(item["status"])
            )
            status_lbl.pack(side="right", padx=(4, 10), pady=6)
            item["status_widget"] = status_lbl

    def _get_status_color(self, status: str) -> str:
        if "Completed" in status or "Done" in status:
            return "#4CAF50"  # Green
        elif "Translating" in status:
            return "#64B5F6"  # Blue
        elif "Cancelled" in status:
            return "#FFA726"  # Orange
        elif "Error" in status or "Failed" in status:
            return "#EF5350"  # Red
        return "gray70"

    def _update_file_status(self, index: int, status_text: str):
        if 0 <= index < len(self.queue):
            self.queue[index]["status"] = status_text
            widget = self.queue[index].get("status_widget")
            if widget and widget.winfo_exists():
                widget.configure(text=status_text, text_color=self._get_status_color(status_text))

    def _request_cancel(self):
        if self.is_translating:
            self.cancel_requested = True
            self.cancel_btn.configure(state="disabled", text="Cancelling...")
            self.file_prog_label.configure(text="Cancelling translation...")

    def _start_batch_thread(self):
        if self.is_translating:
            return

        api_key = self.api_entry.get().strip()
        if not api_key:
            messagebox.showerror("Missing API Key", "Please enter and save your Gemini API key first.")
            return

        if not self.queue:
            messagebox.showwarning("Empty Queue", "Please add at least one document to the queue.")
            return

        self.is_translating = True
        self.cancel_requested = False
        self.start_btn.configure(state="disabled", text="Translating Queue...")
        self.cancel_btn.configure(state="normal", text="Cancel")
        self.add_files_btn.configure(state="disabled")
        self.clear_btn.configure(state="disabled")
        self.open_folder_btn.configure(state="disabled")

        thread = threading.Thread(
            target=self._run_queue_worker,
            args=(api_key,),
            daemon=True
        )
        thread.start()

    def _run_queue_worker(self, api_key: str):
        src_lang = self.src_lang_menu.get()
        tgt_lang = self.tgt_lang_menu.get()
        model_name = self.model_menu.get()
        pacing_str = self.pacing_menu.get()

        if "1.0" in pacing_str:
            interval = 1.0
        elif "4.0" in pacing_str:
            interval = 4.0
        else:
            interval = 2.5

        gemini = GeminiTranslator(api_key=api_key, model_name=model_name, min_interval=interval)
        pdf_engine = PDFTranslator(gemini)
        office_engine = OfficeTranslator(gemini)

        total_files = len(self.queue)
        completed_count = 0

        # Custom export folder or original file folder
        chosen_export_dir = self.export_path_entry.get().strip()
        if chosen_export_dir and not os.path.exists(chosen_export_dir):
            try:
                os.makedirs(chosen_export_dir, exist_ok=True)
            except Exception:
                chosen_export_dir = ""

        for f_idx, item in enumerate(self.queue):
            if self.cancel_requested:
                for rem_idx in range(f_idx, total_files):
                    self.after(0, lambda idx=rem_idx: self._update_file_status(idx, "Cancelled"))
                break

            input_path = item["path"]
            file_name = item["name"]
            p = Path(input_path)
            ext = p.suffix.lower()

            target_dir = chosen_export_dir if chosen_export_dir else str(p.parent)
            self.last_output_dir = target_dir

            # Format filename as requested: OriginalName_traducido.ext
            output_filename = f"{p.stem}_traducido{ext}"
            output_path = os.path.join(target_dir, output_filename)

            self.after(0, lambda idx=f_idx: self._update_file_status(idx, "Translating..."))
            self.after(0, lambda idx=f_idx, tot=total_files, name=file_name: self.batch_prog_label.configure(
                text=f"Total Progress: File {idx+1}/{tot} ({name})"
            ))
            self.after(0, lambda idx=f_idx, tot=total_files: self.total_progress_bar.set(idx / tot))

            def file_progress(ratio: float, msg: str):
                self.after(0, lambda r=ratio: self.file_progress_bar.set(r))
                self.after(0, lambda m=msg: self.file_prog_label.configure(text=m))

            try:
                if ext == ".pdf":
                    pdf_engine.translate_pdf(
                        input_path, output_path, src_lang, tgt_lang,
                        progress_callback=file_progress,
                        cancel_check=lambda: self.cancel_requested
                    )
                elif ext == ".docx":
                    office_engine.translate_docx(
                        input_path, output_path, src_lang, tgt_lang,
                        progress_callback=file_progress,
                        cancel_check=lambda: self.cancel_requested
                    )
                elif ext == ".pptx":
                    office_engine.translate_pptx(
                        input_path, output_path, src_lang, tgt_lang,
                        progress_callback=file_progress,
                        cancel_check=lambda: self.cancel_requested
                    )
                elif ext == ".xlsx":
                    office_engine.translate_xlsx(
                        input_path, output_path, src_lang, tgt_lang,
                        progress_callback=file_progress,
                        cancel_check=lambda: self.cancel_requested
                    )
                else:
                    raise ValueError(f"Unsupported format: {ext}")

                completed_count += 1
                self.after(0, lambda idx=f_idx: self._update_file_status(idx, "Completed"))
            except InterruptedError:
                self.after(0, lambda idx=f_idx: self._update_file_status(idx, "Cancelled"))
                for rem_idx in range(f_idx + 1, total_files):
                    self.after(0, lambda idx=rem_idx: self._update_file_status(idx, "Cancelled"))
                break
            except Exception as e:
                err_str = str(e)
                self.after(0, lambda idx=f_idx, err=err_str: self._update_file_status(idx, f"Error: {err[:22]}"))

        if self.cancel_requested:
            self.after(0, self.file_prog_label.configure, {"text": "Translation was cancelled."})
        else:
            self.after(0, self.total_progress_bar.set, 1.0)
            self.after(0, lambda c=completed_count, t=total_files: self.batch_prog_label.configure(
                text=f"Batch Finished: {c}/{t} files translated successfully."
            ))

        self.after(0, self._on_batch_complete)

    def _on_batch_complete(self):
        self.is_translating = False
        self.start_btn.configure(state="normal", text="Start Batch Translation")
        self.cancel_btn.configure(state="disabled", text="Cancel")
        self.add_files_btn.configure(state="normal")
        self.clear_btn.configure(state="normal")
        self.open_folder_btn.configure(state="normal")
        if not self.cancel_requested:
            self.file_prog_label.configure(text="Batch complete! Check output files.")
            messagebox.showinfo("Queue Finished", "All queued documents have been processed!")

    def _open_output_folder(self):
        if self.last_output_dir and os.path.exists(self.last_output_dir):
            subprocess.run(["explorer", self.last_output_dir])

if __name__ == "__main__":
    app = DocTranslatorApp()
    app.mainloop()
