import customtkinter as ctk
from tkinter import filedialog
import threading
from config import Config
from ai.gemini_client import ai_client

class LogAnalyzerPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        
        # Split: Input Area | Analysis Report
        self.grid_rowconfigure(1, weight=1); self.grid_columnconfigure(0, weight=1)

        # 1. Top Bar
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ctk.CTkLabel(top, text="📜 Deep Log Analyzer", font=("Segoe UI", 24, "bold")).pack(side="left")
        
        # 2. Workspace
        self.paned = ctk.CTkFrame(self, fg_color="transparent")
        self.paned.grid(row=1, column=0, sticky="nsew")
        self.paned.grid_columnconfigure((0, 1), weight=1); self.paned.grid_rowconfigure(0, weight=1)

        # Left: Raw Log Input
        left_f = ctk.CTkFrame(self.paned, fg_color=Config.COLORS['bg_secondary'])
        left_f.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        
        ctk.CTkLabel(left_f, text="Source Log Content", font=("Segoe UI", 12, "bold")).pack(pady=10)
        self.input_text = ctk.CTkTextbox(left_f, font=("Consolas", 11), fg_color="#0F172A", text_color="#F87171")
        self.input_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.input_text.insert("1.0", "Drag log file here or click 'Load'...")

        # Right: AI Diagnosis
        right_f = ctk.CTkFrame(self.paned, fg_color=Config.COLORS['bg_secondary'])
        right_f.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        
        ctk.CTkLabel(right_f, text="AI Pattern Recognition & Solution", font=("Segoe UI", 12, "bold")).pack(pady=10)
        self.output_text = ctk.CTkTextbox(right_f, font=("Segoe UI", 13), fg_color="#1E293B", text_color="#E2E8F0")
        self.output_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # 3. Action Bar
        act = ctk.CTkFrame(self, fg_color="transparent")
        act.grid(row=2, column=0, sticky="ew", pady=10)
        
        ctk.CTkButton(act, text="📁 Load .glf / .log", width=150, command=self.load_file).pack(side="left")
        self.btn_run = ctk.CTkButton(act, text="🔍 Identify Error Patterns", fg_color="#8B5CF6", width=200, command=self.run_rca)
        self.btn_run.pack(side="right")

    def load_file(self):
        path = filedialog.askopenfilename()
        if path:
            with open(path, 'r', errors='ignore') as f:
                content = "".join(f.readlines()[-1000:]) # Last 1000 lines
                self.input_text.delete("1.0", "end"); self.input_text.insert("1.0", content)

    def run_rca(self):
        self.btn_run.configure(state="disabled", text="Processing Pattern...")
        self.output_text.delete("1.0", "end"); self.output_text.insert("1.0", "🤖 AI is parsing logs... finding error codes...")
        threading.Thread(target=self._ai_work, daemon=True).start()

    def _ai_work(self):
        raw = self.input_text.get("1.0", "end")
        prompt = f"Analyze these SAP BO logs. Find common patterns, identify error codes, and suggest a fix roadmap:\n{raw}"
        res = ai_client.get_response(prompt)
        self.after(0, lambda: [self.output_text.delete("1.0", "end"), self.output_text.insert("1.0", res), self.btn_run.configure(state="normal", text="🔍 Identify Error Patterns")])