"""
gui/tabs/tab_security.py  —  Security & Sessions
GET  active sessions, security scan
DEL  kill session (real REST call)
"""
from gui.tabs._base import *


class SecurityTab(BaseTab):

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._sessions = []
        self._scan_results = []
        self._mode = "sessions"
        self._build()
        self._load_sessions()

    def _build(self):
        rf = self._page_header("Security & Sessions", "🔐",
                                "Active sessions, security scan, anomaly detection")
        ctk.CTkButton(rf, text="⟳ Refresh", width=90, height=30,
                      fg_color=BG2, text_color=TEXT, font=F_SM,
                      command=self._refresh).pack(side="right", padx=3)
        ctk.CTkButton(rf, text="🔍 Security Scan", width=120, height=30,
                      fg_color=VIOLET, text_color="white", font=F_SM,
                      command=self._run_scan).pack(side="right", padx=3)

        body = self._body
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        # tiles
        tiles = ctk.CTkFrame(body, fg_color="transparent")
        tiles.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        self._t = {}
        for k, lbl, col, ico in [
            ("sessions", "Active Sessions", CYAN,   "👤"),
            ("issues",   "Security Issues", RED,    "⚠"),
            ("critical", "Critical",        RED,    "🚨"),
            ("warning",  "Warnings",        AMBER,  "⚠"),
        ]:
            c, v = stat_tile(tiles, lbl, "—", col, ico)
            c.pack(side="left", padx=(0, 8), fill="both", expand=True)
            self._t[k] = v

        # mode bar
        mbar = ctk.CTkFrame(body, fg_color=BG1, corner_radius=8, height=40)
        mbar.grid(row=1, column=0, sticky="ew", padx=14, pady=8)
        mbar.pack_propagate(False)
        self._s_btn = ctk.CTkButton(mbar, text="👤 Active Sessions", width=140, height=28,
                                     fg_color=BLUE, text_color="white", font=F_SM,
                                     command=lambda: self._set_mode("sessions"))
        self._s_btn.pack(side="left", padx=8, pady=6)
        self._sc_btn = ctk.CTkButton(mbar, text="🔍 Scan Results", width=120, height=28,
                                      fg_color=BG2, text_color=TEXT2, font=F_SM,
                                      command=lambda: self._set_mode("scan"))
        self._sc_btn.pack(side="left", padx=2, pady=6)
        self._q = ctk.StringVar()
        self._q.trace_add("write", lambda *_: self._render())
        ctk.CTkEntry(mbar, textvariable=self._q, placeholder_text="🔎 Filter…",
                     width=200, height=28, fg_color=BG2, border_color=BG2,
                     text_color=TEXT, font=F_SM).pack(side="left", padx=8)

        # sessions tree
        s_cols = [("user","User",160),("auth","Auth Type",110),
                   ("created","Connected Since",160),("desc","Description",200)]
        self._tree_s, tf_s = make_tree(body, s_cols)
        tf_s.grid(row=2, column=0, sticky="nsew", padx=14)
        self._tf_s = tf_s

        # scan tree
        sc_cols = [("sev","Severity",90),("type","Issue Type",160),
                    ("obj","Object",200),("detail","Detail",260)]
        self._tree_sc, tf_sc = make_tree(body, sc_cols)
        tf_sc.grid(row=2, column=0, sticky="nsew", padx=14)
        self._tf_sc = tf_sc
        tf_sc.grid_remove()

        # actions
        act = ctk.CTkFrame(body, fg_color=BG1, corner_radius=0, height=42)
        act.grid(row=3, column=0, sticky="ew")
        act.pack_propagate(False)
        ctk.CTkButton(act, text="🚫 Kill Session", width=120, height=30,
                      fg_color=BG2, hover_color=RED, text_color=TEXT, font=F_SM,
                      command=self._kill_session).pack(side="left", padx=4, pady=6)
        ctk.CTkButton(act, text="🔄 Auto-Fix Issue", width=130, height=30,
                      fg_color=BG2, hover_color=GREEN, text_color=TEXT, font=F_SM,
                      command=self._auto_fix).pack(side="left", padx=4, pady=6)

    def _refresh(self):
        if self._mode == "sessions":
            self._load_sessions()
        else:
            self._run_scan()

    def _set_mode(self, mode):
        self._mode = mode
        if mode == "sessions":
            self._s_btn.configure(fg_color=BLUE, text_color="white")
            self._sc_btn.configure(fg_color=BG2, text_color=TEXT2)
            self._tf_s.grid(); self._tf_sc.grid_remove()
        else:
            self._sc_btn.configure(fg_color=BLUE, text_color="white")
            self._s_btn.configure(fg_color=BG2, text_color=TEXT2)
            self._tf_sc.grid(); self._tf_s.grid_remove()
        self._render()

    def _load_sessions(self):
        self.set_status("⏳ Loading sessions…", AMBER)
        bg(bo_session.get_active_sessions, self._on_sessions, self)

    def _on_sessions(self, data):
        self._sessions = data or []
        self._t["sessions"].configure(text=str(len(self._sessions)))
        self._render()
        self.set_status(f"✅ {len(self._sessions)} active sessions", GREEN)

    def _run_scan(self):
        self.set_status("⏳ Running security scan…", AMBER)
        bg(bo_session.scan_security, self._on_scan, self)

    def _on_scan(self, data):
        self._scan_results = data or []
        crits = sum(1 for i in self._scan_results if i.get("severity","").upper() == "CRITICAL")
        warns = sum(1 for i in self._scan_results if i.get("severity","").upper() == "WARNING")
        self._t["issues"].configure(text=str(len(self._scan_results)))
        self._t["critical"].configure(text=str(crits))
        self._t["warning"].configure(text=str(warns))
        self._set_mode("scan")
        self.set_status(f"🔍 {len(self._scan_results)} issues — {crits} critical", RED if crits else AMBER)

    def _render(self):
        q = self._q.get().lower()
        if self._mode == "sessions":
            for r in self._tree_s.get_children(): self._tree_s.delete(r)
            for s in self._sessions:
                user = s.get("user","")
                if q and q not in user.lower(): continue
                self._tree_s.insert("", "end", iid=str(s.get("id","")),
                                    values=(user, s.get("auth_type",""),
                                            str(s.get("created",""))[:19],
                                            s.get("description","")))
        else:
            for r in self._tree_sc.get_children(): self._tree_sc.delete(r)
            for i, issue in enumerate(self._scan_results):
                sev = issue.get("severity","").upper()
                col_tag = "crit" if sev == "CRITICAL" else ("warn" if sev == "WARNING" else "info")
                if q and q not in str(issue).lower(): continue
                icon = "🚨" if sev == "CRITICAL" else ("⚠" if sev == "WARNING" else "ℹ")
                self._tree_sc.insert("", "end", iid=str(i), tags=(col_tag,),
                                     values=(f"{icon} {sev}",
                                             issue.get("type",""),
                                             issue.get("object","")[:40],
                                             issue.get("detail","")[:60]))
            self._tree_sc.tag_configure("crit", foreground=RED)
            self._tree_sc.tag_configure("warn", foreground=AMBER)
            self._tree_sc.tag_configure("info", foreground=BLUE)

    def _kill_session(self):
        if self._mode != "sessions": return
        sel = self._tree_s.selection()
        if not sel:
            show_info("Select Session", "Select a session to kill.", parent=self)
            return
        sid  = sel[0]
        user = self._tree_s.item(sid)["values"][0]
        if not confirm("Kill Session", f"Kill session for: {user}?", parent=self):
            return
        self.set_status(f"⏳ Killing session {user}…", AMBER)
        bg(lambda: bo_session.kill_session(sid),
           lambda r: (self._handle_write(r, f"Session killed: {user}"),
                      self._load_sessions()), self)

    def _auto_fix(self):
        if self._mode != "scan": return
        sel = self._tree_sc.selection()
        if not sel:
            show_info("Select Issue", "Select a scan issue to auto-fix.", parent=self)
            return
        idx  = int(sel[0])
        issue = self._scan_results[idx]
        if not issue.get("auto_fix"):
            show_info("Not Auto-Fixable", f"This issue requires manual intervention:\n{issue.get('detail','')}", parent=self)
            return
        if not confirm("Auto-Fix", f"Apply auto-fix to:\n{issue.get('type','')} — {issue.get('object','')}?", parent=self):
            return
        self.set_status("⏳ Applying fix…", AMBER)
        bg(lambda: bo_session.apply_self_heal(issue),
           lambda r: self._handle_write(r, f"Fixed: {issue.get('type','')}"), self)

    def _handle_write(self, r, ok_msg):
        ok  = r[0] if isinstance(r, tuple) else bool(r)
        msg = r[1] if isinstance(r, tuple) and len(r) > 1 else ""
        if ok:
            self.set_status(f"✅ {ok_msg}", GREEN)
        else:
            self.set_status(f"❌ {msg[:80]}", RED)
            show_error("Failed", msg, parent=self)
