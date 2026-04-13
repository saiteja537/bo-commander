"""
gui/tabs/tab_servers.py  —  Servers  (Java Admin SDK integrated)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

What changed vs the original:
  NEW  Start / Stop / Restart via Java Admin SDK bridge
       (bridges/java_admin_sdk.py → bridges/ServerManager.jar)
  NEW  SDK status badge in the header — green when connected, amber when not
  NEW  📁 Setup SDK wizard button shows step-by-step JAR setup instructions
  NEW  Action buttons are ENABLED when bridge is available, disabled otherwise
  NEW  Auto-refresh toggle (30-second interval)
  NEW  KB snapshot saved after every load (for history / trend analysis)
  KEPT All existing REST-API read behaviour unchanged
  KEPT "Open CMC" as always-available fallback

Drop-in replacement for:  gui/tabs/tab_servers.py
Requires:                  bridges/java_admin_sdk.py  +  bridges/ServerManager.jar
                           (optional — falls back gracefully if absent)
"""

import webbrowser
import tkinter.filedialog as _fd
from gui.tabs._base import *

# ── Java bridge (optional) ────────────────────────────────────────────────────
try:
    from bridges.java_admin_sdk import java_bridge as _jb
    _BRIDGE = _jb
    _BRIDGE_OK = _jb.available
except Exception:
    _BRIDGE    = None
    _BRIDGE_OK = False

# ── Knowledge-base snapshot (optional) ───────────────────────────────────────
try:
    from memory.knowledge_base import kb as _kb
    _KB_OK = True
except Exception:
    _kb    = None
    _KB_OK = False


class ServersTab(BaseTab):

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._servers        = []
        self._auto_refresh   = False
        self._refresh_job    = None
        self._selected_srv   = None
        self._build()
        self._load()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        rf = self._page_header("Servers", "🖥",
                                "Live status • Start / Stop / Restart via Java SDK")

        # Right-side header buttons
        ctk.CTkButton(rf, text="⟳ Refresh", width=90, height=30,
                      fg_color=BG2, text_color=TEXT, font=F_SM,
                      command=self._load).pack(side="right", padx=3)

        self._auto_btn = ctk.CTkButton(
            rf, text="⏱ Auto: OFF", width=105, height=30,
            fg_color=BG2, text_color=TEXT2, font=F_SM,
            command=self._toggle_auto)
        self._auto_btn.pack(side="right", padx=3)

        ctk.CTkButton(rf, text="🌐 Open CMC", width=100, height=30,
                      fg_color=BLUE, text_color="white", font=F_SM,
                      command=self._open_cmc).pack(side="right", padx=3)

        body = self._body
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(3, weight=1)

        # ── KPI tiles ─────────────────────────────────────────────────────────
        tiles = ctk.CTkFrame(body, fg_color="transparent")
        tiles.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        self._t = {}
        for k, lbl, col, ico in [
            ("total",   "Total",         CYAN,  "🖧"),
            ("running", "Running",        GREEN, "●"),
            ("stopped", "Stopped",        RED,   "○"),
            ("errors",  "With Failures",  AMBER, "⚠"),
        ]:
            c, v = stat_tile(tiles, lbl, "—", col, ico)
            c.pack(side="left", padx=(0, 8), fill="both", expand=True)
            self._t[k] = v

        # ── SDK status banner ─────────────────────────────────────────────────
        if _BRIDGE_OK:
            sdk_bar = ctk.CTkFrame(body, fg_color="#001800", corner_radius=8,
                                    border_color=GREEN, border_width=1)
            sdk_bar.grid(row=1, column=0, sticky="ew", padx=14, pady=(8, 2))
            ctk.CTkLabel(sdk_bar,
                         text="✅  Java Admin SDK Bridge connected — "
                              "Start / Stop / Restart are active",
                         font=F_SM, text_color=GREEN, anchor="w"
                         ).pack(padx=14, pady=8, fill="x")
        else:
            sdk_bar = ctk.CTkFrame(body, fg_color="#1c1800", corner_radius=8,
                                    border_color=AMBER, border_width=1)
            sdk_bar.grid(row=1, column=0, sticky="ew", padx=14, pady=(8, 2))
            sdk_inner = ctk.CTkFrame(sdk_bar, fg_color="transparent")
            sdk_inner.pack(fill="x", padx=14, pady=8)
            ctk.CTkLabel(sdk_inner,
                         text=("⚠  Server Start/Stop requires Java Admin SDK  "
                                "— REST API does not expose this operation."),
                         font=F_SM, text_color=AMBER, anchor="w",
                         ).pack(side="left", fill="x", expand=True)
            ctk.CTkButton(sdk_inner, text="📁 Setup SDK",
                          width=100, height=28,
                          fg_color=AMBER, text_color=BG0, font=F_SM,
                          command=self._show_sdk_wizard).pack(side="right", padx=(8, 0))
            ctk.CTkButton(sdk_inner, text="🌐 Open CMC",
                          width=90, height=28,
                          fg_color=BG2, text_color=TEXT2, font=F_SM,
                          command=self._open_cmc).pack(side="right", padx=4)

        # ── Server action toolbar ─────────────────────────────────────────────
        act = ctk.CTkFrame(body, fg_color=BG1, corner_radius=0, height=46)
        act.grid(row=2, column=0, sticky="ew")
        act.pack_propagate(False)

        self._sel_lbl = ctk.CTkLabel(act, text="Select a server →",
                                      font=F_SM, text_color=TEXT2)
        self._sel_lbl.pack(side="left", padx=12)

        _ab = dict(height=30, font=F_SM,
                   state="normal" if _BRIDGE_OK else "disabled")

        self._btn_start = ctk.CTkButton(
            act, text="▶ Start", width=85,
            fg_color=GREEN if _BRIDGE_OK else BG2,
            text_color=BG0 if _BRIDGE_OK else TEXT2,
            command=lambda: self._server_action("start"), **_ab)
        self._btn_start.pack(side="right", padx=4, pady=8)

        self._btn_stop = ctk.CTkButton(
            act, text="⏹ Stop", width=85,
            fg_color=RED if _BRIDGE_OK else BG2,
            text_color="white" if _BRIDGE_OK else TEXT2,
            command=lambda: self._server_action("stop"), **_ab)
        self._btn_stop.pack(side="right", padx=4, pady=8)

        self._btn_restart = ctk.CTkButton(
            act, text="🔄 Restart", width=90,
            fg_color=AMBER if _BRIDGE_OK else BG2,
            text_color=BG0 if _BRIDGE_OK else TEXT2,
            command=lambda: self._server_action("restart"), **_ab)
        self._btn_restart.pack(side="right", padx=4, pady=8)

        ctk.CTkButton(act, text="🔍 Details", width=90, height=30,
                      fg_color=BG2, text_color=TEXT, font=F_SM,
                      command=self._show_details).pack(side="right", padx=4, pady=8)

        if not _BRIDGE_OK:
            ctk.CTkLabel(act,
                         text="Start/Stop requires Java SDK — click '📁 Setup SDK' above",
                         font=F_XS, text_color=TEXT2
                         ).pack(side="left", padx=8)

        # ── Server table ──────────────────────────────────────────────────────
        cols = [
            ("status",   "Status",      100),
            ("name",     "Server Name", 280),
            ("kind",     "Kind",        160),
            ("host",     "Host",        130),
            ("failures", "Failures",     80),
            ("pid",      "PID",          60),
        ]
        self._tree, tf = make_tree(body, cols, multi=False)
        tf.grid(row=3, column=0, sticky="nsew", padx=14, pady=(4, 10))
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", self._show_details)
        self._tree.tag_configure("ok",  foreground=GREEN)
        self._tree.tag_configure("err", foreground=RED)

    # ── Load ─────────────────────────────────────────────────────────────────

    def _load(self):
        self.set_status("⏳ Loading servers…", AMBER)

        def _run():
            # Prefer Java bridge for richer data
            if _BRIDGE_OK and _BRIDGE:
                ok, data = _BRIDGE.list_servers()
                if ok and isinstance(data, list) and data:
                    return data, "Java SDK"
            # Fall back to REST API
            return bo_session.get_all_servers() or [], "REST API"

        def _done(result):
            servers, source = result
            self._servers = servers
            self._render()
            running = sum(1 for s in servers
                          if str(s.get("status") or
                                 s.get("SI_SERVER_IS_ALIVE", "")).upper()
                          in ("RUNNING", "TRUE", "1", "STARTED"))
            stopped  = len(servers) - running
            failures = sum(1 for s in servers
                           if int(s.get("failures") or
                                  s.get("SI_TOTAL_NUM_FAILURES", 0) or 0) > 0)
            self._t["total"].configure(text=str(len(servers)))
            self._t["running"].configure(text=str(running))
            self._t["stopped"].configure(text=str(stopped))
            self._t["errors"].configure(text=str(failures))

            # KB snapshot
            if _KB_OK and _kb:
                for s in servers:
                    try:
                        _kb.save_server_snapshot(
                            server_id=str(s.get("id") or s.get("SI_ID", "")),
                            server_name=s.get("name") or s.get("SI_NAME", ""),
                            status=s.get("status") or (
                                "Running"
                                if str(s.get("SI_SERVER_IS_ALIVE","")).upper()
                                in ("TRUE","1")
                                else "Stopped"),
                            failures=int(s.get("failures") or
                                        s.get("SI_TOTAL_NUM_FAILURES", 0) or 0),
                        )
                    except Exception:
                        pass

            col = GREEN if stopped == 0 else (AMBER if running > 0 else RED)
            self.set_status(
                f"✅ {len(servers)} servers  —  "
                f"{running} running, {stopped} stopped  [{source}]", col)

        bg(_run, _done, self)

    def _render(self):
        for r in self._tree.get_children():
            self._tree.delete(r)
        for srv in self._servers:
            st    = (srv.get("status") or
                     ("Running"
                      if str(srv.get("SI_SERVER_IS_ALIVE","")).upper()
                      in ("TRUE","1","RUNNING")
                      else "Stopped"))
            ico   = "● Running" if st in ("Running","RUNNING") else "○ Stopped"
            tag   = "ok" if st in ("Running","RUNNING") else "err"
            iid   = str(srv.get("id") or srv.get("SI_ID", id(srv)))
            name  = srv.get("name") or srv.get("SI_NAME", "")
            self._tree.insert("", "end", iid=iid, tags=(tag,),
                              values=(ico, name,
                                      srv.get("kind") or srv.get("SI_KIND",""),
                                      srv.get("host") or srv.get("SI_SERVER_HOST",""),
                                      srv.get("failures") or srv.get("SI_TOTAL_NUM_FAILURES",0) or 0,
                                      srv.get("pid") or srv.get("SI_PID","")))

    # ── Selection ─────────────────────────────────────────────────────────────

    def _on_select(self, _event=None):
        sel = self._tree.selection()
        if not sel:
            return
        iid  = sel[0]
        name = self._tree.set(iid, "name")
        self._selected_srv = name
        self._sel_lbl.configure(text=f"Selected: {name}")
        if _BRIDGE_OK:
            for btn in (self._btn_start, self._btn_stop, self._btn_restart):
                btn.configure(state="normal")

    # ── Server actions ────────────────────────────────────────────────────────

    def _server_action(self, action: str):
        if not self._selected_srv:
            self.set_status("⚠ Select a server first", AMBER)
            return
        if not _BRIDGE_OK or not _BRIDGE:
            self._open_cmc()
            return

        verbs = {"start": "Start", "stop": "Stop", "restart": "Restart"}
        verb  = verbs[action]
        if not confirm(f"⚠ {verb} Server",
                       f"{verb} server:\n\n  {self._selected_srv}\n\nProceed?",
                       parent=self):
            return

        self.set_status(f"⏳ {verb}ing {self._selected_srv}…", AMBER)
        for b in (self._btn_start, self._btn_stop, self._btn_restart):
            b.configure(state="disabled")

        srv_name = self._selected_srv

        def _run():
            fn = getattr(_BRIDGE, f"{action}_server")
            return fn(srv_name)

        def _done(result):
            ok, msg = result
            for b in (self._btn_start, self._btn_stop, self._btn_restart):
                b.configure(state="normal")
            if ok:
                self.set_status(
                    f"✅ {verb} sent to {srv_name}  —  refreshing in 3s…", GREEN)
                if _KB_OK and _kb:
                    _kb.log_automation(
                        trigger="user", action=f"{action}_server",
                        target=srv_name, result="success", success=True)
                self.after(3000, self._load)
            else:
                self.set_status(f"❌ {verb} failed: {msg}", RED)
                if _KB_OK and _kb:
                    _kb.log_automation(
                        trigger="user", action=f"{action}_server",
                        target=srv_name, result=msg, success=False)

        bg(_run, _done, self)

    # ── Auto refresh ──────────────────────────────────────────────────────────

    def _toggle_auto(self):
        self._auto_refresh = not self._auto_refresh
        if self._auto_refresh:
            self._auto_btn.configure(text="⏱ Auto: ON", text_color=GREEN)
            self._schedule()
        else:
            self._auto_btn.configure(text="⏱ Auto: OFF", text_color=TEXT2)
            if self._refresh_job:
                self.after_cancel(self._refresh_job)
                self._refresh_job = None

    def _schedule(self):
        if self._auto_refresh:
            self._load()
            self._refresh_job = self.after(30_000, self._schedule)

    # ── Details popup ─────────────────────────────────────────────────────────

    def _show_details(self, _event=None):
        sel = self._tree.selection()
        if not sel:
            return
        iid = sel[0]
        srv = next((s for s in self._servers
                    if str(s.get("id") or s.get("SI_ID","")) == iid), None)
        if not srv:
            return
        _ServerDetailWindow(self, srv)

    # ── CMC opener ───────────────────────────────────────────────────────────

    def _open_cmc(self):
        url = bo_session.get_server_start_url()
        webbrowser.open(url)
        self.set_status(f"🌐 Opened CMC: {url}")

    # ── SDK setup wizard ──────────────────────────────────────────────────────

    def _show_sdk_wizard(self):
        """Step-by-step popup to configure the Java Admin SDK bridge."""
        win = ctk.CTkToplevel(self)
        win.title("📁 Java Admin SDK Setup")
        win.geometry("720x580")
        win.configure(fg_color=BG0)
        win.grab_set()

        ctk.CTkLabel(win, text="⚙  Java Admin SDK Setup",
                     font=F_H1, text_color=AMBER).pack(pady=(16, 4))
        ctk.CTkLabel(win,
                     text=("Once configured, Start / Stop / Restart buttons "
                            "become active without needing CMC."),
                     font=F_SM, text_color=TEXT2).pack()

        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=8)

        steps = [
            ("Step 1 — Compile ServerManager.java",
             "cd bridges\n"
             "javac -cp \"D:\\SAP BO\\SAP BO\\java\\lib\\*\" ServerManager.java\n"
             "jar cfe ServerManager.jar ServerManager ServerManager.class"),
            ("Step 2 — Add to .env",
             "JAVA_BRIDGE_JAR=D:\\bo-commander\\bridges\\ServerManager.jar\n"
             "JAVA_SDK_CLASSPATH=D:\\SAP BO\\SAP BO\\java\\lib\\*"),
            ("Step 3 — Classpath jars required",
             "cecore.jar  cesession.jar  celib.jar\n"
             "ceplugins_core.jar  ebus420.jar\n"
             "(all found in:  D:\\SAP BO\\SAP BO\\java\\lib\\)"),
            ("Step 4 — Restart BO Commander",
             "The Java bridge detects the JAR automatically.\n"
             "You will see a green 'Java Admin SDK Bridge connected' banner."),
        ]

        for title, code in steps:
            f = ctk.CTkFrame(scroll, fg_color=BG1, corner_radius=8,
                              border_color=AMBER, border_width=1)
            f.pack(fill="x", pady=6)
            ctk.CTkLabel(f, text=title, font=F_H3, text_color=AMBER,
                         anchor="w").pack(fill="x", padx=12, pady=(10, 4))
            tb = ctk.CTkTextbox(f, height=60, fg_color=BG0,
                                 text_color=TEAL, font=F_MONO)
            tb.pack(fill="x", padx=12, pady=(0, 10))
            tb.insert("end", code)
            tb.configure(state="disabled")

        # JAR path picker
        jar_row = ctk.CTkFrame(win, fg_color="transparent")
        jar_row.pack(fill="x", padx=20, pady=(6, 4))
        ctk.CTkLabel(jar_row, text="JAR Path:", font=F_SM,
                     text_color=TEXT2).pack(side="left")
        jar_var = ctk.StringVar()
        jar_entry = ctk.CTkEntry(jar_row, textvariable=jar_var, width=420,
                                  placeholder_text="D:\\bo-commander\\bridges\\ServerManager.jar")
        jar_entry.pack(side="left", padx=8)

        def _browse():
            p = _fd.askopenfilename(
                filetypes=[("JAR files", "*.jar"), ("All files", "*.*")],
                title="Select ServerManager.jar", parent=win)
            if p:
                jar_var.set(p)

        ctk.CTkButton(jar_row, text="Browse", width=70,
                      fg_color=BG2, font=F_SM,
                      command=_browse).pack(side="left")

        def _save():
            jar = jar_var.get().strip()
            if not jar:
                return
            try:
                import re
                env_path = __import__("pathlib").Path(".env")
                txt = env_path.read_text("utf-8") if env_path.exists() else ""
                if "JAVA_BRIDGE_JAR=" in txt:
                    txt = re.sub(r"JAVA_BRIDGE_JAR=.*",
                                 f"JAVA_BRIDGE_JAR={jar}", txt)
                else:
                    txt += f"\nJAVA_BRIDGE_JAR={jar}\n"
                env_path.write_text(txt, "utf-8")
                self.set_status(
                    "✅ JAR path saved to .env — restart BO Commander to activate",
                    GREEN)
                win.destroy()
            except Exception as e:
                self.set_status(f"❌ Save failed: {e}", RED)

        ctk.CTkButton(win, text="💾 Save & Close", height=38,
                      fg_color=AMBER, text_color=BG0, font=F_H3,
                      command=_save).pack(fill="x", padx=20, pady=10)


class _ServerDetailWindow(ctk.CTkToplevel):
    def __init__(self, parent, srv):
        super().__init__(parent)
        self.title(f"🖥  {srv.get('name','Server')}")
        self.geometry("500x440")
        self.configure(fg_color=BG0)
        self._build(srv)

    def _build(self, srv):
        name = srv.get("name") or srv.get("SI_NAME", "")
        st   = (srv.get("status") or
                ("Running"
                 if str(srv.get("SI_SERVER_IS_ALIVE","")).upper()
                 in ("TRUE","1","RUNNING")
                 else "Stopped"))
        col  = GREEN if "running" in st.lower() else RED

        ctk.CTkLabel(self, text=name, font=F_H2, text_color=CYAN
                     ).pack(pady=(16, 4))
        ctk.CTkLabel(self, text=f"● {st}", font=F_H3, text_color=col
                     ).pack()
        ctk.CTkFrame(self, fg_color=BG2, height=1).pack(fill="x", padx=20, pady=8)

        frame = ctk.CTkFrame(self, fg_color=BG1, corner_radius=10)
        frame.pack(fill="both", expand=True, padx=20, pady=4)

        fields = [
            ("Kind",        srv.get("kind") or srv.get("SI_KIND","")),
            ("Host",        srv.get("host") or srv.get("SI_SERVER_HOST","")),
            ("PID",         srv.get("pid")  or srv.get("SI_PID","")),
            ("Total Failures", srv.get("failures") or srv.get("SI_TOTAL_NUM_FAILURES",0)),
            ("Description", srv.get("description") or srv.get("SI_DESCRIPTION","")),
        ]
        for lbl, val in fields:
            if not val and val != 0:
                val = "—"
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=3)
            ctk.CTkLabel(row, text=lbl, font=F_SM, text_color=TEXT2,
                         width=130, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=str(val), font=F_SM, text_color=TEXT,
                         wraplength=300, justify="left",
                         anchor="w").pack(side="left", fill="x", expand=True)

        ctk.CTkButton(self, text="✕ Close", height=34,
                      fg_color=BG2, text_color=TEXT2, font=F_SM,
                      command=self.destroy).pack(fill="x", padx=20, pady=12)
