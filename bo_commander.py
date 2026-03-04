"""
bo_commander.py  -  BO Commander v1.0.0
Intelligent SAP BusinessObjects Control Center

Developed by : Sai Teja Guddanti
Contact      : saitejaguddanti999@gmail.com
LinkedIn     : https://www.linkedin.com/in/sai-teja-628082288

Single-file entry point. No external license_manager or license_dialog needed.
Banner + license check + activation dialog are all embedded in this file.
"""
import sys, os, json, threading, hashlib, platform, socket, webbrowser
from datetime import date, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------
MASTER_KEY   = "BOCMD-25STG-ADMIN-XKEY9"   # the key you give to users
WEB_PORT     = 8765
AUTO_BROWSER = False
DOCS_DIR     = Path(__file__).parent / "docs"

DEV_NAME     = "Sai Teja Guddanti"
DEV_EMAIL    = "saitejaguddanti999@gmail.com"
DEV_LINKEDIN = "https://www.linkedin.com/in/sai-teja-628082288"
VERSION      = "1.0.0"
LICENSE_FILE = Path.home() / ".bocommander" / "license.json"


# ---------------------------------------------------------------------------
# LICENSE  (inline, no external module)
# ---------------------------------------------------------------------------

def _lic_load():
    try:
        if LICENSE_FILE.exists():
            return json.loads(LICENSE_FILE.read_text())
    except Exception:
        pass
    return {}


def _lic_save(data):
    try:
        LICENSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        LICENSE_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def _validate_key(key):
    clean = key.strip().upper().replace("-", "")
    return clean == MASTER_KEY.upper().replace("-", "")


def is_activated():
    """Returns (activated: bool, user_name: str)"""
    d = _lic_load()
    return d.get("activated", False), d.get("user_name", "")


def _do_activate(user_name, entered_key):
    """Returns (success: bool, message: str)"""
    if not _validate_key(entered_key):
        return False, ("Invalid license key.\n\n"
                       "Please contact the developer to get a valid key:\n"
                       + DEV_EMAIL)
    _lic_save({
        "activated":    True,
        "user_name":    user_name.strip() or "Unknown",
        "key":          entered_key.strip().upper(),
        "activated_on": str(date.today()),
        "version":      VERSION,
    })
    return True, "License activated! Welcome, " + user_name.strip() + "."


# ---------------------------------------------------------------------------
# BANNER
# ---------------------------------------------------------------------------

def _print_banner(activated=False, user_name=""):
    CY = "\033[96m"; BL = "\033[94m"; GR = "\033[92m"
    YL = "\033[93m"; WH = "\033[97m"; GY = "\033[90m"
    BD = "\033[1m";  RS = "\033[0m"
    SEP = GY + "-" * 98 + RS
    print()
    print(CY + BD)
    print("  BO COMMANDER  v" + VERSION + "  |  Intelligent SAP BusinessObjects Control Center")
    print("  AI-Powered Administration, Monitoring, Diagnostics, Security, Housekeeping")
    print(RS)
    print(SEP)
    print()
    print("  " + YL + BD + "Developed by:" + RS)
    print("    " + WH + BD + DEV_NAME + RS)
    print("    " + BL + "Email    : " + DEV_EMAIL + RS)
    print("    " + CY + "LinkedIn : " + DEV_LINKEDIN + RS)
    print("    " + GY + "(c) 2025 " + DEV_NAME + ". All rights reserved." + RS)
    print()
    print("  " + YL + BD + "License:" + RS)
    if activated and user_name:
        print("    " + GR + "ACTIVATED  -  registered to: " + WH + BD + user_name + RS)
    else:
        print("    " + YL + "Trial Mode  -  activate when prompted" + RS)
    print()
    print("  " + YL + BD + "System:" + RS)
    print("    " + GY + "OS   : " + WH + platform.system() + " " + platform.release() + RS)
    print("    " + GY + "Host : " + WH + socket.gethostname() + RS)
    print("    " + GY + "Time : " + WH + datetime.now().strftime("%Y-%m-%d  %H:%M:%S") + RS)
    print()
    print(SEP)
    print("  " + CY + "  Loading GUI ..." + RS)
    print("  " + BL + "  Product info : http://localhost:" + str(WEB_PORT) + RS)
    print("  " + YL + "  AI may make mistakes - always verify critical actions." + RS)
    print(SEP)
    print()


# ---------------------------------------------------------------------------
# LICENSE DIALOG  (inline CTk dialog, no external module)
# ---------------------------------------------------------------------------

def _show_license_dialog():
    """
    Shows license activation dialog.
    Returns (activated: bool, user_name: str).
    Calls sys.exit(0) if user closes without activating.
    """
    import customtkinter as ctk

    C_BG   = "#080e17"
    C_BG2  = "#0d1824"
    C_BORD = "#1a2e42"
    C_CYN  = "#22d3ee"
    C_RED  = "#ef4444"
    C_GRY  = "#8fafc8"
    C_WHT  = "#e2eaf4"

    result = {"ok": False, "name": ""}
    closed = {"v": False}

    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.withdraw()

    dlg = ctk.CTkToplevel(root)
    dlg.title("BO Commander - License Activation")
    dlg.geometry("520x630")
    dlg.resizable(False, False)
    dlg.configure(fg_color=C_BG)
    dlg.grab_set()
    dlg.lift()
    dlg.focus_force()

    def _on_close():
        closed["v"] = True
        root.quit()
    dlg.protocol("WM_DELETE_WINDOW", _on_close)

    dlg.update_idletasks()
    sw = dlg.winfo_screenwidth()
    sh = dlg.winfo_screenheight()
    dlg.geometry("520x630+" + str((sw-520)//2) + "+" + str((sh-630)//2))

    P = {"padx": 40}

    ctk.CTkLabel(dlg, text="BO Commander",
                 font=("Courier New", 28, "bold"),
                 text_color=C_CYN).pack(pady=(38, 4))
    ctk.CTkLabel(dlg, text="v" + VERSION + "  |  Intelligent SAP BO Control Center",
                 font=("Segoe UI", 12), text_color=C_GRY).pack()

    ctk.CTkFrame(dlg, height=1, fg_color=C_BORD).pack(fill="x", padx=40, pady=22)

    ctk.CTkLabel(dlg, text="License Activation",
                 font=("Segoe UI", 16, "bold"),
                 text_color=C_WHT).pack(**P, anchor="w")
    ctk.CTkLabel(dlg,
                 text="Enter the license key provided by the developer.",
                 font=("Segoe UI", 12), text_color=C_GRY,
                 justify="left").pack(**P, anchor="w", pady=(4, 0))

    ctk.CTkLabel(dlg, text="Your Name",
                 font=("Segoe UI", 12), text_color=C_GRY).pack(**P, anchor="w", pady=(18, 0))
    name_e = ctk.CTkEntry(dlg, height=42, placeholder_text="e.g. John Smith",
                           font=("Segoe UI", 13),
                           fg_color=C_BG2, border_color=C_BORD, text_color=C_WHT)
    name_e.pack(fill="x", **P, pady=(4, 0))

    ctk.CTkLabel(dlg, text="License Key",
                 font=("Segoe UI", 12), text_color=C_GRY).pack(**P, anchor="w", pady=(14, 0))
    key_e = ctk.CTkEntry(dlg, height=42,
                          placeholder_text="BOCMD-XXXXX-XXXXX-XXXXX",
                          font=("Courier New", 14),
                          fg_color=C_BG2, border_color=C_BORD, text_color=C_CYN)
    key_e.pack(fill="x", **P, pady=(4, 0))

    msg_lbl = ctk.CTkLabel(dlg, text="", font=("Segoe UI", 11),
                            text_color=C_RED, wraplength=440, justify="left")
    msg_lbl.pack(**P, anchor="w", pady=(8, 0))

    def _submit():
        name = name_e.get().strip()
        key  = key_e.get().strip()
        if not key:
            msg_lbl.configure(text="Please enter your license key.", text_color=C_RED)
            return
        if not name:
            msg_lbl.configure(text="Please enter your name.", text_color=C_RED)
            return
        btn.configure(state="disabled", text="Validating...")
        dlg.update()
        ok, msg = _do_activate(name, key)
        if ok:
            result["ok"]   = True
            result["name"] = name
            msg_lbl.configure(text="Activated! Loading...", text_color="#22c55e")
            btn.configure(text="Activated!")
            dlg.after(900, root.quit)
        else:
            msg_lbl.configure(text=msg, text_color=C_RED)
            btn.configure(state="normal", text="Activate BO Commander")

    key_e.bind("<Return>", lambda e: _submit())

    btn = ctk.CTkButton(dlg, text="Activate BO Commander",
                         height=46, corner_radius=8,
                         font=("Segoe UI", 14, "bold"),
                         fg_color=C_CYN, text_color=C_BG,
                         hover_color="#06b6d4",
                         command=_submit)
    btn.pack(fill="x", **P, pady=(14, 0))

    ctk.CTkFrame(dlg, height=1, fg_color=C_BORD).pack(fill="x", padx=40, pady=18)

    ctk.CTkLabel(dlg, text="No key?  Contact the developer:",
                 font=("Segoe UI", 11), text_color=C_GRY).pack()
    ctk.CTkLabel(dlg, text=DEV_EMAIL,
                 font=("Segoe UI", 12, "bold"), text_color=C_CYN).pack(pady=(2, 0))
    ctk.CTkLabel(dlg, text=DEV_LINKEDIN,
                 font=("Segoe UI", 11), text_color=C_GRY).pack(pady=(2, 10))

    root.mainloop()

    if closed["v"] or not result["ok"]:
        print("\nActivation cancelled. Exiting.")
        sys.exit(0)

    try:
        root.destroy()
    except Exception:
        pass

    return result["ok"], result["name"]


# ---------------------------------------------------------------------------
# WEB SERVER
# ---------------------------------------------------------------------------
def _start_web_server():
    """Serve the docs folder on localhost:WEB_PORT in a daemon thread."""
    import http.server, socketserver, os
    if not DOCS_DIR.exists():
        return

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(DOCS_DIR), **kwargs)
        def log_message(self, fmt, *args):
            pass  # Suppress HTTP access logs

    def _serve():
        try:
            with socketserver.TCPServer(("", WEB_PORT), _Handler) as httpd:
                httpd.serve_forever()
        except OSError:
            pass  # Port already in use — ignore

    threading.Thread(target=_serve, daemon=True).start()


# ── GUI bootstrap ─────────────────────────────────────────────────────────────


# ---------------------------------------------------------------------------
# GUI  (all pages - unchanged)
# ---------------------------------------------------------------------------
def launch_gui():
    import customtkinter as ctk
    import ctypes
    from config import Config
    from gui.pages.login import LoginPage
    from core.sapbo_connection import bo_session
    from core.monitoring import SystemMonitor
    from ai.sentinel_agent import SentinelAgent
    from gui.pages.dashboard             import DashboardPage
    from gui.pages.users                 import UsersPage
    from gui.pages.servers               import ServersPage
    from gui.pages.reports               import ReportsPage
    from gui.pages.audit                 import AuditPage
    from gui.pages.folders               import FoldersPage
    from gui.pages.bulk_ops              import BulkOpsPage
    from gui.pages.universes             import UniversesPage
    from gui.pages.connections           import ConnectionsPage
    from gui.pages.instance_manager      import InstanceManagerPage
    from gui.pages.authentication        import AuthenticationPage
    from gui.pages.license_keys          import LicenseKeysPage
    from gui.pages.promotion             import PromotionPage
    from gui.pages.versioning            import VersioningPage
    from gui.pages.scheduling            import SchedulingPage
    from gui.pages.publishing            import PublishingPage
    from gui.pages.sessions              import SessionsPage
    from gui.pages.log_analyzer          import LogAnalyzerPage
    from gui.pages.sentinel              import SentinelPage
    from gui.pages.settings              import SettingsPage
    from gui.pages.report_viewer         import ReportViewerPage
    from gui.pages.system_monitor        import SystemMonitorPage
    from gui.pages.security_analyzer     import SecurityAnalyzerPage
    from gui.pages.cleanup_hub           import CleanupHubPage
    from gui.pages.query_builder         import QueryBuilderPage
    from gui.pages.dependency_resolver   import DependencyResolverPage
    from gui.pages.instance_cleanup      import InstanceCleanupPage
    from gui.pages.failed_schedules      import FailedSchedulesPage
    from gui.pages.user_activity         import UserActivityPage
    from gui.pages.server_health         import ServerHealthPage
    from gui.pages.broken_reports        import BrokenReportsPage
    from gui.pages.housekeeping          import HousekeepingPage
    from gui.pages.ai_assistant          import AIAssistantPage
    from gui.pages.applications          import ApplicationsPage
    from gui.pages.broken_objects        import BrokenObjectsPage
    from gui.pages.deep_search           import DeepSearchPage
    from gui.pages.health_heatmap        import HealthHeatmapPage
    from gui.pages.impact_analysis       import ImpactAnalysisPage
    from gui.pages.instance_deep_control import InstanceDeepControlPage
    from gui.pages.log_correlation       import LogCorrelationPage
    from gui.pages.metadata_view         import MetadataViewPage
    from gui.pages.notifications         import NotificationsPage
    from gui.pages.olap_connections      import OLAPConnectionsPage
    from gui.pages.promotion_resolver    import PromotionResolverPage
    from gui.pages.recycle_bin           import RecycleBinPage
    from gui.pages.report_interaction    import ReportInteractionPage
    from gui.pages.self_healing          import SelfHealingPage
    from gui.pages.services              import ServicesPage
    from gui.pages.web_services          import WebServicesPage
    from gui.pages.sso_tester            import SSOTesterPage
    from gui.pages.ldap_sync_monitor     import LDAPSyncMonitorPage
    from gui.pages.repository_diagnostic import RepositoryDiagnosticPage

    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    class BOCommanderApp(ctk.CTk):
        def __init__(self):
            super().__init__()
            self.monitor  = None
            self.sentinel = SentinelAgent(ui_callback=self.refresh_sentinel_page)
            self.title(f"{Config.APP_NAME} v{Config.VERSION}")
            self.geometry("1450x950")
            self.minsize(1100, 750)
            self.protocol("WM_DELETE_WINDOW", self.on_close)
            self.show_login()

        def on_close(self):
            if self.monitor: self.monitor.stop()
            self.destroy()

        def show_login(self):
            for w in self.winfo_children(): w.destroy()
            self.login_page = LoginPage(self, self.on_login_success, self.sentinel)

        def on_login_success(self):
            self.login_page.destroy()
            self.grid_rowconfigure(0, weight=1)
            self.grid_columnconfigure(1, weight=1)
            self.setup_sidebar()
            self.setup_main_area()
            self.update_connection_status()
            self.monitor = SystemMonitor(self.sentinel)
            self.monitor.start()
            self.select_page("Dashboard")

        def refresh_sentinel_page(self):
            if hasattr(self, "page_title") and self.page_title.cget("text") == "AI Sentinel":
                self.select_page("AI Sentinel")

        def setup_sidebar(self):
            self.sidebar_frame = ctk.CTkScrollableFrame(
                self, width=260, corner_radius=0,
                fg_color=Config.COLORS["bg_secondary"])
            self.sidebar_frame.grid(row=0, column=0, sticky="nsew")

            ctk.CTkLabel(self.sidebar_frame, text=Config.APP_NAME,
                         font=Config.FONTS["header"]).pack(pady=(25, 5))
            ctk.CTkLabel(self.sidebar_frame, text=Config.TAGLINE,
                         font=Config.FONTS["small"],
                         text_color=Config.COLORS["text_secondary"]).pack(pady=(0, 20))

            self.nav_buttons = {}
            menus = [
                "Dashboard", "AI Sentinel", "\U0001f514 Notifications",
                "--- AI TOOLS ---",
                "AI Assistant", "Self Healing", "Health Heatmap",
                "--- POWER TOOLS ---",
                "Security Scanner", "\U0001f5a5  System Monitor", "Orphan Purge",
                "Query Builder", "Dep. Resolver", "Instance Cleanup",
                "Failed Schedules", "User Activity", "Server Health",
                "Broken Reports", "Housekeeping", "Broken Objects",
                "Deep Search", "Impact Analysis", "Log Correlation",
                "Instance Deep Control", "Promotion Resolver",
                "--- DIAGNOSTICS ---",
                "SSO Tester", "LDAP Sync Monitor", "Repo Diagnostic",
                "--- CMC TABS ---",
                "Users", "Sessions", "Servers", "Folders", "Reports",
                "Report Viewer", "Report Interaction", "Universes",
                "Connections", "OLAP Connections", "Instance Manager",
                "Bulk Ops", "Log Analyzer", "Scheduling", "Promotion",
                "Versioning", "Publishing", "Authentication", "Licenses",
                "Audit", "Applications", "Services", "Web Services",
                "Recycle Bin", "Metadata View", "Settings",
            ]
            for m in menus:
                if m.startswith("---"):
                    ctk.CTkLabel(self.sidebar_frame, text=m,
                                 font=("Segoe UI", 10, "bold"),
                                 text_color="gray").pack(pady=(15, 5))
                    continue
                btn = ctk.CTkButton(
                    self.sidebar_frame, text=m, height=38, corner_radius=8,
                    fg_color="transparent",
                    text_color=Config.COLORS["text_secondary"],
                    hover_color=Config.COLORS["bg_tertiary"],
                    anchor="w",
                    command=lambda x=m: self.select_page(x))
                btn.pack(fill="x", padx=15, pady=2)
                self.nav_buttons[m] = btn

            ctk.CTkButton(self.sidebar_frame, text="Log Out",
                          fg_color=Config.COLORS["danger"],
                          hover_color="#DC2626",
                          command=self.logout).pack(pady=40, padx=20)

        def setup_main_area(self):
            self.main_frame = ctk.CTkFrame(self, corner_radius=0,
                                           fg_color=Config.COLORS["bg_primary"])
            self.main_frame.grid(row=0, column=1, sticky="nsew")
            top_bar = ctk.CTkFrame(self.main_frame, height=70, fg_color="transparent")
            top_bar.pack(side="top", fill="x", padx=35, pady=25)
            self.page_title = ctk.CTkLabel(top_bar, text="Dashboard",
                                           font=Config.FONTS["sub_header"],
                                           text_color=Config.COLORS["text_primary"])
            self.page_title.pack(side="left")
            self.conn_status = ctk.CTkLabel(top_bar, text="\u25cf Connected",
                                            font=Config.FONTS["small"],
                                            text_color=Config.COLORS["success"])
            self.conn_status.pack(side="right")
            self.content_area = ctk.CTkFrame(self.main_frame, fg_color="transparent")
            self.content_area.pack(side="top", fill="both", expand=True, padx=35, pady=5)

        def select_page(self, page_name):
            for name, btn in self.nav_buttons.items():
                btn.configure(fg_color="transparent",
                               text_color=Config.COLORS["text_secondary"])
            if page_name in self.nav_buttons:
                self.nav_buttons[page_name].configure(
                    fg_color=Config.COLORS["bg_tertiary"],
                    text_color=Config.COLORS["primary"])
            self.page_title.configure(text=page_name)
            for w in self.content_area.winfo_children(): w.destroy()

            pages = {
                "Dashboard":              lambda: DashboardPage(self.content_area),
                "AI Sentinel":            lambda: SentinelPage(self.content_area, agent=self.sentinel),
                "\U0001f514 Notifications": lambda: NotificationsPage(self.content_area),
                "AI Assistant":           lambda: AIAssistantPage(self.content_area),
                "Self Healing":           lambda: SelfHealingPage(self.content_area),
                "Health Heatmap":         lambda: HealthHeatmapPage(self.content_area),
                "Security Scanner":       lambda: SecurityAnalyzerPage(self.content_area),
                "\U0001f5a5  System Monitor": lambda: SystemMonitorPage(self.content_area),
                "Orphan Purge":           lambda: CleanupHubPage(self.content_area),
                "Query Builder":          lambda: QueryBuilderPage(self.content_area),
                "Dep. Resolver":          lambda: DependencyResolverPage(self.content_area),
                "Instance Cleanup":       lambda: InstanceCleanupPage(self.content_area),
                "Failed Schedules":       lambda: FailedSchedulesPage(self.content_area),
                "User Activity":          lambda: UserActivityPage(self.content_area),
                "Server Health":          lambda: ServerHealthPage(self.content_area),
                "Broken Reports":         lambda: BrokenReportsPage(self.content_area),
                "Housekeeping":           lambda: HousekeepingPage(self.content_area),
                "Broken Objects":         lambda: BrokenObjectsPage(self.content_area),
                "Deep Search":            lambda: DeepSearchPage(self.content_area),
                "Impact Analysis":        lambda: ImpactAnalysisPage(self.content_area),
                "Log Correlation":        lambda: LogCorrelationPage(self.content_area),
                "Instance Deep Control":  lambda: InstanceDeepControlPage(self.content_area),
                "Promotion Resolver":     lambda: PromotionResolverPage(self.content_area),
                "SSO Tester":             lambda: SSOTesterPage(self.content_area),
                "LDAP Sync Monitor":      lambda: LDAPSyncMonitorPage(self.content_area),
                "Repo Diagnostic":        lambda: RepositoryDiagnosticPage(self.content_area),
                "Users":                  lambda: UsersPage(self.content_area),
                "Sessions":               lambda: SessionsPage(self.content_area),
                "Servers":                lambda: ServersPage(self.content_area),
                "Folders":                lambda: FoldersPage(self.content_area),
                "Reports":                lambda: ReportsPage(self.content_area),
                "Report Viewer":          lambda: ReportViewerPage(self.content_area),
                "Report Interaction":     lambda: ReportInteractionPage(self.content_area),
                "Universes":              lambda: UniversesPage(self.content_area),
                "Connections":            lambda: ConnectionsPage(self.content_area),
                "OLAP Connections":       lambda: OLAPConnectionsPage(self.content_area),
                "Instance Manager":       lambda: InstanceManagerPage(self.content_area),
                "Bulk Ops":               lambda: BulkOpsPage(self.content_area),
                "Log Analyzer":           lambda: LogAnalyzerPage(self.content_area),
                "Scheduling":             lambda: SchedulingPage(self.content_area),
                "Promotion":              lambda: PromotionPage(self.content_area),
                "Versioning":             lambda: VersioningPage(self.content_area),
                "Publishing":             lambda: PublishingPage(self.content_area),
                "Authentication":         lambda: AuthenticationPage(self.content_area),
                "Licenses":               lambda: LicenseKeysPage(self.content_area),
                "Audit":                  lambda: AuditPage(self.content_area),
                "Applications":           lambda: ApplicationsPage(self.content_area),
                "Services":               lambda: ServicesPage(self.content_area),
                "Web Services":           lambda: WebServicesPage(self.content_area),
                "Recycle Bin":            lambda: RecycleBinPage(self.content_area),
                "Metadata View":          lambda: MetadataViewPage(self.content_area),
                "Settings":               lambda: SettingsPage(self.content_area),
            }
            builder = pages.get(page_name)
            if builder:
                builder().pack(fill="both", expand=True)
            else:
                ctk.CTkLabel(self.content_area,
                             text=f"{page_name} — Coming Soon",
                             font=Config.FONTS["header"]).pack(expand=True)

        def update_connection_status(self):
            if bo_session.connected:
                host = bo_session.cms_details.get("host", "Unknown")
                user = bo_session.cms_details.get("user", "Unknown")
                self.conn_status.configure(
                    text=f"\u25cf Connected to {host} ({user})",
                    text_color=Config.COLORS["success"])
            else:
                self.conn_status.configure(text="\u25cf Disconnected",
                                           text_color=Config.COLORS["danger"])

        def logout(self):
            if self.monitor: self.monitor.stop()
            bo_session.logout()
            self.show_login()

    app = BOCommanderApp()
    app.mainloop()


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------
if __name__ == "__main__":

    # 1. Check saved activation
    activated, user_name = is_activated()

    # 2. If not activated, show dialog
    if not activated:
        activated, user_name = _show_license_dialog()

    # 3. Print banner
    _print_banner(activated=activated, user_name=user_name)

    # 4. Start docs web server
    _start_web_server()

    # 5. Auto-browser (optional)
    if AUTO_BROWSER:
        threading.Timer(1.5, lambda: webbrowser.open("http://localhost:" + str(WEB_PORT))).start()

    # 6. Launch GUI
    launch_gui()