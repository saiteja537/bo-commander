"""
gui/tabs/tab_reports.py  —  Reports Manager (Full CRUD)
GET  list all reports, instance history
POST run/schedule a report (XML — correct format)
DEL  delete report
"""
import webbrowser
from gui.tabs._base import *

# URL probe cache
_WEB_BASE = [None]

def _get_web_base():
    if _WEB_BASE[0]:
        return _WEB_BASE[0]
    try:
        import requests
        from urllib.parse import urlparse
        base   = (getattr(bo_session, "base_url", "") or "").rstrip("/")
        parsed = urlparse(base)
        host   = parsed.hostname or "localhost"
        for port in [8080, 443, 80, 8443, 8000]:
            for scheme in ["http", "https"]:
                try:
                    url = f"{scheme}://{host}:{port}/BOE/OpenDocument/"
                    r = bo_session.session.head(url, timeout=2, allow_redirects=True,
                                                verify=False)
                    if r.status_code not in (404, 410, 502, 503, 504):
                        _WEB_BASE[0] = f"{scheme}://{host}:{port}"
                        return _WEB_BASE[0]
                except Exception:
                    pass
        _WEB_BASE[0] = f"http://{host}:8080"
    except Exception:
        _WEB_BASE[0] = "http://localhost:8080"
    return _WEB_BASE[0]

def _open_doc_url(report_id):
    base = _get_web_base()
    return f"{base}/BOE/OpenDocument/opendoc/openDocument.jsp?iDocID={report_id}&sIDType=InfoObjectID"


KIND_META = {
    "Webi":          ("📊", "WebI",    BLUE),
    "CrystalReport": ("💎", "Crystal", VIOLET),
    "Excel":         ("📗", "AO/XLS",  GREEN),
    "Pdf":           ("📄", "PDF",     RED),
}


class ReportsTab(BaseTab):

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._reports = []
        self._type_f  = "All"
        self._build()
        self._load()

    def _build(self):
        rf = self._page_header("Reports Manager", "📊",
                                "Run, schedule, delete, and view report history")
        ctk.CTkButton(rf, text="⟳ Refresh", width=90, height=30,
                      fg_color=BG2, text_color=TEXT, font=F_SM,
                      command=self._load).pack(side="right", padx=3)

        body = self._body
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        # ── Stat tiles ────────────────────────────────────────────────────────
        tiles = ctk.CTkFrame(body, fg_color="transparent")
        tiles.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        self._t = {}
        for k, lbl, col, ico in [
            ("total",   "Total",      CYAN,   "📋"),
            ("webi",    "WebI",       BLUE,   "📊"),
            ("crystal", "Crystal",   VIOLET, "💎"),
            ("ao",      "AO/Excel",  GREEN,  "📗"),
            ("failed",  "Failed Runs", RED,  "❌"),
        ]:
            c, v = stat_tile(tiles, lbl, "—", col, ico)
            c.pack(side="left", padx=(0, 8), fill="both", expand=True)
            self._t[k] = v

        # ── Filter bar ────────────────────────────────────────────────────────
        fbar = ctk.CTkFrame(body, fg_color=BG1, corner_radius=8, height=44)
        fbar.grid(row=1, column=0, sticky="ew", padx=14, pady=8)
        fbar.pack_propagate(False)

        self._type_btns = {}
        for tid, ico, col in [("All","📋",CYAN),("Webi","📊",BLUE),
                               ("CrystalReport","💎",VIOLET),("Excel","📗",GREEN),("Pdf","📄",RED)]:
            lbl = "All" if tid=="All" else KIND_META.get(tid,("","?",""))[1]
            b = ctk.CTkButton(fbar, text=f"{ico} {lbl}", width=90, height=28,
                              corner_radius=14, font=F_XS,
                              fg_color=col if tid=="All" else BG2,
                              hover_color=col, text_color="white" if tid=="All" else TEXT,
                              command=lambda t=tid,c=col: self._set_type(t,c))
            b.pack(side="left", padx=2, pady=6)
            self._type_btns[tid] = (b, col)

        self._q = ctk.StringVar()
        self._q.trace_add("write", lambda *_: self._render())
        ctk.CTkEntry(fbar, textvariable=self._q, placeholder_text="🔎 Search…",
                     width=260, height=28, fg_color=BG2, border_color=BG2,
                     text_color=TEXT, font=F_SM).pack(side="left", padx=8)

        # ── Tree ──────────────────────────────────────────────────────────────
        cols = [
            ("kind",    "Type",     80),
            ("name",    "Name",     280),
            ("owner",   "Owner",    100),
            ("folder",  "Folder",   120),
            ("last_run","Last Run", 140),
            ("created", "Created",  120),
        ]
        self._tree, tree_frame = make_tree(body, cols)
        tree_frame.grid(row=2, column=0, sticky="nsew", padx=14)
        self._tree.bind("<Double-1>", self._open_selected)

        # ── Action row ────────────────────────────────────────────────────────
        act = ctk.CTkFrame(body, fg_color=BG1, corner_radius=0, height=42)
        act.grid(row=3, column=0, sticky="ew")
        act.pack_propagate(False)
        for text, col, cmd in [
            ("▶ Run",        GREEN,  self._run_selected),
            ("🌐 Open",      BLUE,   self._open_browser),
            ("📋 History",   BG2,    self._show_history),
            ("🗑 Delete",    RED,    self._delete_selected),
        ]:
            ctk.CTkButton(act, text=text, width=110, height=30,
                          fg_color=BG2, hover_color=col,
                          text_color=TEXT, font=F_SM,
                          command=cmd).pack(side="left", padx=4, pady=6)

    # ── Data ──────────────────────────────────────────────────────────────────
    def _load(self):
        _WEB_BASE[0] = None   # reset port probe
        self.set_status("⏳ Loading reports…", AMBER)
        bg(bo_session.get_all_reports_typed, self._on_loaded, self)

    def _on_loaded(self, data):
        self._reports = data or []
        kinds = [r.get("kind","") for r in self._reports]
        self._t["total"].configure(text=str(len(self._reports)))
        self._t["webi"].configure(text=str(kinds.count("Webi")))
        self._t["crystal"].configure(text=str(kinds.count("CrystalReport")))
        self._t["ao"].configure(text=str(kinds.count("Excel")))
        self._t["failed"].configure(text="…")
        self._render()
        self.set_status(f"✅ {len(self._reports)} reports loaded", GREEN)
        bg(lambda: len(bo_session.get_instances(status="failed", limit=200) or []),
           lambda n: self._t["failed"].configure(text=str(n)), self)

    def _set_type(self, tid, col):
        self._type_f = tid
        for t, (b, c) in self._type_btns.items():
            b.configure(fg_color=c if t==tid else BG2,
                        text_color="white" if t==tid else TEXT)
        self._render()

    def _render(self):
        q = self._q.get().lower()
        for r in self._tree.get_children(): self._tree.delete(r)
        count = 0
        for rep in self._reports:
            if self._type_f != "All" and rep.get("kind") != self._type_f:
                continue
            if q and q not in rep.get("name","").lower() and q not in rep.get("owner","").lower():
                continue
            kind = rep.get("kind","")
            icon = KIND_META.get(kind, ("📋","",TEXT))[0]
            self._tree.insert("", "end", iid=str(rep.get("id","")),
                              values=(f"{icon} {KIND_META.get(kind,('','?',''))[1]}",
                                      rep.get("name",""), rep.get("owner",""),
                                      str(rep.get("folder",""))[:28],
                                      str(rep.get("last_run",""))[:19],
                                      str(rep.get("created",""))[:16]))
            count += 1
        self.set_status(f"📊 {count} of {len(self._reports)} reports")

    def _selected_report(self):
        sel = self._tree.selection()
        if not sel:
            show_info("Select Report", "Select a report first.", parent=self)
            return None, None
        iid = sel[0]
        rep = next((r for r in self._reports if str(r.get("id","")) == iid), None)
        return iid, rep

    # ── CRUD ──────────────────────────────────────────────────────────────────
    def _run_selected(self):
        iid, rep = self._selected_report()
        if not rep:
            return
        self.set_status(f"⏳ Scheduling: {rep['name']}…", AMBER)
        bg(lambda: bo_session.schedule_report(iid, "now"),
           lambda r: self._handle_write(r, f"Scheduled: {rep['name']}"), self)

    def _open_browser(self):
        iid, rep = self._selected_report()
        if not rep:
            return
        url = _open_doc_url(iid)
        webbrowser.open(url)
        self.set_status(f"🌐 Opened: {rep['name']}")

    def _open_selected(self, _event=None):
        self._open_browser()

    def _show_history(self):
        iid, rep = self._selected_report()
        if not rep:
            return
        _HistoryWindow(self, rep, iid)

    def _delete_selected(self):
        iid, rep = self._selected_report()
        if not rep:
            return
        if not confirm("Delete Report",
                       f"Permanently delete report:\n\n{rep['name']}\n\n"
                       "This removes the report and ALL its instances.", parent=self):
            return
        self.set_status(f"⏳ Deleting {rep['name']}…", AMBER)
        def _do():
            return bo_session.delete_report(iid)
        def _done(r):
            self._handle_write(r, f"Deleted: {rep['name']}")
            if (r[0] if isinstance(r, tuple) else bool(r)):
                self._load()
        bg(_do, _done, self)

    def _handle_write(self, r, ok_msg):
        ok  = r[0] if isinstance(r, tuple) else bool(r)
        msg = r[1] if isinstance(r, tuple) and len(r)>1 else ""
        if ok:
            self.set_status(f"✅ {ok_msg}", GREEN)
        else:
            self.set_status(f"❌ {msg[:80]}", RED)
            show_error("Failed", msg, parent=self)


class _HistoryWindow(ctk.CTkToplevel):
    def __init__(self, parent, report, report_id):
        super().__init__(parent)
        self._rep = report
        self._rid = report_id
        self.title(f"📋 History — {report.get('name','')[:50]}")
        self.geometry("900x480")
        self.configure(fg_color=BG0)
        self._build()
        bg(lambda: bo_session.get_report_instances(report_id, limit=100),
           self._on_loaded, self)

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=BG2, corner_radius=0, height=46)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=f"📋  {self._rep.get('name','')}",
                     font=F_H2, text_color=TEXT).pack(side="left", padx=14)
        self._count_lbl = ctk.CTkLabel(hdr, text="Loading…", font=F_SM, text_color=TEXT2)
        self._count_lbl.pack(side="right", padx=14)

        cols = [("status","Status",110),("start","Started",155),
                ("end","Ended",155),("owner","Owner",110),("fmt","Format",80)]
        self._tree, tf = make_tree(self, cols, multi=False)
        tf.pack(fill="both", expand=True, padx=10, pady=8)

        act = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=40)
        act.pack(fill="x")
        act.pack_propagate(False)
        ctk.CTkButton(act, text="🔄 Retry Failed", width=120, height=28,
                      fg_color=AMBER, text_color=BG0, font=F_SM,
                      command=self._retry_failed).pack(side="left", padx=8, pady=6)
        ctk.CTkButton(act, text="✕ Close", width=80, height=28,
                      fg_color=BG2, text_color=TEXT2, font=F_SM,
                      command=self.destroy).pack(side="right", padx=8, pady=6)

    def _on_loaded(self, instances):
        self._instances = instances or []
        for r in self._tree.get_children(): self._tree.delete(r)
        STATUS_ICON = {"Success":"✅","Failed":"❌","Running":"⏳","Pending":"⏸"}
        STATUS_TAG  = {"Success":"ok","Failed":"fail","Running":"run","Pending":"pend"}
        for inst in self._instances:
            st   = inst.get("status","")
            icon = STATUS_ICON.get(st,"⬜")
            tag  = STATUS_TAG.get(st,"")
            self._tree.insert("", "end", tags=(tag,),
                              values=(f"{icon} {st}",
                                      str(inst.get("start_time",""))[:19],
                                      str(inst.get("end_time",""))[:19],
                                      inst.get("owner",""), inst.get("format","PDF")))
        self._tree.tag_configure("ok",   foreground=GREEN)
        self._tree.tag_configure("fail", foreground=RED)
        self._tree.tag_configure("run",  foreground=AMBER)
        self._tree.tag_configure("pend", foreground=TEXT2)
        self._count_lbl.configure(text=f"{len(self._instances)} instances")

    def _retry_failed(self):
        failed_ids = [str(i.get("id","")) for i in self._instances
                      if "fail" in str(i.get("status","")).lower() and i.get("id")]
        if not failed_ids:
            show_info("No Failures", "No failed instances found.", parent=self)
            return
        ok, err = bo_session.bulk_retry_instances(failed_ids)
        show_info("Retry", f"✅ Retried: {ok}   ❌ Errors: {err}", parent=self)
