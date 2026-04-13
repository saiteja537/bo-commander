"""
gui/tabs/tab_dependencies.py  —  Object Dependencies
GET  dependency and dependent chain for any CMS object
Visual tree showing universe → report → instance chains
"""
from gui.tabs._base import *


class DependenciesTab(BaseTab):

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._build()

    def _build(self):
        self._page_header("Object Dependencies", "🔗",
                           "Find what depends on what — safe-delete wizard")

        body = self._body
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # ── Left: search panel ────────────────────────────────────────────────
        left = ctk.CTkFrame(body, fg_color=BG1, corner_radius=10, width=280)
        left.grid(row=0, column=0, sticky="nsew", padx=(14, 4), pady=10)
        left.grid_propagate(False)

        ctk.CTkLabel(left, text="🔍  Search Object",
                     font=F_H3, text_color=CYAN).pack(anchor="w", padx=12, pady=(12, 4))
        ctk.CTkFrame(left, fg_color=BG2, height=1).pack(fill="x", padx=8)

        ctk.CTkLabel(left, text="Object Name or ID:", font=F_SM,
                     text_color=TEXT2).pack(anchor="w", padx=12, pady=(10, 2))
        self._q_var = ctk.StringVar()
        ctk.CTkEntry(left, textvariable=self._q_var,
                     placeholder_text="e.g. Monthly Sales Report",
                     fg_color=BG2, border_color=BG2, text_color=TEXT,
                     font=F_BODY).pack(fill="x", padx=12)

        ctk.CTkLabel(left, text="Object Type:", font=F_SM,
                     text_color=TEXT2).pack(anchor="w", padx=12, pady=(8, 2))
        self._kind_var = ctk.StringVar(value="Any")
        ctk.CTkOptionMenu(left, variable=self._kind_var,
                           values=["Any","Webi","CrystalReport","Universe",
                                   "Connection","Folder"],
                           fg_color=BG2, button_color=BG2,
                           dropdown_fg_color=BG1, text_color=TEXT,
                           font=F_BODY).pack(fill="x", padx=12)

        ctk.CTkButton(left, text="🔍 Search", height=36, fg_color=CYAN,
                      text_color=BG0, font=F_H3,
                      command=self._search).pack(fill="x", padx=12, pady=10)

        ctk.CTkFrame(left, fg_color=BG2, height=1).pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(left, text="Search Results:", font=F_SM,
                     text_color=TEXT2).pack(anchor="w", padx=12, pady=(4, 2))
        self._result_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent", height=260)
        self._result_scroll.pack(fill="both", expand=True, padx=4)

        # ── Right: dependency tree ────────────────────────────────────────────
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 14), pady=10)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(right, fg_color=BG1, corner_radius=8)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self._obj_lbl = ctk.CTkLabel(hdr, text="Select an object to analyse",
                                      font=F_H3, text_color=TEXT2)
        self._obj_lbl.pack(side="left", padx=12, pady=8)
        ctk.CTkButton(hdr, text="⬇ Dependents", width=110, height=26,
                      fg_color=BG2, text_color=TEXT2, font=F_SM,
                      command=lambda: self._load_deps("down")).pack(side="right", padx=4, pady=6)
        ctk.CTkButton(hdr, text="⬆ Dependencies", width=120, height=26,
                      fg_color=BG2, text_color=TEXT2, font=F_SM,
                      command=lambda: self._load_deps("up")).pack(side="right", padx=4, pady=6)

        cols = [("rel","Relation",90),("kind","Type",100),
                ("name","Object Name",280),("owner","Owner",100),("id","ID",70)]
        self._tree, tf = make_tree(right, cols, multi=False)
        tf.grid(row=1, column=0, sticky="nsew")

        act = ctk.CTkFrame(right, fg_color=BG1, corner_radius=0, height=42)
        act.grid(row=2, column=0, sticky="ew")
        act.pack_propagate(False)
        ctk.CTkButton(act, text="📊 Impact Report", width=130, height=30,
                      fg_color=BG2, hover_color=BLUE, text_color=TEXT, font=F_SM,
                      command=self._impact_report).pack(side="left", padx=4, pady=6)

        self._selected_obj = None

    def _search(self):
        q    = self._q_var.get().strip()
        kind = self._kind_var.get()
        if not q:
            show_info("Enter Query", "Enter an object name or ID.", parent=self)
            return
        self.set_status(f"⏳ Searching for '{q}'…", AMBER)
        bg(lambda: bo_session.deep_search(q, search_in=[kind] if kind != "Any" else None, limit=30),
           self._on_searched, self)

    def _on_searched(self, results):
        for w in self._result_scroll.winfo_children():
            w.destroy()
        results = results or []
        if not results:
            ctk.CTkLabel(self._result_scroll, text="No results found.",
                         font=F_SM, text_color=TEXT2).pack()
            self.set_status("No results", TEXT2)
            return
        for obj in results[:30]:
            name = obj.get("name","")
            kind = obj.get("kind","")
            oid  = obj.get("id","")
            btn  = ctk.CTkButton(self._result_scroll,
                                  text=f"[{kind}] {name[:32]}",
                                  height=28, anchor="w", font=F_XS,
                                  fg_color="transparent", hover_color=BG2,
                                  text_color=TEXT,
                                  command=lambda o=obj: self._select_obj(o))
            btn.pack(fill="x", pady=1)
        self.set_status(f"🔍 {len(results)} results", GREEN)

    def _select_obj(self, obj):
        self._selected_obj = obj
        name = obj.get("name","")
        kind = obj.get("kind","")
        self._obj_lbl.configure(text=f"[{kind}] {name}", text_color=CYAN)
        self._load_deps("down")

    def _load_deps(self, direction):
        if not self._selected_obj:
            show_info("Select Object", "Search and select an object first.", parent=self)
            return
        oid  = self._selected_obj.get("id","")
        kind = self._selected_obj.get("kind","")
        self.set_status(f"⏳ Loading {'dependents' if direction=='down' else 'dependencies'}…", AMBER)

        if direction == "down":
            fn = lambda: bo_session.get_object_dependents(oid)
        else:
            fn = lambda: bo_session.get_object_dependencies(oid)

        def _done(data):
            items = data or []
            for r in self._tree.get_children(): self._tree.delete(r)
            # Root node
            name = self._selected_obj.get("name","")
            self._tree.insert("", "end", values=("📌 ROOT", kind, name, "", oid))
            rel_label = "▼ Uses" if direction == "up" else "▲ Used by"
            for item in items:
                self._tree.insert("", "end",
                                   values=(rel_label,
                                           item.get("kind",""),
                                           item.get("name",""),
                                           item.get("owner",""),
                                           str(item.get("id",""))))
            self.set_status(f"🔗 {len(items)} {'dependents' if direction=='down' else 'dependencies'} found", GREEN)

        bg(fn, _done, self)

    def _impact_report(self):
        if not self._selected_obj:
            return
        oid  = self._selected_obj.get("id","")
        kind = self._selected_obj.get("kind","")
        name = self._selected_obj.get("name","")
        self.set_status("⏳ Building impact report…", AMBER)
        bg(lambda: bo_session.get_impact_analysis(oid, kind),
           lambda r: _ImpactReportWindow(self, r, name), self)


class _ImpactReportWindow(ctk.CTkToplevel):
    def __init__(self, parent, data, name):
        super().__init__(parent)
        self.title(f"📊 Impact Report — {name}")
        self.geometry("620x500")
        self.configure(fg_color=BG0)
        ctk.CTkLabel(self, text=f"📊  Impact: {name}", font=F_H2, text_color=CYAN).pack(pady=(16,4))
        ctk.CTkFrame(self, fg_color=BG2, height=1).pack(fill="x", padx=20)
        box = ctk.CTkScrollableFrame(self, fg_color="transparent")
        box.pack(fill="both", expand=True, padx=16, pady=8)
        data = data or {}
        for section, items in data.items():
            ctk.CTkLabel(box, text=section.replace("_"," ").title(),
                         font=F_H3, text_color=AMBER).pack(anchor="w", pady=(8,2))
            if isinstance(items, list):
                for it in (items[:20] if items else []):
                    n = it.get("name","") or str(it)
                    ctk.CTkLabel(box, text=f"  • {n}", font=F_SM,
                                 text_color=TEXT, anchor="w").pack(fill="x")
            elif items:
                ctk.CTkLabel(box, text=f"  {items}", font=F_SM,
                             text_color=TEXT, anchor="w").pack(fill="x")
        ctk.CTkButton(self, text="✕ Close", height=34, fg_color=BG2,
                      text_color=TEXT2, command=self.destroy).pack(fill="x", padx=20, pady=10)
