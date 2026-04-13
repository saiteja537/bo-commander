"""
gui/pages/broken_objects.py  —  BO Commander Broken Objects  v2.0
Production UI for detecting and resolving broken SAP BO objects with:
  • Live CMS scan via get_broken_objects()
  • Severity classification (name markers, orphan connections)
  • Kind filter tabs
  • Detail drawer per object
  • Bulk delete with confirmation
  • Export CSV
  • AI Fix suggestion via Gemini
"""

import csv
import threading
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
    "Webi":          ("📊", BLUE),
    "CrystalReport": ("💎", VIOLET),
    "Excel":         ("📗", GREEN),
    "Pdf":           ("📄", RED),
    "Universe":      ("🌐", CYAN),
    "Connection":    ("🔌", AMBER),
    "Folder":        ("📁", TEXT2),
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

# AI helper
try:
    from ai.gemini_client import ai_client
    HAS_AI = True
except Exception:
    HAS_AI = False


class _DetailDrawer(ctk.CTkToplevel):
    def __init__(self, parent, obj):
        super().__init__(parent)
        self.title(f"🔨  {obj.get('name','')[:50]}")
        self.geometry("520x380")
        self.configure(fg_color=BG0)
        self.resizable(False, False)
        self.grab_set()
        self._build(obj)

    def _build(self, o):
        kind  = o.get("kind","")
        icon, kcolor = KIND_META.get(kind, ("📋", TEXT2))

        hdr = ctk.CTkFrame(self, fg_color=BG2, corner_radius=0, height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=f"{icon}  {o.get('name','')[:55]}",
                     font=("Segoe UI", 12, "bold"), text_color=TEXT).pack(side="left", padx=14)
        ctk.CTkLabel(hdr, text=kind, font=("Segoe UI", 10),
                     text_color=kcolor).pack(side="right", padx=14)

        body = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0)
        body.pack(fill="both", expand=True)

        def row(k, v, vc=TEXT):
            f = ctk.CTkFrame(body, fg_color="transparent", height=30)
            f.pack(fill="x", padx=16, pady=2)
            f.pack_propagate(False)
            ctk.CTkLabel(f, text=k, width=150, anchor="w",
                         font=("Segoe UI", 10, "bold"), text_color=TEXT2).pack(side="left")
            ctk.CTkLabel(f, text=str(v)[:120], anchor="w",
                         font=("Segoe UI", 10), text_color=vc).pack(side="left")

        row("Object ID",   o.get("id","—"))
        row("Name",        o.get("name","—"))
        row("Kind",        o.get("kind","—"),   kcolor)
        row("Owner",       o.get("owner","—"))
        row("Cause",       o.get("cause","—"),  RED)
        row("Suggested Fix", o.get("fix","—"),  GREEN)
        row("Last Updated",str(o.get("updated","—"))[:19])

        fix_frame = ctk.CTkFrame(body, fg_color=BG2, corner_radius=6)
        fix_frame.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(fix_frame, text="💡  Recommended Action",
                     font=("Segoe UI", 10, "bold"), text_color=AMBER).pack(anchor="w", padx=12, pady=(8,2))
        ctk.CTkLabel(fix_frame,
                     text=o.get("fix", "Review the object in CMC and check its connections or parent folder."),
                     font=("Segoe UI", 10), text_color=TEXT, wraplength=440,
                     justify="left").pack(anchor="w", padx=12, pady=(0,10))

        ctk.CTkButton(self, text="Close", width=90, height=32,
                      fg_color=BG2, text_color=TEXT2,
                      command=self.destroy).pack(pady=10)


class _AIFixWindow(ctk.CTkToplevel):
    """AI batch fix suggestions for all broken objects."""
    def __init__(self, parent, objects):
        super().__init__(parent)
        self.title("🤖  AI Broken Object Fix Advisor")
        self.geometry("700x520")
        self.configure(fg_color=BG0)
        self.grab_set()
        self._build(objects)
        threading.Thread(target=self._analyze, args=(objects,), daemon=True).start()

    def _build(self, objects):
        hdr = ctk.CTkFrame(self, fg_color=BG2, corner_radius=0, height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="🤖  AI Broken Object Fix Advisor",
                     font=("Segoe UI", 13, "bold"), text_color=CYAN).pack(side="left", padx=14)
        ctk.CTkLabel(hdr, text=f"{len(objects)} objects",
                     font=F["small"], text_color=TEXT2).pack(side="right", padx=14)

        info = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=36)
        info.pack(fill="x")
        info.pack_propagate(False)
        ctk.CTkLabel(info, text="⚠  Review AI suggestions before applying to production",
                     font=("Segoe UI", 9), text_color=AMBER).pack(side="left", padx=14)

        self._box = ctk.CTkTextbox(self, font=("Segoe UI", 12),
                                    fg_color=BG1, text_color=TEXT,
                                    border_color=BG2, border_width=1, wrap="word")
        self._box.pack(fill="both", expand=True, padx=14, pady=10)
        self._box.insert("end", "⏳  Gemini AI is analysing broken objects…\n")
        self._box.configure(state="disabled")

        ctk.CTkButton(self, text="Close", width=90, height=32,
                      fg_color=BG2, text_color=TEXT2,
                      command=self.destroy).pack(pady=(0,12))

    def _analyze(self, objects):
        try:
            sample = objects[:20]
            lines  = "\n".join(
                f"  [{o.get('kind','?')}] {o.get('name','')} — cause: {o.get('cause','?')}"
                for o in sample)
            prompt = (
                "You are an SAP BusinessObjects BI 4.3 expert.\n\n"
                f"These {len(objects)} objects are broken in the CMS:\n{lines}\n\n"
                "For each category of breakage, provide:\n"
                "1. ROOT CAUSE — what causes this in SAP BO\n"
                "2. HOW TO IDENTIFY — CMC location, query\n"
                "3. FIX STEPS — numbered, specific\n"
                "4. PREVENTION\n\n"
                "Be specific. Use Windows paths. Plain text, no markdown."
            )
            resp = ai_client.get_response(prompt)
        except Exception as e:
            resp = f"AI unavailable: {e}\n\nManual steps:\n"
            resp += "1. Open CMC → Objects\n"
            resp += "2. Search for objects with [broken] or [invalid] in name\n"
            resp += "3. Check associated universes and connections\n"
            resp += "4. Delete or rename broken objects\n"

        try:
            if self.winfo_exists():
                self.after(0, self._set, resp)
        except Exception:
            pass

    def _set(self, text):
        self._box.configure(state="normal")
        self._box.delete("1.0","end")
        self._box.insert("end", text)
        self._box.configure(state="disabled")


class BrokenObjectsPage(ctk.CTkFrame):

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=BG0, corner_radius=0, **kw)
        _PAGE_REF[0] = self.winfo_toplevel()
        self._all      = []
        self._type_f   = "All"
        self._destroyed = False
        self._sel_ids  = set()
        self._build()

    def destroy(self):
        self._destroyed = True
        super().destroy()

    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="🔨  Broken Objects",
                     font=("Segoe UI", 18, "bold"),
                     text_color=CYAN).pack(side="left", padx=18)
        self._status_lbl = ctk.CTkLabel(hdr, text="Click Scan to detect broken objects",
                                         font=F["small"], text_color=TEXT2)
        self._status_lbl.pack(side="right", padx=18)
        ctk.CTkButton(hdr, text="🔍 Scan", width=84, height=30,
                      fg_color=BLUE, text_color="white", font=F["small"],
                      hover_color="#2563eb", command=self._scan).pack(side="right")
        ctk.CTkButton(hdr, text="🗑 Delete", width=80, height=30,
                      fg_color=RED, text_color="white", font=F["small"],
                      hover_color="#dc2626",
                      command=self._delete_selected).pack(side="right", padx=(0,4))
        ctk.CTkButton(hdr, text="⬇ CSV", width=68, height=30,
                      fg_color=GREEN, text_color="white", font=F["small"],
                      hover_color="#16a34a",
                      command=self._export_csv).pack(side="right", padx=(0,4))
        if HAS_AI:
            ctk.CTkButton(hdr, text="🤖 AI Fix", width=80, height=30,
                          fg_color=VIOLET, text_color="white", font=F["small"],
                          hover_color="#7c3aed",
                          command=self._ai_fix).pack(side="right", padx=(0,4))

        # Summary tiles
        tiles = ctk.CTkFrame(self, fg_color="transparent", height=70)
        tiles.pack(fill="x", padx=14, pady=(10,0))
        tiles.pack_propagate(False)
        self._tiles = {}
        for key, lbl, col in [
            ("total",   "Total Broken",   RED),
            ("webi",    "WebI",           BLUE),
            ("crystal", "Crystal",        VIOLET),
            ("universe","Universe",       CYAN),
            ("other",   "Other",          AMBER),
        ]:
            t = ctk.CTkFrame(tiles, fg_color=BG1, corner_radius=8,
                             border_color=BG2, border_width=1)
            t.pack(side="left", padx=(0,8), fill="both", expand=True)
            ctk.CTkLabel(t, text=lbl, font=("Segoe UI", 9),
                         text_color=TEXT2).pack(pady=(8,0))
            v = ctk.CTkLabel(t, text="—", font=("Segoe UI", 22, "bold"),
                             text_color=col)
            v.pack(pady=(0,8))
            self._tiles[key] = v

        # Filter bar
        fbar = ctk.CTkFrame(self, fg_color=BG1, height=44)
        fbar.pack(fill="x", padx=0, pady=(8,0))
        fbar.pack_propagate(False)

        # Kind tabs
        self._kind_btns = {}
        for tid, icon, lbl, col in [
            ("All",           "📋", "All",     CYAN),
            ("Webi",          "📊", "WebI",    BLUE),
            ("CrystalReport", "💎", "Crystal", VIOLET),
            ("Universe",      "🌐", "Universe",CYAN),
            ("Connection",    "🔌", "Connection",AMBER),
        ]:
            b = ctk.CTkButton(fbar, text=f"{icon} {lbl}",
                              width=104, height=28, corner_radius=6,
                              font=F["small"],
                              fg_color=col if tid=="All" else BG2,
                              hover_color=col, text_color=TEXT,
                              command=lambda t=tid, c=col: self._set_type(t, c))
            b.pack(side="left", padx=(8 if tid=="All" else 3, 0))
            self._kind_btns[tid] = (b, col)

        # Search
        self._q = ctk.StringVar()
        self._q.trace_add("write", lambda *_: self._render())
        ctk.CTkEntry(fbar, textvariable=self._q,
                     placeholder_text="🔎  Search by name, owner…",
                     width=240, height=28,
                     fg_color=BG2, border_color=BG2,
                     text_color=TEXT, font=F["small"]).pack(side="right", padx=10)

        # Table header
        thead = ctk.CTkFrame(self, fg_color=BG2, height=30)
        thead.pack(fill="x", padx=0, pady=(8,0))
        thead.pack_propagate(False)
        for lbl, w in [("  ●",28),("Object Name",310),("Type",110),
                        ("Owner",110),("Cause",180),("Suggested Fix",200),("Updated",140)]:
            ctk.CTkLabel(thead, text=lbl, width=w, anchor="w",
                         font=("Segoe UI", 10, "bold"),
                         text_color=TEXT2).pack(side="left", padx=(8,0))

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True)

        self._status_bar = ctk.CTkLabel(self, text="", font=F["small"],
                                         text_color=TEXT2)
        self._status_bar.pack(anchor="w", padx=14, pady=(0,6))

    # ── data ──────────────────────────────────────────────────────────────────
    def _scan(self):
        self._status_lbl.configure(text="⏳ Scanning CMS…")
        for w in self._scroll.winfo_children():
            w.destroy()
        self._all = []
        self._sel_ids.clear()
        _bg(bo_session.get_broken_objects, self._on_scanned)

    def _on_scanned(self, items):
        if self._destroyed: return
        self._all = items or []
        self._update_tiles()
        self._render()
        n = len(self._all)
        self._status_lbl.configure(
            text=f"{'⚠ ' if n > 0 else '✅ '}{n} broken object{'s' if n!=1 else ''} found")

    def _update_tiles(self):
        kinds = [o.get("kind","") for o in self._all]
        self._tiles["total"].configure(text=str(len(self._all)))
        self._tiles["webi"].configure(text=str(kinds.count("Webi")))
        self._tiles["crystal"].configure(text=str(kinds.count("CrystalReport")))
        self._tiles["universe"].configure(text=str(kinds.count("Universe")))
        other = sum(1 for k in kinds if k not in ("Webi","CrystalReport","Universe"))
        self._tiles["other"].configure(text=str(other))

    def _set_type(self, tid, col):
        self._type_f = tid
        for t, (b, c) in self._kind_btns.items():
            b.configure(fg_color=c if t==tid else BG2)
        self._render()

    def _render(self):
        if self._destroyed: return
        q = self._q.get().lower()
        shown = [
            o for o in self._all
            if (self._type_f == "All" or o.get("kind","") == self._type_f)
            and (not q or q in o.get("name","").lower()
                       or q in o.get("owner","").lower()
                       or q in o.get("cause","").lower())
        ]
        try:
            for w in self._scroll.winfo_children():
                w.destroy()
        except Exception:
            return

        if not shown:
            msg = ("No broken objects found — system is clean ✅" if self._all == []
                   else "No objects match the current filter."
                   if self._all else "Click Scan to detect broken objects.")
            ctk.CTkLabel(self._scroll, text=msg,
                         font=F["body"], text_color=TEXT2).pack(pady=40)
            self._status_bar.configure(text="0 shown")
            return

        self._sel_ids.clear()
        for i, o in enumerate(shown):
            self._row(o, i)
        self._status_bar.configure(
            text=f"Showing {len(shown)} of {len(self._all)} broken objects")

    def _row(self, o, idx):
        kind  = o.get("kind","")
        icon, kcolor = KIND_META.get(kind, ("📋", TEXT2))
        bg = BG1 if idx % 2 == 0 else "transparent"

        row = ctk.CTkFrame(self._scroll, fg_color=bg, corner_radius=4, height=34)
        row.pack(fill="x", pady=1, padx=4)
        row.pack_propagate(False)

        sel_var = ctk.BooleanVar()
        oid = str(o.get("id",""))
        def on_toggle(v=sel_var, sid=oid):
            if v.get(): self._sel_ids.add(sid)
            else:       self._sel_ids.discard(sid)
        ctk.CTkCheckBox(row, text="", variable=sel_var,
                        width=24, checkbox_width=16, checkbox_height=16,
                        command=on_toggle).pack(side="left", padx=(6,2))

        # Name (clickable)
        name_lbl = ctk.CTkLabel(row,
                                 text=f"{icon}  {o.get('name','')[:50]}",
                                 width=306, anchor="w",
                                 font=("Segoe UI", 11, "bold"),
                                 text_color=RED, cursor="hand2")
        name_lbl.pack(side="left", padx=2)
        name_lbl.bind("<Button-1>", lambda e, obj=o: _DetailDrawer(self.winfo_toplevel(), obj))
        name_lbl.bind("<Enter>",    lambda e, l=name_lbl: l.configure(text_color=AMBER))
        name_lbl.bind("<Leave>",    lambda e, l=name_lbl: l.configure(text_color=RED))

        for val, w, col in [
            (kind[:18],                      108, kcolor),
            (o.get("owner","")[:18],         108, TEXT2),
            (o.get("cause","")[:28],         178, AMBER),
            (o.get("fix","")[:32],           198, GREEN),
            (str(o.get("updated",""))[:16],  138, TEXT2),
        ]:
            ctk.CTkLabel(row, text=str(val), width=w, anchor="w",
                         font=("Segoe UI", 10),
                         text_color=col).pack(side="left", padx=(4,0))

        ctk.CTkButton(row, text="⋯", width=28, height=24, corner_radius=4,
                      fg_color=BG2, text_color=TEXT2, font=("Segoe UI", 12),
                      hover_color=BLUE,
                      command=lambda obj=o: _DetailDrawer(self.winfo_toplevel(), obj)
                      ).pack(side="right", padx=6)

    # ── actions ───────────────────────────────────────────────────────────────
    def _delete_selected(self):
        if not self._sel_ids:
            messagebox.showinfo("Select", "Tick objects to delete.", parent=self)
            return
        if not messagebox.askyesno(
                "Confirm Delete",
                f"Permanently delete {len(self._sel_ids)} object(s)?\n"
                "This action cannot be undone.", parent=self):
            return
        ids = list(self._sel_ids)
        self._status_lbl.configure(text=f"⏳ Deleting {len(ids)} objects…")
        def _do():
            ok = sum(1 for oid in ids if bo_session.delete_object(oid)[0])
            return ok
        def _done(ok):
            self._status_lbl.configure(text=f"✅ Deleted {ok}/{len(ids)}")
            self._scan()
        _bg(_do, _done)

    def _export_csv(self):
        if not self._all:
            messagebox.showinfo("No data", "Run Scan first.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            title="Export CSV",
            defaultextension=".csv",
            filetypes=[("CSV","*.csv")],
            initialfile=f"bo_broken_objects_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            parent=self)
        if not path: return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(
                    f, fieldnames=["id","name","kind","owner","cause","fix","updated"],
                    extrasaction="ignore")
                w.writeheader()
                w.writerows(self._all)
            self._status_bar.configure(
                text=f"✅ Exported {len(self._all)} rows → {path}")
        except Exception as e:
            self._status_bar.configure(text=f"❌ Export failed: {e}")

    def _ai_fix(self):
        if not self._all:
            messagebox.showinfo("No data", "Run Scan first.", parent=self)
            return
        _AIFixWindow(self.winfo_toplevel(), self._all)