"""
gui/tabs/tab_monitoring.py  —  System Monitoring & Self-Healing
GET  run_self_healing_scan — finds auto-fixable issues
PUT  apply_self_heal — auto-fix one issue at a time
"""
from gui.tabs._base import *


class MonitoringTab(BaseTab):

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._issues = []
        self._build()
        self._scan()

    def _build(self):
        rf = self._page_header("System Monitoring", "📡",
                                "Auto-detect and self-heal SAP BO issues")
        ctk.CTkButton(rf, text="🔍 Scan Now", width=100, height=30,
                      fg_color=CYAN, text_color=BG0, font=F_SM,
                      command=self._scan).pack(side="right", padx=3)
        ctk.CTkButton(rf, text="🔧 Fix All Auto", width=120, height=30,
                      fg_color=GREEN, text_color="white", font=F_SM,
                      command=self._fix_all).pack(side="right", padx=3)

        body = self._body
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        tiles = ctk.CTkFrame(body, fg_color="transparent")
        tiles.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        self._t = {}
        for k, lbl, col, ico in [
            ("total",    "Total Issues", CYAN,  "📊"),
            ("critical", "Critical",     RED,   "🚨"),
            ("error",    "Errors",       RED,   "❌"),
            ("warning",  "Warnings",     AMBER, "⚠"),
            ("fixable",  "Auto-Fixable", GREEN, "🔧"),
        ]:
            c, v = stat_tile(tiles, lbl, "—", col, ico)
            c.pack(side="left", padx=(0, 8), fill="both", expand=True)
            self._t[k] = v

        # Health bar
        hbar = ctk.CTkFrame(body, fg_color=BG1, corner_radius=8)
        hbar.grid(row=1, column=0, sticky="ew", padx=14, pady=8)
        ctk.CTkLabel(hbar, text="System Health:",
                     font=F_SM, text_color=TEXT2).pack(side="left", padx=12, pady=8)
        self._health_bar = ctk.CTkProgressBar(hbar, height=16, corner_radius=8,
                                               fg_color=BG2, progress_color=GREEN)
        self._health_bar.pack(side="left", fill="x", expand=True, padx=8, pady=8)
        self._health_bar.set(1.0)
        self._health_lbl = ctk.CTkLabel(hbar, text="100%  Healthy",
                                         font=F_H3, text_color=GREEN)
        self._health_lbl.pack(side="right", padx=12)

        cols = [("sev","Severity",100),("type","Issue Type",160),
                ("obj","Object",200),("detail","Detail",250),("fix","Auto-Fix",90)]
        self._tree, tf = make_tree(body, cols)
        tf.grid(row=2, column=0, sticky="nsew", padx=14)

        act = ctk.CTkFrame(body, fg_color=BG1, corner_radius=0, height=42)
        act.grid(row=3, column=0, sticky="ew")
        act.pack_propagate(False)
        ctk.CTkButton(act, text="🔧 Fix Selected", width=120, height=30,
                      fg_color=BG2, hover_color=GREEN, text_color=TEXT, font=F_SM,
                      command=self._fix_selected).pack(side="left", padx=4, pady=6)
        ctk.CTkButton(act, text="🔍 Details", width=100, height=30,
                      fg_color=BG2, hover_color=BLUE, text_color=TEXT, font=F_SM,
                      command=self._show_details).pack(side="left", padx=4, pady=6)

    def _scan(self):
        self.set_status("⏳ Scanning SAP BO environment…", AMBER)
        bg(bo_session.run_self_healing_scan, self._on_scanned, self)

    def _on_scanned(self, issues):
        self._issues = issues or []
        crits   = sum(1 for i in self._issues if i.get("severity","").upper() == "CRITICAL")
        errs    = sum(1 for i in self._issues if i.get("severity","").upper() == "ERROR")
        warns   = sum(1 for i in self._issues if i.get("severity","").upper() == "WARNING")
        fixable = sum(1 for i in self._issues if i.get("auto_fix"))
        self._t["total"].configure(text=str(len(self._issues)))
        self._t["critical"].configure(text=str(crits))
        self._t["error"].configure(text=str(errs))
        self._t["warning"].configure(text=str(warns))
        self._t["fixable"].configure(text=str(fixable))

        # Health score
        if not self._issues:
            health = 1.0; color = GREEN; label = "100%  Healthy"
        elif crits > 0:
            health = max(0.05, 0.5 - crits * 0.1); color = RED
            label = f"{int(health*100)}%  Critical"
        elif errs > 0:
            health = max(0.3, 0.75 - errs * 0.05); color = AMBER
            label = f"{int(health*100)}%  Degraded"
        else:
            health = max(0.6, 0.9 - warns * 0.02); color = TEAL
            label = f"{int(health*100)}%  Warnings"
        self._health_bar.set(health)
        self._health_bar.configure(progress_color=color)
        self._health_lbl.configure(text=label, text_color=color)

        self._render()
        col = RED if crits else (AMBER if errs else GREEN)
        self.set_status(f"🔍 {len(self._issues)} issues  —  {crits} critical  {fixable} auto-fixable", col)

    def _render(self):
        for r in self._tree.get_children(): self._tree.delete(r)
        SEV_ICON = {"CRITICAL":"🚨","ERROR":"❌","WARNING":"⚠","INFO":"ℹ"}
        SEV_TAG  = {"CRITICAL":"crit","ERROR":"err","WARNING":"warn","INFO":"info"}
        for i, issue in enumerate(self._issues):
            sev  = issue.get("severity","").upper()
            icon = SEV_ICON.get(sev, "•")
            tag  = SEV_TAG.get(sev, "info")
            fix  = "✅ Yes" if issue.get("auto_fix") else "❌ No"
            self._tree.insert("", "end", iid=str(i), tags=(tag,),
                              values=(f"{icon} {sev}",
                                      issue.get("type","")[:30],
                                      str(issue.get("object",""))[:40],
                                      issue.get("detail","")[:50], fix))
        self._tree.tag_configure("crit", foreground=RED)
        self._tree.tag_configure("err",  foreground=RED)
        self._tree.tag_configure("warn", foreground=AMBER)
        self._tree.tag_configure("info", foreground=BLUE)

    def _fix_selected(self):
        sel = self._tree.selection()
        if not sel:
            show_info("Select Issue", "Select an issue to fix.", parent=self)
            return
        idx   = int(sel[0])
        issue = self._issues[idx]
        if not issue.get("auto_fix"):
            show_info("Not Auto-Fixable",
                      f"This issue requires manual intervention:\n\n{issue.get('detail','')}\n\n"
                      "Please use CMC or contact your BO admin.", parent=self)
            return
        if not confirm("Apply Fix",
                       f"Auto-fix:\n{issue.get('type','')} — {issue.get('object','')}\n\n"
                       f"Fix action: {issue.get('fix_action','')}", parent=self):
            return
        self.set_status(f"⏳ Applying fix…", AMBER)
        bg(lambda: bo_session.apply_self_heal(issue),
           lambda r: (
               self.set_status(f"✅ Fixed: {issue.get('type','')}" if r[0] else f"❌ Fix failed: {r[1][:60]}",
                               GREEN if r[0] else RED),
               self._scan()
           ), self)

    def _fix_all(self):
        fixable = [i for i in self._issues if i.get("auto_fix")]
        if not fixable:
            show_info("No Issues", "No auto-fixable issues found.", parent=self)
            return
        if not confirm("Fix All",
                       f"Auto-fix {len(fixable)} issue(s)?\n\n"
                       + "\n".join(f"• {i.get('type','')} — {i.get('object','')}" for i in fixable[:10]),
                       parent=self):
            return
        self.set_status(f"⏳ Fixing {len(fixable)} issues…", AMBER)
        def _run():
            ok = err = 0
            for issue in fixable:
                r, _ = bo_session.apply_self_heal(issue)
                if r: ok += 1
                else: err += 1
            return ok, err
        bg(_run, lambda r: (
            self.set_status(f"✅ Fixed: {r[0]}  ❌ Failed: {r[1]}", GREEN if r[1] == 0 else AMBER),
            self._scan()
        ), self)

    def _show_details(self):
        sel = self._tree.selection()
        if not sel: return
        issue = self._issues[int(sel[0])]
        msg   = "\n".join(f"{k}: {v}" for k, v in issue.items())
        show_info("Issue Details", msg, parent=self)
