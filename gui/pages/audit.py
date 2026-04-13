"""
gui/pages/audit.py  —  BO Commander Audit Events  v2.0
Production UI for SAP BO audit log viewer with:
  • Live query from CMS audit tables
  • Day-range selector + user filter + keyword search
  • Summary tiles with event counts per type
  • Activity sparkline (hourly bar chart on canvas)
  • Per-row hover highlight
  • Export CSV
  • Event detail drawer
"""

import csv
import threading
from collections import Counter
from datetime import datetime
from tkinter import messagebox, filedialog
import tkinter as tk

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

KIND_COLORS = {
    "AuditEvent":    CYAN,
    "Webi":          BLUE,
    "CrystalReport": VIOLET,
    "User":          GREEN,
    "UserGroup":     AMBER,
    "Session":       "#06b6d4",
    "CMS":           RED,
}


class _EventDetail(ctk.CTkToplevel):
    def __init__(self, parent, rec):
        super().__init__(parent)
        self.title("Audit Event Detail")
        self.geometry("520x320")
        self.configure(fg_color=BG0)
        self.resizable(False, False)
        self.grab_set()
        self._build(rec)

    def _build(self, r):
        hdr = ctk.CTkFrame(self, fg_color=BG2, corner_radius=0, height=44)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=f"📋  {r.get('name','')[:55]}",
                     font=("Segoe UI", 12, "bold"), text_color=TEXT).pack(side="left", padx=14)

        body = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0)
        body.pack(fill="both", expand=True)

        def row(k, v, vc=TEXT):
            f = ctk.CTkFrame(body, fg_color="transparent", height=30)
            f.pack(fill="x", padx=16, pady=2)
            f.pack_propagate(False)
            ctk.CTkLabel(f, text=k, width=130, anchor="w",
                         font=("Segoe UI", 10, "bold"), text_color=TEXT2).pack(side="left")
            ctk.CTkLabel(f, text=str(v)[:120], anchor="w",
                         font=("Segoe UI", 10), text_color=vc).pack(side="left")

        row("Timestamp",   str(r.get("timestamp",""))[:19].replace("T"," "))
        row("Event Name",  r.get("name","—"))
        row("User",        r.get("user","—"),    GREEN)
        row("Kind",        r.get("kind","—"),    KIND_COLORS.get(r.get("kind",""), TEXT2))
        row("Status",      r.get("status","—"),  GREEN if "success" in str(r.get("status","")).lower() else AMBER)
        row("Description", r.get("description","—") or "—")
        row("Object ID",   r.get("id","—"))

        ctk.CTkButton(self, text="Close", width=90, height=32,
                      fg_color=BG2, text_color=TEXT2,
                      command=self.destroy).pack(pady=10)


class _ActivityChart(ctk.CTkFrame):
    """Hourly activity bar chart drawn on a canvas."""
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=BG2, corner_radius=8, **kw)
        self._canvas = tk.Canvas(self, bg=BG2, highlightthickness=0, height=60)
        self._canvas.pack(fill="both", expand=True, padx=8, pady=6)

    def draw(self, records):
        self._canvas.delete("all")
        if not records:
            self._canvas.create_text(10, 30, text="No data",
                                      fill=TEXT2, font=("Segoe UI",9), anchor="w")
            return
        # Count by hour of day
        counts = Counter()
        for r in records:
            ts = str(r.get("timestamp",""))
            try:
                h = int(ts[11:13])
                counts[h] += 1
            except Exception:
                pass
        if not counts:
            return
        max_v = max(counts.values()) or 1
        w = self._canvas.winfo_width() or 600
        bar_w = max(4, (w - 40) // 24)
        for h in range(24):
            v = counts.get(h, 0)
            x = 20 + h * bar_w
            bar_h = int((v / max_v) * 44)
            col = RED if v == max(counts.values()) else BLUE
            if bar_h > 0:
                self._canvas.create_rectangle(
                    x, 54 - bar_h, x + bar_w - 2, 54,
                    fill=col, outline="")
            # hour label every 6h
            if h % 6 == 0:
                self._canvas.create_text(x, 57, text=f"{h:02d}h",
                                          fill=TEXT2, font=("Segoe UI",7), anchor="n")


class AuditPage(ctk.CTkFrame):

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=BG0, corner_radius=0, **kw)
        self._records  = []
        self._loading  = False
        self._destroyed= False
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
        ctk.CTkLabel(hdr, text="📋  Audit Events",
                     font=("Segoe UI", 18, "bold"),
                     text_color=CYAN).pack(side="left", padx=18)
        self._status_lbl = ctk.CTkLabel(hdr, text="", font=F["small"],
                                         text_color=TEXT2)
        self._status_lbl.pack(side="right", padx=18)
        self._refresh_btn = ctk.CTkButton(
            hdr, text="⟳ Refresh", width=90, height=30,
            fg_color=BG2, text_color=TEXT2, font=F["small"],
            hover_color=BG0, command=self._load)
        self._refresh_btn.pack(side="right")
        ctk.CTkButton(hdr, text="⬇ CSV", width=74, height=30,
                      fg_color=GREEN, text_color="white", font=F["small"],
                      hover_color="#16a34a",
                      command=self._export_csv).pack(side="right", padx=(0,6))

        # Summary tiles
        self._tile_frame = ctk.CTkFrame(self, fg_color="transparent", height=72)
        self._tile_frame.pack(fill="x", padx=14, pady=(10,0))
        self._tile_frame.pack_propagate(False)
        self._tiles = {}
        for key, lbl, col in [
            ("total",   "Total Events",  CYAN),
            ("users_n", "Unique Users",  BLUE),
            ("kinds_n", "Event Types",   VIOLET),
            ("today",   "Today",         GREEN),
            ("errors",  "Errors",        RED),
        ]:
            t = ctk.CTkFrame(self._tile_frame, fg_color=BG1, corner_radius=8,
                             border_color=BG2, border_width=1)
            t.pack(side="left", padx=(0,8), fill="both", expand=True)
            ctk.CTkLabel(t, text=lbl, font=("Segoe UI", 9),
                         text_color=TEXT2).pack(pady=(8,0))
            v = ctk.CTkLabel(t, text="—", font=("Segoe UI", 22, "bold"),
                             text_color=col)
            v.pack(pady=(0,8))
            self._tiles[key] = v

        # Activity chart
        self._chart = _ActivityChart(self, height=70)
        self._chart.pack(fill="x", padx=14, pady=(8,0))

        # Filter bar
        fbar = ctk.CTkFrame(self, fg_color=BG1, height=46)
        fbar.pack(fill="x", padx=0, pady=(8,0))
        fbar.pack_propagate(False)

        ctk.CTkLabel(fbar, text="Days:", font=F["small"],
                     text_color=TEXT2).pack(side="left", padx=(14,4))
        self._days_var = ctk.StringVar(value="7")
        ctk.CTkSegmentedButton(
            fbar, values=["1","7","14","30","90"],
            variable=self._days_var,
            fg_color=BG2, selected_color=CYAN,
            selected_hover_color="#06b6d4",
            font=F["small"], height=28,
            width=220).pack(side="left", padx=(0,12))

        ctk.CTkLabel(fbar, text="User:", font=F["small"],
                     text_color=TEXT2).pack(side="left", padx=(0,4))
        self._user_entry = ctk.CTkEntry(
            fbar, width=150, height=28,
            placeholder_text="all users",
            fg_color=BG2, border_color=BG2,
            text_color=TEXT, font=F["small"])
        self._user_entry.pack(side="left", padx=(0,8))

        ctk.CTkLabel(fbar, text="Search:", font=F["small"],
                     text_color=TEXT2).pack(side="left", padx=(0,4))
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filter())
        ctk.CTkEntry(fbar, textvariable=self._search_var,
                     width=200, height=28,
                     placeholder_text="filter…",
                     fg_color=BG2, border_color=BG2,
                     text_color=TEXT, font=F["small"]).pack(side="left")

        ctk.CTkButton(fbar, text="Apply", width=74, height=28,
                      fg_color=CYAN, text_color=BG0,
                      hover_color="#06b6d4", font=F["small"],
                      command=self._load).pack(side="left", padx=8)

        # Table header
        thead = ctk.CTkFrame(self, fg_color=BG2, height=30)
        thead.pack(fill="x", padx=0, pady=(8,0))
        thead.pack_propagate(False)
        for lbl, w in [("Timestamp",175),("Event / Name",320),
                        ("User",150),("Type",130),("Status",100),("Description",200)]:
            ctk.CTkLabel(thead, text=lbl, width=w, anchor="w",
                         font=("Segoe UI", 10, "bold"),
                         text_color=TEXT2).pack(side="left", padx=(10,0))

        # Scroll
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True)

        self._status_bar = ctk.CTkLabel(self, text="", font=F["small"],
                                         text_color=TEXT2)
        self._status_bar.pack(anchor="w", padx=14, pady=(0,6))

    # ── data ──────────────────────────────────────────────────────────────────
    def _load(self):
        if self._loading: return
        self._loading = True
        self._refresh_btn.configure(state="disabled", text="Loading…")
        self._status_lbl.configure(text="⏳ Querying CMS…")
        for w in self._scroll.winfo_children():
            w.destroy()

        days = int(self._days_var.get() or 7)
        user = self._user_entry.get().strip() or None

        def _fetch():
            try:
                recs = bo_session.get_historical_audit(days=days, user=user)
                if not self._destroyed:
                    self.after(0, lambda r=recs: self._on_loaded(r))
            except Exception as e:
                if not self._destroyed:
                    self.after(0, lambda: self._show_error(str(e)))
        threading.Thread(target=_fetch, daemon=True).start()

    def _on_loaded(self, records):
        self._loading = False
        self._refresh_btn.configure(state="normal", text="⟳ Refresh")
        self._records = records or []

        # Update tiles
        total   = len(self._records)
        users_s = set(r.get("user","") for r in self._records if r.get("user"))
        kinds_s = set(r.get("kind","") for r in self._records)
        today_s = datetime.now().strftime("%Y-%m-%d")
        today_n = sum(1 for r in self._records
                      if today_s in str(r.get("timestamp","")))
        errors_n= sum(1 for r in self._records
                      if "fail" in str(r.get("status","")).lower()
                      or "error" in str(r.get("name","")).lower())

        self._tiles["total"].configure(text=str(total))
        self._tiles["users_n"].configure(text=str(len(users_s)))
        self._tiles["kinds_n"].configure(text=str(len(kinds_s)))
        self._tiles["today"].configure(text=str(today_n))
        self._tiles["errors"].configure(text=str(errors_n))

        self._status_lbl.configure(text=f"{total} events")

        # draw chart
        self.after(100, lambda: self._chart.draw(self._records))
        self._apply_filter()

    def _apply_filter(self):
        if self._destroyed: return
        q = self._search_var.get().lower()
        visible = [
            r for r in self._records
            if not q
            or q in str(r.get("name","")).lower()
            or q in str(r.get("user","")).lower()
            or q in str(r.get("kind","")).lower()
            or q in str(r.get("description","")).lower()
        ]
        try:
            for w in self._scroll.winfo_children():
                w.destroy()
        except Exception:
            return

        if not visible:
            ctk.CTkLabel(self._scroll,
                         text="No audit events for this period.\n"
                              "Ensure the SAP BO Audit Server is enabled and the Audit DB is configured.",
                         font=F["body"], text_color=TEXT2,
                         justify="center").pack(pady=40)
            self._status_bar.configure(text="0 events shown")
            return

        capped = visible[:500]
        for i, r in enumerate(capped):
            self._add_row(r, i)

        self._status_bar.configure(
            text=f"Showing {len(capped)} of {len(self._records)} events"
                 + (" (capped at 500)" if len(visible) > 500 else ""))

    def _add_row(self, rec, idx):
        ts    = str(rec.get("timestamp",""))[:19].replace("T"," ")
        name  = str(rec.get("name",""))[:55]
        user  = str(rec.get("user",""))
        kind  = str(rec.get("kind",""))
        status= str(rec.get("status",""))
        desc  = str(rec.get("description",""))[:70]
        kcolor= KIND_COLORS.get(kind, TEXT2)
        scol  = GREEN if "success" in status.lower() else (RED if "fail" in status.lower() else TEXT2)
        bg    = BG1 if idx % 2 == 0 else "transparent"

        row = ctk.CTkFrame(self._scroll, fg_color=bg, corner_radius=4, height=30)
        row.pack(fill="x", pady=1, padx=2)
        row.pack_propagate(False)
        row.bind("<Enter>",  lambda e, r=row: r.configure(fg_color=BG2))
        row.bind("<Leave>",  lambda e, r=row, b=bg: r.configure(fg_color=b))
        row.bind("<Button-1>", lambda e, rec=rec: _EventDetail(self.winfo_toplevel(), rec))

        for val, w, col in [
            (ts,   172, TEXT2),
            (name, 318, TEXT),
            (user, 148, GREEN),
            (kind, 128, kcolor),
            (status, 98, scol),
            (desc, 198, TEXT2),
        ]:
            ctk.CTkLabel(row, text=val, width=w, anchor="w",
                         font=("Segoe UI", 10), text_color=col,
                         cursor="hand2").pack(side="left", padx=(10,0))

    def _show_error(self, msg):
        self._loading = False
        self._refresh_btn.configure(state="normal", text="⟳ Refresh")
        ctk.CTkLabel(self._scroll,
                     text=f"⚠  {msg}",
                     font=F["body"], text_color=AMBER,
                     wraplength=800, justify="left").pack(pady=30, padx=20, anchor="w")
        self._status_lbl.configure(text="Error")

    def _export_csv(self):
        if not self._records:
            messagebox.showinfo("No data", "No audit events loaded.", parent=self)
            return
        path = filedialog.asksaveasfilename(
            title="Export Audit CSV",
            defaultextension=".csv",
            filetypes=[("CSV","*.csv")],
            initialfile=f"bo_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            parent=self)
        if not path: return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(
                    f, fieldnames=["timestamp","name","user","kind","status","description"],
                    extrasaction="ignore")
                w.writeheader()
                w.writerows(self._records)
            self._status_bar.configure(
                text=f"✅ Exported {len(self._records)} rows → {path}")
        except Exception as e:
            self._status_bar.configure(text=f"❌ Export failed: {e}")