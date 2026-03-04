import customtkinter as ctk
import threading
from config import Config
from core.sapbo_connection import bo_session


class VersioningPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 20))

        ctk.CTkLabel(
            top,
            text="Version Management (VMS)",
            font=("Segoe UI", 24, "bold")
        ).pack(side="left")

        # ===== LEFT PANEL (OBJECT ID INPUT) =====

        left = ctk.CTkFrame(self, fg_color=Config.COLORS['bg_secondary'])
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 5))

        ctk.CTkLabel(left, text="Object ID",
                     font=("Segoe UI", 12, "bold")).pack(pady=10)

        self.obj_id_entry = ctk.CTkEntry(left, placeholder_text="Enter Object ID")
        self.obj_id_entry.pack(fill="x", padx=10, pady=5)

        ctk.CTkButton(
            left,
            text="Load Versions",
            command=self.load_versions
        ).pack(pady=10)

        # ===== RIGHT PANEL =====

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=1, column=1, sticky="nsew", padx=5)

        self.scroll = ctk.CTkScrollableFrame(
            right,
            fg_color=Config.COLORS['bg_secondary']
        )
        self.scroll.pack(fill="both", expand=True)

    # ================= LOAD REAL VERSIONS =================

    def load_versions(self):
        obj_id = self.obj_id_entry.get()
        if not obj_id:
            return

        for w in self.scroll.winfo_children():
            w.destroy()

        threading.Thread(
            target=self._fetch,
            args=(obj_id,),
            daemon=True
        ).start()

    def _fetch(self, obj_id):
        versions = bo_session.get_object_versions(obj_id)
        self.after(0, lambda: self._render(versions))

    def _render(self, versions):
        for v in versions:
            row = ctk.CTkFrame(
                self.scroll,
                fg_color=Config.COLORS['bg_tertiary'],
                height=80
            )
            row.pack(fill="x", pady=2, padx=5)

            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", padx=15, pady=10)

            color = Config.COLORS['success'] if v["is_current"] else "white"

            ctk.CTkLabel(
                info,
                text=f"Revision {v['rev']}",
                font=("Segoe UI", 14, "bold"),
                text_color=color
            ).pack(anchor="w")

            ctk.CTkLabel(
                info,
                text=f"By: {v['user']} | {v['date']}",
                text_color="gray",
                font=("Consolas", 10)
            ).pack(anchor="w")

            ctk.CTkLabel(
                row,
                text=f"\"{v['comment']}\"",
                font=("Segoe UI", 11, "italic")
            ).pack(side="left", padx=20)