"""
gui/tabs/tab_universes.py  —  Universes & Connections
GET  list universes, connections, impact analysis
POST test connection (4.3+ only)
DEL  delete connection
"""
from gui.tabs._base import *


class UniversesTab(BaseTab):

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._universes    = []
        self._connections  = []
        self._mode         = "universes"
        self._build()
        self._load()

    def _build(self):
        rf = self._page_header("Universes & Connections", "🌐",
                                "Manage UNV/UNX universes, database connections, impact analysis")
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
            ("universes",   "Universes",   CYAN,   "🌐"),
            ("unx",         "UNX",         BLUE,   "📐"),
            ("unv",         "UNV (Legacy)", VIOLET, "📦"),
            ("connections", "Connections", TEAL,   "🔌"),
        ]:
            c, v = stat_tile(tiles, lbl, "—", col, ico)
            c.pack(side="left", padx=(0, 8), fill="both", expand=True)
            self._t[k] = v

        mbar = ctk.CTkFrame(body, fg_color=BG1, corner_radius=8, height=40)
        mbar.grid(row=1, column=0, sticky="ew", padx=14, pady=8)
        mbar.pack_propagate(False)
        self._u_btn = ctk.CTkButton(mbar, text="🌐 Universes", width=110, height=28,
                                     fg_color=BLUE, text_color="white", font=F_SM,
                                     command=lambda: self._set_mode("universes"))
        self._u_btn.pack(side="left", padx=8, pady=6)
        self._c_btn = ctk.CTkButton(mbar, text="🔌 Connections", width=110, height=28,
                                     fg_color=BG2, text_color=TEXT2, font=F_SM,
                                     command=lambda: self._set_mode("connections"))
        self._c_btn.pack(side="left", padx=2, pady=6)
        self._q = ctk.StringVar()
        self._q.trace_add("write", lambda *_: self._render())
        ctk.CTkEntry(mbar, textvariable=self._q, placeholder_text="🔎 Search…",
                     width=200, height=28, fg_color=BG2, border_color=BG2,
                     text_color=TEXT, font=F_SM).pack(side="left", padx=8)

        u_cols = [("kind","Type",70),("name","Name",240),("owner","Owner",100),
                   ("created","Created",130),("desc","Description",200)]
        self._tree_u, tf_u = make_tree(body, u_cols)
        tf_u.grid(row=2, column=0, sticky="nsew", padx=14)
        self._tf_u = tf_u

        c_cols = [("kind","Type",80),("name","Name",200),("db","Database",150),
                   ("host","Host",130),("owner","Owner",100)]
        self._tree_c, tf_c = make_tree(body, c_cols)
        tf_c.grid(row=2, column=0, sticky="nsew", padx=14)
        self._tf_c = tf_c
        tf_c.grid_remove()

        act = ctk.CTkFrame(body, fg_color=BG1, corner_radius=0, height=42)
        act.grid(row=3, column=0, sticky="ew")
        act.pack_propagate(False)
        ctk.CTkButton(act, text="🔌 Test Connection", width=130, height=30,
                      fg_color=BG2, hover_color=GREEN, text_color=TEXT, font=F_SM,
                      command=self._test_connection).pack(side="left", padx=4, pady=6)
        ctk.CTkButton(act, text="🔗 Impact Analysis", width=130, height=30,
                      fg_color=BG2, hover_color=BLUE, text_color=TEXT, font=F_SM,
                      command=self._impact_analysis).pack(side="left", padx=4, pady=6)
        ctk.CTkButton(act, text="🗑 Delete", width=90, height=30,
                      fg_color=BG2, hover_color=RED, text_color=TEXT, font=F_SM,
                      command=self._delete_selected).pack(side="left", padx=4, pady=6)

    def _load(self):
        self.set_status("⏳ Loading universes and connections…", AMBER)
        bg(lambda: (bo_session.get_all_universes(), bo_session.get_all_connections_typed()),
           self._on_loaded, self)

    def _on_loaded(self, result):
        self._universes, self._connections = result or ([], [])
        unx = sum(1 for u in self._universes if "unx" in str(u.get("kind","")).lower())
        unv = len(self._universes) - unx
        self._t["universes"].configure(text=str(len(self._universes)))
        self._t["unx"].configure(text=str(unx))
        self._t["unv"].configure(text=str(unv))
        self._t["connections"].configure(text=str(len(self._connections)))
        self._render()
        self.set_status(f"✅ {len(self._universes)} universes  |  {len(self._connections)} connections", GREEN)

    def _set_mode(self, mode):
        self._mode = mode
        if mode == "universes":
            self._u_btn.configure(fg_color=BLUE, text_color="white")
            self._c_btn.configure(fg_color=BG2, text_color=TEXT2)
            self._tf_u.grid(); self._tf_c.grid_remove()
        else:
            self._c_btn.configure(fg_color=BLUE, text_color="white")
            self._u_btn.configure(fg_color=BG2, text_color=TEXT2)
            self._tf_c.grid(); self._tf_u.grid_remove()
        self._render()

    def _render(self):
        q = self._q.get().lower()
        if self._mode == "universes":
            for r in self._tree_u.get_children(): self._tree_u.delete(r)
            for u in self._universes:
                if q and q not in u.get("name","").lower(): continue
                kind = u.get("kind","")
                ico  = "📐" if "unx" in kind.lower() else "📦"
                self._tree_u.insert("", "end", iid=str(u.get("id","")),
                                    values=(f"{ico} {kind}", u.get("name",""),
                                            u.get("owner",""), str(u.get("created",""))[:16],
                                            u.get("description","")[:50]))
        else:
            for r in self._tree_c.get_children(): self._tree_c.delete(r)
            for c in self._connections:
                if q and q not in c.get("name","").lower(): continue
                self._tree_c.insert("", "end", iid=str(c.get("id","")),
                                    values=(c.get("kind",""), c.get("name",""),
                                            c.get("database",""), c.get("host",""),
                                            c.get("owner","")))

    def _test_connection(self):
        if self._mode != "connections": return
        sel = self._tree_c.selection()
        if not sel:
            show_info("Select", "Select a connection to test.", parent=self)
            return
        cid   = sel[0]
        cname = self._tree_c.item(cid)["values"][1]
        self.set_status(f"⏳ Testing: {cname}…", AMBER)
        bg(lambda: bo_session.test_connection_typed(cid),
           lambda r: self._show_test_result(r, cname), self)

    def _show_test_result(self, result, cname):
        ok  = result[0] if isinstance(result, tuple) else bool(result)
        msg = result[1] if isinstance(result, tuple) and len(result) > 1 else ""
        if ok:
            self.set_status(f"✅ Connection OK: {cname}", GREEN)
            show_info("Test Result", f"✅ Connection '{cname}' is working.\n\n{msg}", parent=self)
        else:
            self.set_status(f"❌ Connection failed: {cname}", RED)
            show_error("Test Failed", f"❌ '{cname}' failed:\n\n{msg}", parent=self)

    def _impact_analysis(self):
        sel = (self._tree_u if self._mode == "universes" else self._tree_c).selection()
        if not sel:
            show_info("Select", "Select an object to analyse.", parent=self)
            return
        oid  = sel[0]
        kind = "Universe" if self._mode == "universes" else "Connection"
        self.set_status(f"⏳ Running impact analysis for {kind} {oid}…", AMBER)
        bg(lambda: bo_session.get_impact_analysis(oid, kind),
           lambda r: _ImpactWindow(self, r, oid), self)

    def _delete_selected(self):
        tree = self._tree_u if self._mode == "universes" else self._tree_c
        sel  = tree.selection()
        if not sel:
            show_info("Select", "Select an item to delete.", parent=self)
            return
        oid  = sel[0]
        name = tree.item(oid)["values"][1]
        kind = "Universe" if self._mode == "universes" else "Connection"
        if not confirm(f"Delete {kind}", f"Permanently delete:\n\n{name}\n\nThis removes all linked objects!", parent=self):
            return
        self.set_status(f"⏳ Deleting {kind}: {name}…", AMBER)
        bg(lambda: bo_session.delete_connection_typed(oid) if self._mode == "connections"
           else bo_session.delete_object(oid),
           lambda r: (self._handle_write(r, f"Deleted {kind}: {name}"), self._load()), self)

    def _handle_write(self, r, ok_msg):
        ok = r[0] if isinstance(r, tuple) else bool(r)
        msg = r[1] if isinstance(r, tuple) and len(r) > 1 else ""
        if ok:
            self.set_status(f"✅ {ok_msg}", GREEN)
        else:
            self.set_status(f"❌ {msg[:80]}", RED)
            show_error("Failed", msg, parent=self)


class _ImpactWindow(ctk.CTkToplevel):
    def __init__(self, parent, data, oid):
        super().__init__(parent)
        self.title(f"🔗 Impact Analysis — Object {oid}")
        self.geometry("600x440")
        self.configure(fg_color=BG0)
        self._build(data or {})

    def _build(self, data):
        ctk.CTkLabel(self, text="🔗  Impact Analysis",
                     font=F_H2, text_color=CYAN).pack(pady=(16, 4))
        ctk.CTkFrame(self, fg_color=BG2, height=1).pack(fill="x", padx=20)
        box = ctk.CTkScrollableFrame(self, fg_color="transparent")
        box.pack(fill="both", expand=True, padx=16, pady=8)
        for section, items in data.items():
            if not items: continue
            ctk.CTkLabel(box, text=section.replace("_"," ").title(),
                         font=F_H3, text_color=AMBER).pack(anchor="w", pady=(8,2))
            if isinstance(items, list):
                for it in items[:30]:
                    name = it.get("name","") or str(it)
                    ctk.CTkLabel(box, text=f"  • {name}", font=F_SM,
                                 text_color=TEXT, anchor="w").pack(fill="x")
            else:
                ctk.CTkLabel(box, text=f"  {items}", font=F_SM,
                             text_color=TEXT, anchor="w").pack(fill="x")
        ctk.CTkButton(self, text="✕ Close", height=34, fg_color=BG2,
                      text_color=TEXT2, command=self.destroy).pack(fill="x", padx=20, pady=10)
