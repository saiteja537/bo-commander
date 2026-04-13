"""
gui/tabs/tab_scheduling.py  —  Instances & Scheduling (Full CRUD)
GET  list instances with filters
POST retry failed instances
DEL  delete selected, purge old
"""
from gui.tabs._base import *


class SchedulingTab(BaseTab):

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._instances = []
        self._status_f  = "All"
        self._build()
        self._load()

    def _build(self):
        rf = self._page_header("Instances & Scheduling", "📅",
                                "Manage report run history, retry failures, purge old instances")
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
            ("success", "Success",    GREEN,  "✅"),
            ("failed",  "Failed",     RED,    "❌"),
            ("running", "Running",    AMBER,  "⏳"),
            ("pending", "Pending",    BLUE,   "⏸"),
        ]:
            c, v = stat_tile(tiles, lbl, "—", col, ico)
            c.pack(side="left", padx=(0, 8), fill="both", expand=True)
            self._t[k] = v

        # ── Filter + purge bar ────────────────────────────────────────────────
        fbar = ctk.CTkFrame(body, fg_color=BG1, corner_radius=8, height=44)
        fbar.grid(row=1, column=0, sticky="ew", padx=14, pady=8)
        fbar.pack_propagate(False)

        self._stat_btns = {}
        for st, col in [("All",CYAN),("Success",GREEN),("Failed",RED),
                         ("Running",AMBER),("Pending",BLUE)]:
            b = ctk.CTkButton(fbar, text=st, width=90, height=28, corner_radius=14,
                              font=F_XS,
                              fg_color=col if st=="All" else BG2,
                              hover_color=col,
                              text_color="white" if st=="All" else TEXT,
                              command=lambda s=st,c=col: self._set_filter(s,c))
            b.pack(side="left", padx=2, pady=6)
            self._stat_btns[st] = (b, col)

        # Purge controls
        ctk.CTkFrame(fbar, width=1, fg_color=BG2).pack(side="right", fill="y", padx=6, pady=8)
        ctk.CTkButton(fbar, text="🗑 Purge Old", width=100, height=28,
                      fg_color=BG2, hover_color=RED, text_color=RED, font=F_SM,
                      command=self._purge_dialog).pack(side="right", padx=4, pady=6)

        self._q = ctk.StringVar()
        self._q.trace_add("write", lambda *_: self._render())
        ctk.CTkEntry(fbar, textvariable=self._q, placeholder_text="🔎 Search…",
                     width=200, height=28, fg_color=BG2, border_color=BG2,
                     text_color=TEXT, font=F_SM).pack(side="left", padx=8)

        # ── Tree ──────────────────────────────────────────────────────────────
        cols = [
            ("status",   "Status",      110),
            ("name",     "Report Name", 260),
            ("owner",    "Owner",       100),
            ("kind",     "Type",         80),
            ("start",    "Started",     150),
            ("end",      "Ended",       140),
            ("duration", "Duration(s)",  90),
        ]
        self._tree, tree_f = make_tree(body, cols)
        tree_f.grid(row=2, column=0, sticky="nsew", padx=14)

        # ── Action row ────────────────────────────────────────────────────────
        act = ctk.CTkFrame(body, fg_color=BG1, corner_radius=0, height=42)
        act.grid(row=3, column=0, sticky="ew")
        act.pack_propagate(False)
        for text, col, cmd in [
            ("🔄 Retry Selected",   AMBER, self._retry_selected),
            ("🔄 Retry All Failed", AMBER, self._retry_all_failed),
            ("🗑 Delete Selected",  RED,   self._delete_selected),
        ]:
            ctk.CTkButton(act, text=text, width=140, height=30,
                          fg_color=BG2, hover_color=col,
                          text_color=TEXT, font=F_SM,
                          command=cmd).pack(side="left", padx=4, pady=6)

    # ── Data ──────────────────────────────────────────────────────────────────
    def _load(self):
        self.set_status("⏳ Loading instances…", AMBER)
        bg(lambda: bo_session.get_instances_deep(limit=500), self._on_loaded, self)

    def _on_loaded(self, data):
        self._instances = data or []
        statuses = [i.get("status","") for i in self._instances]
        self._t["total"].configure(text=str(len(self._instances)))
        self._t["success"].configure(text=str(sum(1 for s in statuses if s=="Success")))
        self._t["failed"].configure(text=str(sum(1 for s in statuses if s=="Failed")))
        self._t["running"].configure(text=str(sum(1 for s in statuses if s=="Running")))
        self._t["pending"].configure(text=str(sum(1 for s in statuses if s in ("Pending","Scheduled"))))
        self._render()
        self.set_status(f"✅ {len(self._instances)} instances", GREEN)

    def _set_filter(self, st, col):
        self._status_f = st
        for s, (b, c) in self._stat_btns.items():
            b.configure(fg_color=c if s==st else BG2,
                        text_color="white" if s==st else TEXT)
        self._render()

    def _render(self):
        q = self._q.get().lower()
        for r in self._tree.get_children(): self._tree.delete(r)
        STATUS_TAG = {"Success":"ok","Failed":"fail","Running":"run",
                      "Pending":"pend","Scheduled":"sched"}
        for inst in self._instances:
            st = inst.get("status","")
            if self._status_f != "All" and st.lower() != self._status_f.lower():
                continue
            name = inst.get("name","")
            if q and q not in name.lower() and q not in inst.get("owner","").lower():
                continue
            tag = STATUS_TAG.get(st,"")
            STATUS_ICON = {"Success":"✅","Failed":"❌","Running":"⏳","Pending":"⏸","Scheduled":"📅"}
            icon = STATUS_ICON.get(st,"")
            self._tree.insert("", "end", iid=str(inst.get("id","")), tags=(tag,),
                              values=(f"{icon} {st}", name, inst.get("owner",""),
                                      inst.get("kind",""),
                                      str(inst.get("start",""))[:19],
                                      str(inst.get("end",""))[:19],
                                      inst.get("duration","0")))
        self._tree.tag_configure("ok",    foreground=GREEN)
        self._tree.tag_configure("fail",  foreground=RED)
        self._tree.tag_configure("run",   foreground=AMBER)
        self._tree.tag_configure("pend",  foreground=TEXT2)
        self._tree.tag_configure("sched", foreground=BLUE)
        n = len(self._tree.get_children())
        self.set_status(f"📋 {n} of {len(self._instances)} instances")

    # ── CRUD ──────────────────────────────────────────────────────────────────
    def _retry_selected(self):
        sel = self._tree.selection()
        if not sel:
            show_info("Select", "Select instance(s) first.", parent=self)
            return
        if not confirm("Retry", f"Retry {len(sel)} instance(s)?", parent=self):
            return
        self.set_status(f"⏳ Retrying {len(sel)} instances…", AMBER)
        bg(lambda: bo_session.bulk_retry_instances(list(sel)),
           lambda r: self._handle_bulk_write(r, "retry"), self)

    def _retry_all_failed(self):
        failed = [i for i in self._instances if i.get("status") == "Failed"]
        if not failed:
            show_info("No Failures", "No failed instances found.", parent=self)
            return
        if not confirm("Retry All Failed",
                       f"Retry all {len(failed)} failed instances?", parent=self):
            return
        self.set_status(f"⏳ Retrying {len(failed)} failed instances…", AMBER)
        ids = [str(i.get("id","")) for i in failed]
        bg(lambda: bo_session.bulk_retry_instances(ids),
           lambda r: (self._handle_bulk_write(r, "retry"), self._load()), self)

    def _delete_selected(self):
        sel = self._tree.selection()
        if not sel:
            show_info("Select", "Select instance(s) to delete.", parent=self)
            return
        if not confirm("Delete Instances",
                       f"Delete {len(sel)} instance(s)?\nThis cannot be undone.", parent=self):
            return
        self.set_status(f"⏳ Deleting {len(sel)} instances…", AMBER)
        bg(lambda: bo_session.bulk_delete_instances(list(sel)),
           lambda r: (self._handle_bulk_write(r, "delete"), self._load()), self)

    def _purge_dialog(self):
        d = _PurgeDialog(self)
        self.wait_window(d)
        if d.days is None:
            return
        days = d.days
        if not confirm("Purge Old Instances",
                       f"Purge all instances older than {days} days?\n\nThis CANNOT be undone.",
                       parent=self):
            return
        self.set_status(f"⏳ Purging instances older than {days} days…", AMBER)
        bg(lambda: bo_session.purge_old_instances(days),
           lambda r: (self._handle_purge(r, days), self._load()), self)

    def _handle_bulk_write(self, result, op):
        if isinstance(result, tuple) and len(result) >= 2:
            ok, err = result[0], result[1]
        else:
            ok, err = result, 0
        if isinstance(ok, bool):
            msg = "✅ Done" if ok else f"❌ Failed: {err}"
            color = GREEN if ok else RED
        else:
            msg = f"✅ {op.title()}: {ok} OK  ❌ {err} errors"
            color = GREEN if err == 0 else AMBER
        self.set_status(msg, color)

    def _handle_purge(self, result, days):
        if isinstance(result, tuple):
            n, msg = result
        else:
            n, msg = result, ""
        self.set_status(f"✅ Purged {n} instances older than {days} days", GREEN)


class _PurgeDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.days = None
        self.title("🗑 Purge Old Instances")
        self.geometry("340x200")
        self.configure(fg_color=BG0)
        self.grab_set()
        ctk.CTkLabel(self, text="Purge instances older than:",
                     font=F_H3, text_color=TEXT).pack(pady=(20, 8))
        self._days_var = ctk.StringVar(value="30")
        ctk.CTkOptionMenu(self, variable=self._days_var,
                           values=["7","14","30","60","90","180"],
                           fg_color=BG2, button_color=BG2,
                           dropdown_fg_color=BG1, text_color=TEXT,
                           font=F_BODY).pack(fill="x", padx=24)
        ctk.CTkLabel(self, text="days", font=F_SM, text_color=TEXT2).pack()
        ctk.CTkButton(self, text="🗑 Purge", height=36,
                      fg_color=RED, text_color="white", font=F_SM,
                      command=self._ok).pack(fill="x", padx=24, pady=10)
        ctk.CTkButton(self, text="Cancel", height=30,
                      fg_color=BG2, text_color=TEXT2, font=F_SM,
                      command=self.destroy).pack(fill="x", padx=24)

    def _ok(self):
        self.days = int(self._days_var.get())
        self.destroy()
