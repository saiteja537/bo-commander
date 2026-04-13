"""
bo_commander.py  —  BO Commander v2.0
Intelligent SAP BusinessObjects Control Center
15-Tab Architecture + MultiBOT AI Agent (Phase 1 Production)

Developed by : Sai Teja Guddanti
Contact      : saitejaguddanti999@gmail.com
LinkedIn     : https://www.linkedin.com/in/sai-teja-628082288
© 2025 Sai Teja Guddanti. All rights reserved.

FIXES IN THIS VERSION
  FIX-1  LoginPage crash  — removed illegal 'master=' keyword arg
  FIX-2  Tab import safety — missing/broken tab file never kills the whole app
  FIX-3  Tab caching       — each tab built once and reused (faster nav)
  FIX-4  Windows DPI       — sharp rendering on 4K / high-DPI monitors
  FIX-5  Clean shutdown    — monitor + bo_session stopped gracefully on exit
  FIX-6  Sidebar info      — shows logged-in user + host after login
"""

import sys
import threading
import logging
from pathlib import Path

logger = logging.getLogger("BOCommander")

# ──────────────────────────────────────────────────────────────────────────────
# SETTINGS
# ──────────────────────────────────────────────────────────────────────────────
WEB_PORT = 8765
DOCS_DIR = Path(__file__).parent / "docs"
VERSION  = "2.0"


# ──────────────────────────────────────────────────────────────────────────────
# PRODUCT INFO WEB SERVER  →  http://localhost:8765
# ──────────────────────────────────────────────────────────────────────────────
def _start_web_server():
    """Serve docs/ at http://localhost:8765"""
    import http.server, socketserver
    if not DOCS_DIR.exists():
        return

    class _H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(DOCS_DIR), **kw)
        def log_message(self, *a):
            pass

    def _serve():
        try:
            with socketserver.TCPServer(("", WEB_PORT), _H) as h:
                h.serve_forever()
        except OSError:
            pass

    threading.Thread(target=_serve, daemon=True).start()


# ──────────────────────────────────────────────────────────────────────────────
# SAFE TAB IMPORT — one bad file never crashes the whole app
# ──────────────────────────────────────────────────────────────────────────────
def _safe_import(module_path: str, class_name: str):
    """Import a tab class. Returns a friendly error placeholder on failure."""
    try:
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name)
    except Exception as exc:
        logger.error(f"Tab import failed  [{module_path}.{class_name}]: {exc}")

        import customtkinter as ctk

        _err = str(exc)
        _mod = module_path
        _cls = class_name

        class _Fallback(ctk.CTkFrame):
            def __init__(self, master, **kw):
                super().__init__(master, fg_color="#0F172A", **kw)
                self.grid_columnconfigure(0, weight=1)
                self.grid_rowconfigure(0, weight=1)
                box = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=14)
                box.grid(padx=60, pady=60, sticky="nsew")
                box.grid_columnconfigure(0, weight=1)
                ctk.CTkLabel(box, text="⚠  Tab Failed to Load",
                             font=("Segoe UI", 20, "bold"),
                             text_color="#EF4444").grid(pady=(28, 6))
                ctk.CTkLabel(box, text=f"{_mod}.{_cls}",
                             font=("Consolas", 11),
                             text_color="#94A3B8").grid(pady=(0, 8))
                tb = ctk.CTkTextbox(box, width=700, height=120,
                                     fg_color="#0F172A", text_color="#F59E0B",
                                     font=("Consolas", 10))
                tb.grid(padx=20, pady=4)
                tb.insert("end", _err)
                tb.configure(state="disabled")
                ctk.CTkLabel(box,
                             text="Fix the error in the file listed above and restart BO Commander.",
                             font=("Segoe UI", 10), text_color="#64748B").grid(pady=(8, 24))

        return _Fallback


# ──────────────────────────────────────────────────────────────────────────────
# GUI
# ──────────────────────────────────────────────────────────────────────────────
def launch_gui():

    # ── Windows DPI (must run before any Tk window opens) ────────────────────
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    import customtkinter as ctk
    from config import Config
    from core.sapbo_connection import bo_session

    # Optional heavy modules — safe fallback if missing
    SystemMonitor = None
    try:
        from core.monitoring import SystemMonitor
    except Exception as e:
        logger.warning(f"SystemMonitor unavailable: {e}")

    SentinelAgent = None
    try:
        from ai.sentinel_agent import SentinelAgent
    except Exception as e:
        logger.warning(f"SentinelAgent unavailable: {e}")

    # Login page — required, crash hard if missing
    from gui.pages.login import LoginPage

    # ── 15 Tabs (safe imports) ────────────────────────────────────────────────
    TABS = [
        ("🏠  Dashboard",      _safe_import("gui.tabs.tab_dashboard",       "DashboardTab")),
        ("🤖  MultiBOT",       _safe_import("gui.tabs.tab_multibot",        "MultiBOTTab")),
        ("🖥  Servers",        _safe_import("gui.tabs.tab_servers",         "ServersTab")),
        ("👥  Users",          _safe_import("gui.tabs.tab_users",           "UsersTab")),
        ("🔐  Security",       _safe_import("gui.tabs.tab_security",        "SecurityTab")),
        ("📊  Reports",        _safe_import("gui.tabs.tab_reports",         "ReportsTab")),
        ("🌐  Universes",      _safe_import("gui.tabs.tab_universes",       "UniversesTab")),
        ("📅  Scheduling",     _safe_import("gui.tabs.tab_scheduling",      "SchedulingTab")),
        ("🔄  Promotion",      _safe_import("gui.tabs.tab_promotion",       "PromotionTab")),
        ("🗄  Repository",     _safe_import("gui.tabs.tab_repository",      "RepositoryTab")),
        ("📋  Logs",           _safe_import("gui.tabs.tab_logs",            "LogsTab")),
        ("🔗  Dependencies",   _safe_import("gui.tabs.tab_dependencies",    "DependenciesTab")),
        ("📡  Monitoring",     _safe_import("gui.tabs.tab_monitoring",      "MonitoringTab")),
        ("🧹  Housekeeping",   _safe_import("gui.tabs.tab_housekeeping",    "HousekeepingTab")),
        ("🔍  Query Builder",  _safe_import("gui.tabs.tab_query_builder",   "QueryBuilderTab")),
        ("🧹  Cleanup",        _safe_import("gui.tabs.tab_cleanup",         "CleanupTab")),
        ("⚙  Settings",       _safe_import("gui.tabs.tab_settings",        "SettingsTab")),
    ]

    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    C = Config.COLORS

    # ──────────────────────────────────────────────────────────────────────────
    class BOCommanderApp(ctk.CTk):

        def __init__(self):
            super().__init__()
            self.title(f"{Config.APP_NAME}  v{VERSION}  |  AI-Powered SAP BO Control Center")
            self.geometry("1500x960")
            self.minsize(1200, 780)
            self.protocol("WM_DELETE_WINDOW", self._on_close)

            self._monitor  = None
            self._sentinel = None
            self._tab_cache: dict = {}
            self._user_name = ""

            if SentinelAgent:
                try:
                    self._sentinel = SentinelAgent(ui_callback=lambda: None)
                except Exception as e:
                    logger.warning(f"SentinelAgent init: {e}")

            self._show_login()

        # ── Lifecycle ─────────────────────────────────────────────────────────
        def _on_close(self):
            self._stop_bg()
            try:
                bo_session.logout()
            except Exception:
                pass
            self.destroy()

        def _stop_bg(self):
            if self._monitor:
                try:
                    self._monitor.stop()
                except Exception:
                    pass
                self._monitor = None

        def _clear(self):
            for w in self.winfo_children():
                try:
                    w.destroy()
                except Exception:
                    pass

        # ── Login ─────────────────────────────────────────────────────────────
        def _show_login(self):
            self._clear()
            self._tab_cache.clear()

            # ✅ FIX-1: parent passed positionally — LoginPage(self, ...)
            #            NOT LoginPage(master=self, ...) which caused the crash
            # ✅ FIX-7: sentinel_agent is a required arg in LoginPage — always pass it
            #            (pass None when SentinelAgent failed to load)
            kw = {
                "on_success":     self._on_login_success,
                "sentinel_agent": self._sentinel,   # None when unavailable
            }

            LoginPage(self, **kw).pack(fill="both", expand=True)

        def _on_login_success(self):
            try:
                self._user_name = bo_session.cms_details.get("user", "")
            except Exception:
                self._user_name = ""

            self._clear()

            if SystemMonitor:
                try:
                    # FIX: SystemMonitor may require sentinel_agent as first arg
                    try:
                        self._monitor = SystemMonitor(self._sentinel)
                    except TypeError:
                        self._monitor = SystemMonitor()
                    self._monitor.start()
                except Exception as e:
                    logger.warning(f"Monitor start: {e}")

            self._build_main()

        def logout(self):
            self._stop_bg()
            try:
                bo_session.logout()
            except Exception:
                pass
            self._tab_cache.clear()
            self._show_login()

        # ── Main shell ────────────────────────────────────────────────────────
        def _build_main(self):
            self.configure(fg_color=C["bg_primary"])
            self.grid_columnconfigure(1, weight=1)
            self.grid_rowconfigure(0, weight=1)

            # ── Sidebar ───────────────────────────────────────────────────────
            sb = ctk.CTkFrame(self, width=230, corner_radius=0,
                               fg_color=C["bg_secondary"])
            sb.grid(row=0, column=0, sticky="nsew")
            sb.grid_propagate(False)

            # Brand
            hdr = ctk.CTkFrame(sb, fg_color=C["primary"], height=72, corner_radius=0)
            hdr.pack(fill="x")
            hdr.pack_propagate(False)
            ctk.CTkLabel(hdr, text="⚡  BO Commander",
                         font=("Segoe UI", 16, "bold"),
                         text_color="white").pack(pady=(14, 0))
            ctk.CTkLabel(hdr, text=f"v{VERSION}  ·  AI-Powered",
                         font=("Segoe UI", 9),
                         text_color="#bfdbfe").pack()

            # User info
            info = ctk.CTkFrame(sb, fg_color=C["bg_tertiary"],
                                 corner_radius=8)
            info.pack(fill="x", padx=10, pady=(10, 4))
            user = self._user_name or "Administrator"
            host = bo_session.cms_details.get("host", "—")
            ctk.CTkLabel(info, text=f"👤  {user}",
                         font=("Segoe UI", 10, "bold"),
                         text_color=C["text_primary"],
                         anchor="w").pack(fill="x", padx=8, pady=(6, 0))
            ctk.CTkLabel(info, text=f"🖧  {host}",
                         font=("Segoe UI", 9),
                         text_color=C["text_secondary"],
                         anchor="w").pack(fill="x", padx=8, pady=(0, 6))

            # Connection status
            self._conn_lbl = ctk.CTkLabel(
                sb, text="●  Connected",
                font=("Segoe UI", 10, "bold"),
                text_color=C["success"]
            )
            self._conn_lbl.pack(pady=(2, 6))

            # Nav
            nav = ctk.CTkScrollableFrame(sb, fg_color="transparent",
                                          scrollbar_button_color=C["bg_tertiary"])
            nav.pack(fill="both", expand=True, padx=6)

            self._nav_btns = {}
            for label, _ in TABS:
                btn = ctk.CTkButton(
                    nav, text=label, height=38, corner_radius=8,
                    anchor="w", font=("Segoe UI", 11),
                    fg_color="transparent",
                    text_color=C["text_secondary"],
                    hover_color=C["bg_tertiary"],
                    command=lambda l=label: self._select_tab(l)
                )
                btn.pack(fill="x", pady=1)
                self._nav_btns[label] = btn

            # Logout
            ctk.CTkFrame(sb, fg_color=C["bg_tertiary"], height=1
                          ).pack(fill="x", padx=8, pady=4)
            ctk.CTkButton(
                sb, text="⏻  Log Out", height=36,
                fg_color=C["danger"], hover_color="#dc2626",
                font=("Segoe UI", 11, "bold"),
                command=self.logout
            ).pack(fill="x", padx=8, pady=(0, 4))

            ctk.CTkLabel(sb,
                         text=f"BO Commander v{VERSION}  ·  Phase 1",
                         font=("Segoe UI", 8),
                         text_color=C["bg_tertiary"]
                         ).pack(pady=(0, 8))

            # ── Content ───────────────────────────────────────────────────────
            self._content = ctk.CTkFrame(self, corner_radius=0,
                                          fg_color=C["bg_primary"])
            self._content.grid(row=0, column=1, sticky="nsew")
            self._content.grid_columnconfigure(0, weight=1)
            self._content.grid_rowconfigure(0, weight=1)

            self._select_tab(TABS[0][0])   # open Dashboard

        # ── Tab switch + caching ──────────────────────────────────────────────
        def _select_tab(self, label: str):
            # Update nav highlight
            for l, btn in self._nav_btns.items():
                active = (l == label)
                btn.configure(
                    fg_color=C["bg_tertiary"] if active else "transparent",
                    text_color=C["primary"]   if active else C["text_secondary"]
                )

            # ✅ FIX-3: Hide all cached tabs instead of destroying them
            for cached in self._tab_cache.values():
                try:
                    cached.grid_forget()
                except Exception:
                    pass

            # Build on first visit, reuse after
            if label not in self._tab_cache:
                tab_cls = next((cls for l, cls in TABS if l == label), None)
                if tab_cls is None:
                    return
                try:
                    tab = tab_cls(self._content)
                except Exception as exc:
                    logger.error(f"Tab init crash [{label}]: {exc}")
                    tab = ctk.CTkFrame(self._content, fg_color=C["bg_primary"])
                    ctk.CTkLabel(
                        tab,
                        text=f"❌  {label} crashed on load\n\n{exc}",
                        font=("Segoe UI", 12),
                        text_color=C["danger"],
                        justify="center"
                    ).pack(expand=True)
                self._tab_cache[label] = tab

            self._tab_cache[label].grid(row=0, column=0, sticky="nsew")

    # ── Launch ────────────────────────────────────────────────────────────────
    app = BOCommanderApp()
    app.mainloop()


# ──────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    _start_web_server()

    try:
        from core.banner import print_banner
        print_banner()
    except Exception:
        pass

    print(f"    📖  Product info & features → http://localhost:{WEB_PORT}")
    print(f"    ⚠   AI tools may make mistakes — verify critical actions before applying.\n")

    launch_gui()