"""
gui/tabs/tab_repository.py  —  Repository Health
GET  recycle bin, broken objects, orphan detection
PUT  restore from recycle bin
DEL  delete from recycle bin, empty bin
"""
from gui.tabs._base import *


class RepositoryTab(BaseTab):

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._items   = []
        self._broken  = []
        self._orphans = []
        self._mode    = "recycle"
        self._build()
        self._load()

    def _build(self):
        rf = self._page_header("Repository Health", "🗄",
                                "Recycle bin, broken objects, orphan cleanup")
        ctk.CTkButton(rf, text="⟳ Refresh", width=90, height=30,
                      fg_color=BG2, text_color=TEXT, font=F_SM,
                      command=self._load).pack(side="right", padx=3)
        ctk.CTkButton(rf, text="🗑 Empty Recycle Bin", width=140, height=30,
                      fg_color=RED, text_color="white", font=F_SM,
                      command=self._empty_bin).pack(side="right", padx=3)

        body = self._body
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        tiles = ctk.CTkFrame(body, fg_color="transparent")
        tiles.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        self._t = {}
        for k, lbl, col, ico in [
            ("recycle", "In Recycle Bin", AMBER, "🗑"),
            ("broken",  "Broken Objects", RED,   "💔"),
            ("orphans", "Orphan Instances", VIOLET, "👻"),
        ]:
            c, v = stat_tile(tiles, lbl, "—", col, ico)
            c.pack(side="left", padx=(0, 8), fill="both", expand=True)
            self._t[k] = v

        mbar = ctk.CTkFrame(body, fg_color=BG1, corner_radius=8, height=40)
        mbar.grid(row=1, column=0, sticky="ew", padx=14, pady=8)
        mbar.pack_propagate(False)
        self._btns = {}
        for mode, lbl in [("recycle","🗑 Recycle Bin"),("broken","💔 Broken"),("orphans","👻 Orphans")]:
            b = ctk.CTkButton(mbar, text=lbl, width=130, height=28,
                              fg_color=BLUE if mode == "recycle" else BG2,
                              text_color="white" if mode == "recycle" else TEXT2,
                              font=F_SM, command=lambda m=mode: self._set_mode(m))
            b.pack(side="left", padx=(8 if mode == "recycle" else 2), pady=6)
            self._btns[mode] = b

        # Trees
        r_cols = [("kind","Type",80),("name","Name",220),("owner","Owner",100),
                   ("deleted","Deleted",140),("folder","Folder",150)]
        self._tree_r, tf_r = make_tree(body, r_cols)
        tf_r.grid(row=2, column=0, sticky="nsew", padx=14)
        self._tf_r = tf_r

        b_cols = [("kind","Type",80),("name","Name",220),("issue","Issue",220),
                   ("owner","Owner",100),("path","Path",160)]
        self._tree_b, tf_b = make_tree(body, b_cols)
        tf_b.grid(row=2, column=0, sticky="nsew", padx=14)
        self._tf_b = tf_b; tf_b.grid_remove()

        o_cols = [("kind","Type",80),("name","Name",220),("age","Age (days)",90),
                   ("owner","Owner",100),("start","Last Run",140)]
        self._tree_o, tf_o = make_tree(body, o_cols)
        tf_o.grid(row=2, column=0, sticky="nsew", padx=14)
        self._tf_o = tf_o; tf_o.grid_remove()

        act = ctk.CTkFrame(body, fg_color=BG1, corner_radius=0, height=42)
        act.grid(row=3, column=0, sticky="ew")
        act.pack_propagate(False)
        ctk.CTkButton(act, text="♻ Restore", width=100, height=30,
                      fg_color=BG2, hover_color=GREEN, text_color=TEXT, font=F_SM,
                      command=self._restore).pack(side="left", padx=4, pady=6)
        ctk.CTkButton(act, text="🗑 Delete", width=90, height=30,
                      fg_color=BG2, hover_color=RED, text_color=TEXT, font=F_SM,
                      command=self._delete_selected).pack(side="left", padx=4, pady=6)
        ctk.CTkButton(act, text="🧹 Delete All Orphans", width=150, height=30,
                      fg_color=BG2, hover_color=RED, text_color=TEXT, font=F_SM,
                      command=self._delete_all_orphans).pack(side="left", padx=4, pady=6)

    def _load(self):
        self.set_status("⏳ Loading repository health…", AMBER)
        bg(lambda: (bo_session.get_recycle_bin_items(),
                    bo_session.get_broken_objects(),
                    bo_session.find_orphan_instances(days=90)),
           self._on_loaded, self)

    def _on_loaded(self, result):
        self._items, self._broken, self._orphans = result or ([],[],[])
        self._t["recycle"].configure(text=str(len(self._items)))
        self._t["broken"].configure(text=str(len(self._broken)))
        self._t["orphans"].configure(text=str(len(self._orphans)))
        self._render()
        self.set_status(f"✅ {len(self._items)} recycle  |  {len(self._broken)} broken  |  {len(self._orphans)} orphans",
                        GREEN if not self._broken else AMBER)

    def _set_mode(self, mode):
        self._mode = mode
        for m, b in self._btns.items():
            b.configure(fg_color=BLUE if m == mode else BG2,
                        text_color="white" if m == mode else TEXT2)
        self._tf_r.grid_remove()
        self._tf_b.grid_remove()
        self._tf_o.grid_remove()
        {"recycle": self._tf_r, "broken": self._tf_b, "orphans": self._tf_o}[mode].grid()
        self._render()

    def _render(self):
        if self._mode == "recycle":
            for r in self._tree_r.get_children(): self._tree_r.delete(r)
            for item in self._items:
                self._tree_r.insert("", "end", iid=str(item.get("id","")),
                                    values=(item.get("kind",""), item.get("name",""),
                                            item.get("owner",""),
                                            str(item.get("deleted",""))[:16],
                                            item.get("folder","")))
        elif self._mode == "broken":
            for r in self._tree_b.get_children(): self._tree_b.delete(r)
            for item in self._broken:
                self._tree_b.insert("", "end", iid=str(item.get("id","")), tags=("broken",),
                                    values=(item.get("kind",""), item.get("name",""),
                                            item.get("issue",""), item.get("owner",""),
                                            item.get("path","")))
            self._tree_b.tag_configure("broken", foreground=RED)
        else:
            for r in self._tree_o.get_children(): self._tree_o.delete(r)
            for item in self._orphans:
                self._tree_o.insert("", "end", iid=str(item.get("id","")), tags=("orphan",),
                                    values=(item.get("kind",""), item.get("name",""),
                                            str(item.get("age_days","")),
                                            item.get("owner",""),
                                            str(item.get("start_time",""))[:16]))
            self._tree_o.tag_configure("orphan", foreground=VIOLET)

    def _restore(self):
        if self._mode != "recycle": return
        sel = self._tree_r.selection()
        if not sel:
            show_info("Select", "Select item(s) to restore.", parent=self)
            return
        if not confirm("Restore", f"Restore {len(sel)} item(s) from recycle bin?", parent=self):
            return
        self.set_status("⏳ Restoring…", AMBER)
        def _run():
            ok = err = 0
            for iid in sel:
                r, _ = bo_session.restore_from_recycle_bin(iid)
                if r: ok += 1
                else: err += 1
            return ok, err
        bg(_run, lambda r: (
            self.set_status(f"✅ Restored: {r[0]}  ❌ Errors: {r[1]}", GREEN if r[1] == 0 else AMBER),
            self._load()
        ), self)

    def _delete_selected(self):
        tree = {"recycle": self._tree_r, "broken": self._tree_b, "orphans": self._tree_o}[self._mode]
        sel  = tree.selection()
        if not sel:
            show_info("Select", "Select item(s) first.", parent=self)
            return
        if not confirm("Delete", f"Permanently delete {len(sel)} item(s)?", parent=self):
            return
        self.set_status("⏳ Deleting…", AMBER)
        def _run():
            ok = err = 0
            for iid in sel:
                r, _ = bo_session.delete_object(iid)
                if r: ok += 1
                else: err += 1
            return ok, err
        bg(_run, lambda r: (
            self.set_status(f"✅ Deleted: {r[0]}  ❌ Errors: {r[1]}", GREEN if r[1] == 0 else AMBER),
            self._load()
        ), self)

    def _empty_bin(self):
        n = len(self._items)
        if not n:
            show_info("Empty", "Recycle bin is already empty.", parent=self)
            return
        if not confirm("Empty Recycle Bin",
                       f"Permanently delete ALL {n} recycle bin items?\n\nCannot be undone.",
                       parent=self):
            return
        self.set_status("⏳ Emptying recycle bin…", AMBER)
        bg(bo_session.empty_recycle_bin,
           lambda r: (self.set_status(f"✅ Recycle bin emptied", GREEN), self._load()), self)

    def _delete_all_orphans(self):
        if not self._orphans:
            show_info("No Orphans", "No orphan instances found.", parent=self)
            return
        if not confirm("Delete All Orphans",
                       f"Delete {len(self._orphans)} orphan instance(s)?\n\nCannot be undone.",
                       parent=self):
            return
        self.set_status(f"⏳ Deleting {len(self._orphans)} orphans…", AMBER)
        ids = [str(o.get("id","")) for o in self._orphans]
        bg(lambda: bo_session.bulk_delete_instances(ids),
           lambda r: (self.set_status(f"✅ Deleted orphans: {r[0]} OK  {r[1]} errors",
                                       GREEN if r[1] == 0 else AMBER),
                      self._load()), self)
