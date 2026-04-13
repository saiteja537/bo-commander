"""
gui/tabs/tab_promotion.py  —  Promotion / LCM
GET  list LCM jobs, conflict report
POST run LCM job
"""
from gui.tabs._base import *


class PromotionTab(BaseTab):

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._jobs      = []
        self._conflicts = []
        self._build()
        self._load()

    def _build(self):
        rf = self._page_header("Promotion / LCM", "🔄",
                                "Run lifecycle management (LCM) promotion jobs")
        ctk.CTkButton(rf, text="⟳ Refresh", width=90, height=30,
                      fg_color=BG2, text_color=TEXT, font=F_SM,
                      command=self._load).pack(side="right", padx=3)

        body = self._body
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        tiles = ctk.CTkFrame(body, fg_color="transparent")
        tiles.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        self._t = {}
        for k, lbl, col, ico in [
            ("total",   "Total Jobs", CYAN,   "🔄"),
            ("success", "Success",    GREEN,  "✅"),
            ("failed",  "Failed",     RED,    "❌"),
            ("pending", "Pending",    AMBER,  "⏳"),
        ]:
            c, v = stat_tile(tiles, lbl, "—", col, ico)
            c.pack(side="left", padx=(0, 8), fill="both", expand=True)
            self._t[k] = v

        # LCM availability banner
        self._banner = ctk.CTkFrame(body, fg_color=BG1, corner_radius=8,
                                     border_color=BLUE, border_width=1)
        self._banner.grid(row=1, column=0, sticky="ew", padx=14, pady=8)
        self._banner_lbl = ctk.CTkLabel(self._banner,
                                         text="ℹ  LCM status: checking…",
                                         font=F_SM, text_color=TEXT2, anchor="w")
        self._banner_lbl.pack(padx=14, pady=8, fill="x")

        cols = [("status","Status",110),("name","Job Name",200),
                ("src","Source",130),("tgt","Target",130),
                ("created","Created",130),("updated","Last Run",130)]
        self._tree, tf = make_tree(body, cols)
        tf.grid(row=2, column=0, sticky="nsew", padx=14)

        act = ctk.CTkFrame(body, fg_color=BG1, corner_radius=0, height=42)
        act.grid(row=3, column=0, sticky="ew")
        act.pack_propagate(False)
        ctk.CTkButton(act, text="▶ Run Job", width=110, height=30,
                      fg_color=GREEN, text_color="white", font=F_SM,
                      command=self._run_job).pack(side="left", padx=4, pady=6)
        ctk.CTkButton(act, text="⚠ View Conflicts", width=130, height=30,
                      fg_color=BG2, hover_color=AMBER, text_color=TEXT, font=F_SM,
                      command=self._view_conflicts).pack(side="left", padx=4, pady=6)

    def _load(self):
        self.set_status("⏳ Loading LCM jobs…", AMBER)
        bg(bo_session.get_lcm_jobs, self._on_loaded, self)

    def _on_loaded(self, jobs):
        self._jobs = jobs or []
        if not self._jobs:
            self._banner_lbl.configure(
                text="⚠  LCM add-on may not be installed on this BO server. "
                     "LCM requires the Promotion Management add-on (404 = not installed).",
                text_color=AMBER
            )
            self._banner.configure(border_color=AMBER)
        else:
            self._banner_lbl.configure(
                text=f"✅  LCM is available — {len(self._jobs)} promotion job(s) found",
                text_color=GREEN
            )
            self._banner.configure(border_color=GREEN)

        s_map = {"Success": 0, "Failed": 0, "Pending": 0}
        for j in self._jobs:
            st = str(j.get("status",""))
            if st in s_map: s_map[st] += 1
        self._t["total"].configure(text=str(len(self._jobs)))
        self._t["success"].configure(text=str(s_map["Success"]))
        self._t["failed"].configure(text=str(s_map["Failed"]))
        self._t["pending"].configure(text=str(s_map["Pending"]))
        self._render()
        self.set_status(f"✅ {len(self._jobs)} LCM jobs", GREEN if self._jobs else AMBER)

    def _render(self):
        for r in self._tree.get_children(): self._tree.delete(r)
        for j in self._jobs:
            st  = j.get("status","")
            ico = {"Success":"✅","Failed":"❌","Running":"⏳"}.get(st,"⏸")
            tag = {"Success":"ok","Failed":"fail","Running":"run"}.get(st,"pend")
            self._tree.insert("", "end", iid=str(j.get("id","")), tags=(tag,),
                              values=(f"{ico} {st}", j.get("name",""),
                                      j.get("source_system",""), j.get("target_system",""),
                                      str(j.get("created",""))[:16],
                                      str(j.get("updated",""))[:16]))
        self._tree.tag_configure("ok",   foreground=GREEN)
        self._tree.tag_configure("fail", foreground=RED)
        self._tree.tag_configure("run",  foreground=AMBER)
        self._tree.tag_configure("pend", foreground=TEXT2)

    def _run_job(self):
        sel = self._tree.selection()
        if not sel:
            show_info("Select", "Select a job to run.", parent=self)
            return
        jid   = sel[0]
        jname = self._tree.item(jid)["values"][1]
        if not confirm("Run LCM Job",
                       f"Run promotion job:\n\n{jname}\n\n"
                       "This will promote objects from source to target system.",
                       parent=self):
            return
        self.set_status(f"⏳ Running job: {jname}…", AMBER)
        bg(lambda: bo_session.run_promotion_job(jid),
           lambda r: (
               self.set_status(f"✅ Job started: {jname}" if r[0] else f"❌ Failed: {r[1][:60]}",
                               GREEN if r[0] else RED),
               self._load()
           ), self)

    def _view_conflicts(self):
        sel = self._tree.selection()
        if not sel:
            show_info("Select", "Select a job to view conflicts.", parent=self)
            return
        jid = sel[0]
        self.set_status("⏳ Loading conflicts…", AMBER)
        bg(lambda: bo_session.get_promotion_conflicts(jid),
           lambda r: _ConflictWindow(self, r or [], jid), self)


class _ConflictWindow(ctk.CTkToplevel):
    def __init__(self, parent, conflicts, job_id):
        super().__init__(parent)
        self._parent  = parent
        self._conflicts = conflicts
        self._job_id  = job_id
        self.title(f"⚠  Conflicts — Job {job_id}")
        self.geometry("700x440")
        self.configure(fg_color=BG0)
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text=f"⚠  {len(self._conflicts)} Conflict(s)",
                     font=F_H2, text_color=AMBER).pack(pady=(16, 4))
        ctk.CTkFrame(self, fg_color=BG2, height=1).pack(fill="x", padx=20)

        if not self._conflicts:
            ctk.CTkLabel(self, text="✅ No conflicts found.",
                         font=F_H3, text_color=GREEN).pack(pady=20)
        else:
            cols = [("type","Type",120),("obj","Object",200),
                    ("detail","Detail",240),("resolution","Resolution",100)]
            tree, tf = make_tree(self, cols, multi=False)
            tf.pack(fill="both", expand=True, padx=16, pady=8)
            for i, c in enumerate(self._conflicts):
                tree.insert("", "end", iid=str(i),
                            values=(c.get("type",""), c.get("object",""),
                                    c.get("detail",""), c.get("resolution","")))

        ctk.CTkButton(self, text="✕ Close", height=34, fg_color=BG2,
                      text_color=TEXT2, command=self.destroy).pack(fill="x", padx=20, pady=10)
