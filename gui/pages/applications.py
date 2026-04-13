"""
gui/pages/applications.py  —  BO Commander Applications  v2.0
Production UI for deployed SAP BO application objects with:
  • Type-grouped tiles with counts
  • Detail drawer (ID, description, owner, dates)
  • Search + type filter
  • Export CSV
  • Delete selected
"""

import threading
import csv
from tkinter import messagebox, filedialog
from datetime import datetime

import customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS
F = Config.FONTS

BG0   = C["bg_primary"]
BG1   = C["bg_secondary"]
BG2   = C["bg_tertiary"]
CYAN  = "#22d3ee"
BLUE  = C["primary"]
VIOLET= C["secondary"]
GREEN = C["success"]
AMBER = C["warning"]
RED   = C["danger"]
TEXT  = C["text_primary"]
TEXT2 = C["text_secondary"]

KIND_META = {
    "Application":      ("🖥",  "Application",  BLUE),
    "AnalyticsApp":     ("📊",  "Analytics",    VIOLET),
    "WebIntelligence":  ("🌐",  "WebI App",     CYAN),
    "LCM.Application":  ("🔄",  "LCM App",      AMBER),
    "Publication":      ("📨",  "Publication",  GREEN),
}

_PAGE_REF = [None]

def _bg(fn, cb):
    ref = _PAGE_REF[0]
    def _run():
        try:    r = fn()
        except Exception: r = None
        if ref:
            try: ref.after(0, lambda res=r: cb(res))
            except Exception: pass
    threading.Thread(target=_run, daemon=True).start()


class _DetailDrawer(ctk.CTkToplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.title(f"📦  {app.get('name','')[:50]}")
        self.geometry("480x340")
        self.configure(fg_color=BG0)
        self.resizable(False, False)
        self.grab_set()
        self._build(app)

    def _build(self, a):
        hdr = ctk.CTkFrame(self, fg_color=BG2, corner_radius=0, height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        kind  = a.get("kind","")
        icon, lbl, kcolor = KIND_META.get(kind, ("📦", kind, TEXT2))
        ctk.CTkLabel(hdr, text=f"{icon}  {a.get('name','')}",
                     font=("Segoe UI", 13, "bold"),
                     text_color=TEXT).pack(side="left", padx=14)
        ctk.CTkLabel(hdr, text=lbl, font=("Segoe UI", 10),
                     text_color=kcolor).pack(side="right", padx=14)

        body = ctk.CTkScrollableFrame(self, fg_color=BG1, corner_radius=0)
        body.pack(fill="both", expand=True, padx=0, pady=0)

        def row(k, v, vc=TEXT):
            f = ctk.CTkFrame(body, fg_color="transparent", height=32)
            f.pack(fill="x", padx=14, pady=2)
            f.pack_propagate(False)
            ctk.CTkLabel(f, text=k, width=140, anchor="w",
                         font=("Segoe UI", 10, "bold"),
                         text_color=TEXT2).pack(side="left")
            ctk.CTkLabel(f, text=str(v)[:120], anchor="w",
                         font=("Segoe UI", 10),
                         text_color=vc).pack(side="left", fill="x", expand=True)

        row("ID",          a.get("id","—"))
        row("Name",        a.get("name","—"))
        row("Kind",        a.get("kind","—"),  kcolor)
        row("Owner",       a.get("owner","—"))
        row("Description", a.get("desc","—")  or "—")
        row("Last Updated",str(a.get("updated","—"))[:19])

        ctk.CTkButton(self, text="Close", width=90, height=32,
                      fg_color=BG2, text_color=TEXT2,
                      command=self.destroy).pack(pady=10)


class ApplicationsPage(ctk.CTkFrame):

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=BG0, corner_radius=0, **kw)
        _PAGE_REF[0] = self.winfo_toplevel()
        self._all      = []
        self._type_f   = "All"
        self._destroyed = False
        self._build()
        self._load()

    def destroy(self):
        self._destroyed = True
        super().destroy()

    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="📦  Applications",
                     font=("Segoe UI", 18, "bold"),
                     text_color=CYAN).pack(side="left", padx=18)
        self._status_lbl = ctk.CTkLabel(hdr, text="", font=F["small"],
                                         text_color=TEXT2)
        self._status_lbl.pack(side="right", padx=18)
        ctk.CTkButton(hdr, text="⟳ Refresh", width=90, height=30,
                      fg_color=BG2, text_color=TEXT2, font=F["small"],
                      hover_color=BG0, command=self._load).pack(side="right")
        ctk.CTkButton(hdr, text="⬇ CSV", width=74, height=30,
                      fg_color=GREEN, text_color="white", font=F["small"],
                      hover_color="#16a34a",
                      command=self._export_csv).pack(side="right", padx=(0,6))
        ctk.CTkButton(hdr, text="🗑 Delete", width=80, height=30,
                      fg_color=RED, text_color="white", font=F["small"],
                      hover_color="#dc2626",
                      command=self._delete_sel).pack(side="right", padx=(0,4))

        # Stat tiles
        tiles = ctk.CTkFrame(self, fg_color="transparent", height=72)
        tiles.pack(fill="x", padx=14, pady=(10,0))
        tiles.pack_propagate(False)
        self._tiles = {}
        for key, label, col in [
            ("total","Total",     CYAN),
            ("app",  "Apps",      BLUE),
            ("webi", "WebI",      VIOLET),
            ("pub",  "Publications", GREEN),
            ("lcm",  "LCM",       AMBER),
        ]:
            t = ctk.CTkFrame(tiles, fg_color=BG1, corner_radius=8,
                             border_color=BG2, border_width=1)
            t.pack(side="left", padx=(0,8), fill="both", expand=True)
            ctk.CTkLabel(t, text=label, font=("Segoe UI", 9),
                         text_color=TEXT2).pack(pady=(8,0))
            v = ctk.CTkLabel(t, text="—", font=("Segoe UI", 22, "bold"),
                             text_color=col)
            v.pack(pady=(0,8))
            self._tiles[key] = v

        # Filter bar
        fbar = ctk.CTkFrame(self, fg_color=BG1, height=44)
        fbar.pack(fill="x", padx=0, pady=(10,0))
        fbar.pack_propagate(False)

        # Type buttons
        self._type_btns = {}
        for tid, icon, lbl, col in [
            ("All",           "📦", "All",         CYAN),
            ("Application",   "🖥",  "Apps",        BLUE),
            ("WebIntelligence","🌐","WebI",         VIOLET),
            ("Publication",   "📨", "Publications", GREEN),
            ("LCM.Application","🔄","LCM",         AMBER),
        ]:
            b = ctk.CTkButton(fbar, text=f"{icon} {lbl}",
                              width=104, height=28, corner_radius=6,
                              font=F["small"],
                              fg_color=col if tid == "All" else BG2,
                              hover_color=col, text_color=TEXT,
                              command=lambda t=tid, c=col: self._set_type(t, c))
            b.pack(side="left", padx=(8 if tid=="All" else 3, 0))
            self._type_btns[tid] = (b, col)

        # Search
        self._q = ctk.StringVar()
        self._q.trace_add("write", lambda *_: self._render())
        ctk.CTkEntry(fbar, textvariable=self._q,
                     placeholder_text="🔎  Search by name, owner…",
                     width=240, height=28,
                     fg_color=BG2, border_color=BG2,
                     text_color=TEXT, font=F["small"]).pack(side="right", padx=10)

        # Table header
        thead = ctk.CTkFrame(self, fg_color=BG2, corner_radius=0, height=32)
        thead.pack(fill="x", padx=0, pady=(8,0))
        thead.pack_propagate(False)
        for lbl, w in [("  ●", 28),("Name",320),("Kind",130),
                        ("Owner",120),("Last Updated",150),("",60)]:
            ctk.CTkLabel(thead, text=lbl, width=w, anchor="w",
                         font=("Segoe UI", 10, "bold"),
                         text_color=TEXT2).pack(side="left", padx=(8,0))

        # Scroll
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=0, pady=0)

        self._status_bar = ctk.CTkLabel(self, text="", font=F["small"],
                                         text_color=TEXT2)
        self._status_bar.pack(anchor="w", padx=14, pady=(0,6))

        # selection tracking
        self._sel_ids = set()

    # ── data ──────────────────────────────────────────────────────────────────
    def _load(self):
        self._status_lbl.configure(text="⏳ Loading…")
        for w in self._scroll.winfo_children():
            w.destroy()
        _bg(bo_session.get_all_applications, self._on_loaded)

    def _on_loaded(self, data):
        if self._destroyed: return
        self._all = data or []
        self._update_tiles()
        self._render()
        self._status_lbl.configure(text=f"{len(self._all)} applications")

    def _update_tiles(self):
        kinds = [a.get("kind","") for a in self._all]
        self._tiles["total"].configure(text=str(len(self._all)))
        self._tiles["app"].configure(text=str(kinds.count("Application")))
        self._tiles["webi"].configure(text=str(sum(1 for k in kinds if "WebIntelligence" in k or "Analytics" in k)))
        self._tiles["pub"].configure(text=str(kinds.count("Publication")))
        self._tiles["lcm"].configure(text=str(kinds.count("LCM.Application")))

    def _set_type(self, tid, col):
        self._type_f = tid
        for t, (b, c) in self._type_btns.items():
            b.configure(fg_color=c if t == tid else BG2)
        self._render()

    def _render(self):
        if self._destroyed: return
        q = self._q.get().lower()
        shown = [
            a for a in self._all
            if (self._type_f == "All" or a.get("kind","") == self._type_f)
            and (not q or q in a.get("name","").lower()
                       or q in a.get("owner","").lower()
                       or q in a.get("kind","").lower())
        ]
        try:
            for w in self._scroll.winfo_children():
                w.destroy()
        except Exception:
            return

        if not shown:
            ctk.CTkLabel(self._scroll,
                         text="No applications found." if self._all else "Not connected — click Refresh.",
                         font=F["body"], text_color=TEXT2).pack(pady=40)
            self._status_bar.configure(text="0 shown")
            return

        self._sel_ids.clear()
        for i, a in enumerate(shown):
            self._row(a, i)

        self._status_bar.configure(
            text=f"Showing {len(shown)} of {len(self._all)} applications")

    def _row(self, a, idx):
        kind  = a.get("kind","")
        icon, _, kcolor = KIND_META.get(kind, ("📦", kind, TEXT2))
        bg = BG1 if idx % 2 == 0 else "transparent"

        row = ctk.CTkFrame(self._scroll, fg_color=bg, corner_radius=4, height=36)
        row.pack(fill="x", pady=1, padx=4)
        row.pack_propagate(False)

        # Checkbox
        sel_var = ctk.BooleanVar(value=False)
        def on_toggle(v=sel_var, aid=str(a.get("id",""))):
            if v.get(): self._sel_ids.add(aid)
            else:       self._sel_ids.discard(aid)
        ctk.CTkCheckBox(row, text="", variable=sel_var,
                        width=24, checkbox_width=16, checkbox_height=16,
                        command=on_toggle).pack(side="left", padx=(8,4))

        # Name
        name_lbl = ctk.CTkLabel(row, text=f"{icon}  {a.get('name','')[:55]}",
                                  width=316, anchor="w",
                                  font=("Segoe UI", 11, "bold"),
                                  text_color=TEXT, cursor="hand2")
        name_lbl.pack(side="left", padx=2)
        name_lbl.bind("<Button-1>", lambda e, app=a: _DetailDrawer(self.winfo_toplevel(), app))
        name_lbl.bind("<Enter>",    lambda e, l=name_lbl: l.configure(text_color=CYAN))
        name_lbl.bind("<Leave>",    lambda e, l=name_lbl: l.configure(text_color=TEXT))

        # Kind badge
        ctk.CTkLabel(row, text=kind[:22], width=128, anchor="w",
                     font=("Segoe UI", 10),
                     text_color=kcolor).pack(side="left", padx=2)

        # Owner
        ctk.CTkLabel(row, text=a.get("owner","")[:20], width=118, anchor="w",
                     font=("Segoe UI", 10), text_color=TEXT2).pack(side="left")

        # Updated
        ctk.CTkLabel(row, text=str(a.get("updated",""))[:16], width=148, anchor="w",
                     font=("Segoe UI", 10), text_color=TEXT2).pack(side="left")

        # Detail button
        ctk.CTkButton(row, text="⋯", width=28, height=24, corner_radius=4,
                      fg_color=BG2, text_color=TEXT2, font=("Segoe UI", 12),
                      hover_color=BLUE,
                      command=lambda app=a: _DetailDrawer(self.winfo_toplevel(), app)
                      ).pack(side="right", padx=6)

    # ── actions ───────────────────────────────────────────────────────────────
    def _export_csv(self):
        if not self._all:
            return
        path = filedialog.asksaveasfilename(
            title="Export CSV", defaultextension=".csv",
            filetypes=[("CSV","*.csv")],
            initialfile=f"bo_applications_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            parent=self)
        if not path: return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["id","name","kind","owner","desc","updated"])
                w.writeheader()
                w.writerows(self._all)
            self._status_bar.configure(
                text=f"✅ Exported {len(self._all)} rows → {path}")
        except Exception as e:
            self._status_bar.configure(text=f"❌ Export failed: {e}")

    def _delete_sel(self):
        if not self._sel_ids:
            messagebox.showinfo("Select", "Tick checkboxes to select applications.", parent=self)
            return
        if not messagebox.askyesno(
                "Confirm Delete",
                f"Permanently delete {len(self._sel_ids)} application(s)?\n"
                "This cannot be undone.", parent=self):
            return
        self._status_lbl.configure(text="⏳ Deleting…")
        ids = list(self._sel_ids)
        def _do():
            ok = sum(1 for aid in ids if bo_session.delete_object(aid)[0])
            return ok
        def _done(ok):
            self._status_lbl.configure(text=f"✅ Deleted {ok} / {len(ids)}")
            self._load()
        _bg(_do, _done)