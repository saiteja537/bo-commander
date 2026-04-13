"""
gui/tabs/tab_dashboard.py  —  Dashboard (Live Stats)
Real data from bo_session.get_dashboard_stats(), auto-refreshes every 30s.
"""
import time
import threading
from gui.tabs._base import *


class DashboardTab(BaseTab):

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._stats = {}
        self._auto  = True
        self._build()
        self._load()

    def _build(self):
        rf = self._page_header("Dashboard", "🏠", "Live SAP BO environment health")
        ctk.CTkButton(rf, text="⟳ Refresh", width=90, height=30,
                      fg_color=BG2, text_color=TEXT, font=F_SM,
                      command=self._load).pack(side="right", padx=3)
        self._auto_lbl = ctk.CTkLabel(rf, text="🔄 Auto-refresh ON",
                                       font=F_XS, text_color=GREEN)
        self._auto_lbl.pack(side="right", padx=8)

        body = self._body
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        # ── Top KPI tiles ─────────────────────────────────────────────────────
        kpi_row = ctk.CTkFrame(body, fg_color="transparent")
        kpi_row.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 0))
        self._kpi = {}
        for k, lbl, col, ico in [
            ("servers_running", "Servers Running",  GREEN,  "🖥"),
            ("servers_total",   "Total Servers",    CYAN,   "🖧"),
            ("reports",         "Reports",          BLUE,   "📊"),
            ("users",           "Users",            VIOLET, "👥"),
            ("failed_instances","Failed Instances", RED,    "❌"),
            ("instances_today", "Runs Today",       TEAL,   "📅"),
        ]:
            c, v = stat_tile(kpi_row, lbl, "…", col, ico)
            c.pack(side="left", padx=(0, 8), fill="both", expand=True)
            self._kpi[k] = v

        # ── Servers list + health panel ───────────────────────────────────────
        mid = ctk.CTkFrame(body, fg_color="transparent")
        mid.grid(row=1, column=0, sticky="ew", padx=14, pady=10)
        mid.grid_columnconfigure(0, weight=3)
        mid.grid_columnconfigure(1, weight=1)

        # Server cards panel
        srv_outer = ctk.CTkFrame(mid, fg_color=BG1, corner_radius=10)
        srv_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(srv_outer, text="🖥  Server Status",
                     font=F_H3, text_color=CYAN).pack(anchor="w", padx=12, pady=(10, 4))
        ctk.CTkFrame(srv_outer, fg_color=BG2, height=1).pack(fill="x", padx=8)
        self._srv_scroll = ctk.CTkScrollableFrame(srv_outer, fg_color="transparent",
                                                    height=200)
        self._srv_scroll.pack(fill="both", expand=True, padx=8, pady=4)

        # Health summary panel
        health_panel = ctk.CTkFrame(mid, fg_color=BG1, corner_radius=10)
        health_panel.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(health_panel, text="📡  Health",
                     font=F_H3, text_color=CYAN).pack(anchor="w", padx=12, pady=(10, 4))
        ctk.CTkFrame(health_panel, fg_color=BG2, height=1).pack(fill="x", padx=8)
        self._health_f = ctk.CTkFrame(health_panel, fg_color="transparent")
        self._health_f.pack(fill="both", expand=True, padx=8, pady=4)

        # ── Recent activity ───────────────────────────────────────────────────
        act_frame = ctk.CTkFrame(body, fg_color=BG1, corner_radius=10)
        act_frame.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 10))
        act_frame.grid_columnconfigure(0, weight=1)
        act_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(act_frame, text="📋  Recent Instances (Today)",
                     font=F_H3, text_color=CYAN).grid(row=0, column=0,
                                                        sticky="w", padx=12, pady=(10, 4))
        cols = [("status","Status",110),("name","Report",260),
                ("owner","Owner",110),("start","Started",150),("kind","Type",80)]
        self._inst_tree, tf = make_tree(act_frame, cols, multi=False)
        tf.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

    # ── Data ──────────────────────────────────────────────────────────────────
    def _load(self):
        self.set_status("⏳ Loading dashboard…", AMBER)
        bg(lambda: (bo_session.get_dashboard_stats(),
                    bo_session.get_instances(status=None, limit=50)),
           self._on_loaded, self)

    def _on_loaded(self, result):
        if not result:
            self.set_status("❌ Failed to load", RED)
            return
        stats, instances = result
        self._stats = stats or {}
        self._render_kpi()
        self._render_servers()
        self._render_health()
        self._render_instances(instances or [])
        ts = time.strftime("%H:%M:%S")
        self.set_status(f"✅ Updated at {ts}", GREEN, f"Next refresh in 30s")
        # Auto-refresh every 30s
        self.after(30000, self._auto_refresh)

    def _auto_refresh(self):
        if self._auto:
            self._load()

    def _render_kpi(self):
        s = self._stats
        for k, v in self._kpi.items():
            val = s.get(k, "—")
            v.configure(text=str(val))

    def _render_servers(self):
        for w in self._srv_scroll.winfo_children():
            w.destroy()
        servers = self._stats.get("server_list", [])
        if not servers:
            ctk.CTkLabel(self._srv_scroll, text="No server data available",
                         font=F_SM, text_color=TEXT2).pack()
            return
        for srv in servers[:30]:
            row = ctk.CTkFrame(self._srv_scroll, fg_color=BG2, corner_radius=6)
            row.pack(fill="x", pady=2)
            col  = GREEN if srv.get("status") == "Running" else RED
            icon = "●" if srv.get("status") == "Running" else "○"
            ctk.CTkLabel(row, text=icon, font=F_SM,
                         text_color=col, width=18).pack(side="left", padx=(8, 4))
            ctk.CTkLabel(row,
                         text=str(srv.get("name",""))[:50],
                         font=F_SM, text_color=TEXT,
                         anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text=str(srv.get("status","")),
                         font=F_XS, text_color=col,
                         width=70).pack(side="right", padx=8)

    def _render_health(self):
        for w in self._health_f.winfo_children():
            w.destroy()
        s = self._stats
        total   = max(s.get("servers_total", 1), 1)
        running = s.get("servers_running", 0)
        failed  = s.get("failed_instances", 0)
        health  = int(running / total * 100)
        col     = GREEN if health >= 80 else (AMBER if health >= 50 else RED)
        label   = "Healthy" if health >= 80 else ("Degraded" if health >= 50 else "Critical")

        ctk.CTkLabel(self._health_f, text=f"{health}%",
                     font=("Segoe UI", 32, "bold"), text_color=col).pack(pady=(10, 0))
        ctk.CTkLabel(self._health_f, text=label,
                     font=F_H3, text_color=col).pack()
        ctk.CTkProgressBar(self._health_f, height=8, fg_color=BG2,
                            progress_color=col).pack(fill="x", padx=10, pady=6)

        for lbl, val, c in [("Universes", s.get("universes","—"), BLUE),
                              ("Connections", s.get("connections","—"), TEAL),
                              ("Failed Today", failed, RED if failed > 0 else TEXT2)]:
            row = ctk.CTkFrame(self._health_f, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=2)
            ctk.CTkLabel(row, text=lbl, font=F_XS,
                         text_color=TEXT2, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=str(val), font=(F_XS[0], F_XS[1], "bold"),
                         text_color=c).pack(side="right")

    def _render_instances(self, instances):
        for r in self._inst_tree.get_children():
            self._inst_tree.delete(r)
        STATUS_MAP = {"Success":"✅ Success","Failed":"❌ Failed",
                      "Running":"⏳ Running","Pending":"⏸ Pending"}
        STATUS_TAG = {"Success":"ok","Failed":"fail","Running":"run","Pending":"pend"}
        for inst in (instances or [])[:100]:
            st  = str(inst.get("status",""))
            tag = STATUS_TAG.get(st, "")
            self._inst_tree.insert("", "end", tags=(tag,),
                                   values=(STATUS_MAP.get(st, st),
                                           str(inst.get("name",""))[:50],
                                           inst.get("owner",""),
                                           str(inst.get("start_time",""))[:19],
                                           inst.get("kind","")))
        self._inst_tree.tag_configure("ok",   foreground=GREEN)
        self._inst_tree.tag_configure("fail", foreground=RED)
        self._inst_tree.tag_configure("run",  foreground=AMBER)
        self._inst_tree.tag_configure("pend", foreground=TEXT2)
