import customtkinter as ctk
import threading
from config import Config
from core.sapbo_connection import bo_session

class DependencyResolverPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        
        ctk.CTkLabel(self, text="📦 Promotion Dependency Resolver", font=("Segoe UI", 24, "bold")).pack(anchor="w", pady=(0, 20))

        search_f = ctk.CTkFrame(self, fg_color=Config.COLORS['bg_secondary'], height=80)
        search_f.pack(fill="x", pady=10)
        
        self.entry = ctk.CTkEntry(search_f, placeholder_text="Enter Report ID (e.g. 5432)", width=250)
        self.entry.pack(side="left", padx=20, pady=20)
        ctk.CTkButton(search_f, text="🔍 Scan Dependencies", command=self.run_scan).pack(side="left")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=Config.COLORS['bg_secondary'])
        self.scroll.pack(fill="both", expand=True, pady=10)

    def run_scan(self):
        rid = self.entry.get().strip()
        if not rid: return
        for w in self.scroll.winfo_children(): w.destroy()
        threading.Thread(target=self._fetch, args=(rid,), daemon=True).start()

    def _fetch(self, rid):
        deps = bo_session.get_report_dependencies(rid)
        self.after(0, lambda: self._render(deps))

    def _render(self, deps):
        if not deps:
            ctk.CTkLabel(self.scroll, text="No dependencies found or invalid ID.").pack(pady=40); return
            
        for d in deps:
            row = ctk.CTkFrame(self.scroll, fg_color=Config.COLORS['bg_tertiary'], height=55)
            row.pack(fill="x", pady=2, padx=5)
            ctk.CTkLabel(row, text=f"[{d['kind']}] {d['name']}", font=("Segoe UI", 12, "bold"), width=400, anchor="w").pack(side="left", padx=15)
            ctk.CTkLabel(row, text=f"ID: {d['id']}", text_color="gray").pack(side="left", padx=10)
            ctk.CTkButton(row, text="Add to Job", width=80, height=22).pack(side="right", padx=15)