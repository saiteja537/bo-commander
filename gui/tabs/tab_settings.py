"""
gui/tabs/tab_settings.py  —  Settings
Connection details, AI API key management, BO install path, theme
"""
from gui.tabs._base import *


class SettingsTab(BaseTab):

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._build()
        self._load_current()

    def _build(self):
        self._page_header("Settings", "⚙", "AI keys, BO path, preferences")

        body = self._body
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(body, fg_color="transparent")
        scroll.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=14, pady=10)
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=1)

        # ── Connection card ───────────────────────────────────────────────────
        conn_card = self._card(scroll, "🔌 Connection", CYAN)
        conn_card.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=4)
        self._conn_info = ctk.CTkTextbox(conn_card, height=80, fg_color=BG0,
                                          text_color=TEAL, font=F_MONO, state="disabled")
        self._conn_info.pack(fill="x", padx=12, pady=(4, 12))

        # ── AI Engine card ────────────────────────────────────────────────────
        ai_card = self._card(scroll, "🤖 AI Engine (Gemini)", VIOLET)
        ai_card.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=4)

        ctk.CTkLabel(ai_card, text="Gemini API Key:", font=F_SM,
                     text_color=TEXT2).pack(anchor="w", padx=12, pady=(4, 1))
        self._key_var = ctk.StringVar()
        key_row = ctk.CTkFrame(ai_card, fg_color="transparent")
        key_row.pack(fill="x", padx=12)
        self._key_entry = ctk.CTkEntry(key_row, textvariable=self._key_var,
                                        show="*", fg_color=BG2, border_color=BG2,
                                        text_color=TEXT, font=F_BODY)
        self._key_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(key_row, text="👁", width=32, height=32,
                      fg_color=BG2, font=F_SM,
                      command=self._toggle_key_vis).pack(side="left", padx=2)
        ctk.CTkButton(ai_card, text="💾 Save Key", height=32, fg_color=VIOLET,
                      text_color="white", font=F_SM,
                      command=self._save_key).pack(fill="x", padx=12, pady=8)
        self._ai_status = ctk.CTkLabel(ai_card, text="", font=F_XS, text_color=TEXT2)
        self._ai_status.pack(padx=12, pady=(0, 8))

        # ── BO Install Path card ──────────────────────────────────────────────
        path_card = self._card(scroll, "📁 SAP BO Install Path (for log files)", TEAL)
        path_card.grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)

        ctk.CTkLabel(path_card, text="BO Install Directory:", font=F_SM,
                     text_color=TEXT2).pack(anchor="w", padx=12, pady=(4, 1))
        path_row = ctk.CTkFrame(path_card, fg_color="transparent")
        path_row.pack(fill="x", padx=12)
        self._path_var = ctk.StringVar()
        ctk.CTkEntry(path_row, textvariable=self._path_var,
                     placeholder_text="e.g. D:\\SAP BO\\SAP BO",
                     fg_color=BG2, border_color=BG2, text_color=TEXT,
                     font=F_BODY).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(path_row, text="Browse", width=80, height=32,
                      fg_color=BG2, font=F_SM,
                      command=self._browse_path).pack(side="left", padx=4)
        ctk.CTkButton(path_card, text="💾 Save Path", height=32,
                      fg_color=TEAL, text_color="white", font=F_SM,
                      command=self._save_path).pack(fill="x", padx=12, pady=8)

        # ── Cleanup Defaults card ─────────────────────────────────────────────
        cln_card = self._card(scroll, "🧹 Cleanup Defaults", AMBER)
        cln_card.grid(row=2, column=0, sticky="ew", padx=(0, 6), pady=4)
        ctk.CTkLabel(cln_card, text="Default purge age (days):", font=F_SM,
                     text_color=TEXT2).pack(anchor="w", padx=12, pady=(4, 1))
        self._days_var = ctk.StringVar(value="30")
        ctk.CTkOptionMenu(cln_card, variable=self._days_var,
                           values=["7","14","30","60","90","180"],
                           fg_color=BG2, button_color=BG2,
                           dropdown_fg_color=BG1, text_color=TEXT,
                           font=F_BODY).pack(fill="x", padx=12, pady=(0, 12))

        # ── About card ────────────────────────────────────────────────────────
        about_card = self._card(scroll, "ℹ About BO Commander", CYAN)
        about_card.grid(row=2, column=1, sticky="ew", padx=(6, 0), pady=4)
        about_text = (
            "BO Commander v2.0\n"
            "Intelligent SAP BO Control Center\n\n"
            "Developed by: Sai Teja Guddanti\n"
            "saitejaguddanti999@gmail.com\n"
            "Phase 1 — 15 Tabs, Real CRUD\n"
            "MultiBOT Autonomous AI Agent\n\n"
            "© 2025 Sai Teja Guddanti"
        )
        ctk.CTkLabel(about_card, text=about_text, font=F_SM,
                     text_color=TEXT2, justify="left").pack(padx=12, pady=(4, 12))

    def _card(self, parent, title, color):
        card = ctk.CTkFrame(parent, fg_color=BG1, corner_radius=10,
                             border_color=color, border_width=1)
        strip = ctk.CTkFrame(card, fg_color=color, height=3, corner_radius=0)
        strip.pack(fill="x")
        ctk.CTkLabel(card, text=title, font=F_H3,
                     text_color=color).pack(anchor="w", padx=12, pady=(8, 4))
        ctk.CTkFrame(card, fg_color=BG2, height=1).pack(fill="x", padx=8)
        return card

    def _load_current(self):
        try:
            details = bo_session.cms_details or {}
            info = (
                f"Host   : {details.get('host','—')}\n"
                f"Port   : {details.get('port','—')}\n"
                f"User   : {details.get('user','—')}\n"
                f"Status : {'Connected' if bo_session.connected else 'Disconnected'}"
            )
        except Exception:
            info = "Connection details unavailable"
        self._conn_info.configure(state="normal")
        self._conn_info.delete("1.0", "end")
        self._conn_info.insert("end", info)
        self._conn_info.configure(state="disabled")

        # Load saved settings
        try:
            from config import Config
            self._key_var.set(getattr(Config, "GEMINI_API_KEY", ""))
            self._path_var.set(getattr(Config, "BO_INSTALL_DIR", ""))
            self._ai_status.configure(
                text=f"Key: {'✅ Set' if self._key_var.get() else '❌ Not set'}",
                text_color=GREEN if self._key_var.get() else RED
            )
        except Exception:
            pass

    def _toggle_key_vis(self):
        current = self._key_entry.cget("show")
        self._key_entry.configure(show="" if current == "*" else "*")

    def _save_key(self):
        key = self._key_var.get().strip()
        try:
            from config import Config
            Config.GEMINI_API_KEY = key
            # Try to persist
            import os
            cfg_path = os.path.join(os.path.dirname(__file__), "../../config.py")
            if os.path.exists(cfg_path):
                text  = open(cfg_path).read()
                import re
                text  = re.sub(r'GEMINI_API_KEY\s*=\s*["\'].*?["\']',
                               f'GEMINI_API_KEY = "{key}"', text)
                open(cfg_path, "w").write(text)
            self._ai_status.configure(text="✅ Key saved", text_color=GREEN)
            self.set_status("✅ Gemini API key saved", GREEN)
        except Exception as e:
            self._ai_status.configure(text=f"❌ {e}", text_color=RED)

    def _browse_path(self):
        import tkinter.filedialog as fd
        path = fd.askdirectory(title="Select SAP BO Install Directory")
        if path:
            self._path_var.set(path)

    def _save_path(self):
        path = self._path_var.get().strip()
        try:
            from config import Config
            Config.BO_INSTALL_DIR = path
            import os, re
            cfg_path = os.path.join(os.path.dirname(__file__), "../../config.py")
            if os.path.exists(cfg_path):
                text = open(cfg_path).read()
                text = re.sub(r'BO_INSTALL_DIR\s*=\s*["\'].*?["\']',
                              f'BO_INSTALL_DIR = "{path}"', text)
                open(cfg_path, "w").write(text)
            self.set_status(f"✅ BO path saved: {path}", GREEN)
        except Exception as e:
            self.set_status(f"❌ {e}", RED)
