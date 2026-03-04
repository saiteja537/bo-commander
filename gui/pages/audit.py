"""
gui/pages/audit.py
Audit page — query and display SAP BO audit events from CMS.
Calls: bo_session.get_historical_audit(days, user)
"""
import customtkinter as ctk
import threading
from datetime import datetime
from core.sapbo_connection import bo_session

C = {
    "bg":    "#0d1824", "bg2": "#112030", "bg3": "#1a2e42",
    "border":"#1e3a52", "cyan":"#22d3ee", "blue":"#3b82f6",
    "green": "#22c55e", "amber":"#f59e0b","red": "#ef4444",
    "text":  "#e2eaf4", "text2":"#8fafc8",
}
FONTS = {
    "header": ("Segoe UI", 18, "bold"),
    "body":   ("Segoe UI", 13),
    "small":  ("Segoe UI", 11),
    "mono":   ("Courier New", 11),
}
KIND_COLORS = {
    "AuditEvent": "#22d3ee",
    "Webi":       "#3b82f6",
    "CrystalReport": "#6366f1",
    "User":       "#22c55e",
    "UserGroup":  "#f59e0b",
}


class AuditPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._records = []
        self._loading = False
        self._build()
        self._load()

    # ── Layout ─────────────────────────────────────────────────────────────────
    def _build(self):
        # Top bar
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(top, text="📋  Audit Events",
                     font=FONTS["header"], text_color=C["cyan"]).pack(side="left")

        self._refresh_btn = ctk.CTkButton(
            top, text="⟳  Refresh", width=110, height=34,
            font=FONTS["body"], fg_color=C["bg3"],
            border_color=C["border"], border_width=1,
            hover_color=C["bg2"], command=self._load)
        self._refresh_btn.pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            top, text="⬇  Export CSV", width=120, height=34,
            font=FONTS["body"], fg_color=C["blue"],
            hover_color="#2563eb",
            command=self._export_csv).pack(side="right")

        # Filter bar
        fbar = ctk.CTkFrame(self, fg_color=C["bg2"], corner_radius=8)
        fbar.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(fbar, text="Days:", font=FONTS["small"],
                     text_color=C["text2"]).pack(side="left", padx=(14, 4))
        self._days_var = ctk.StringVar(value="7")
        self._days_seg = ctk.CTkSegmentedButton(
            fbar, values=["1", "7", "14", "30", "90"],
            variable=self._days_var,
            fg_color=C["bg3"], selected_color=C["cyan"],
            selected_hover_color="#06b6d4",
            font=FONTS["small"], height=30)
        self._days_seg.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(fbar, text="User:", font=FONTS["small"],
                     text_color=C["text2"]).pack(side="left", padx=(0, 4))
        self._user_entry = ctk.CTkEntry(
            fbar, width=160, height=30, placeholder_text="all users",
            font=FONTS["body"], fg_color=C["bg3"],
            border_color=C["border"], text_color=C["text"])
        self._user_entry.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(fbar, text="Search:", font=FONTS["small"],
                     text_color=C["text2"]).pack(side="left", padx=(0, 4))
        self._search_entry = ctk.CTkEntry(
            fbar, width=200, height=30, placeholder_text="filter results...",
            font=FONTS["body"], fg_color=C["bg3"],
            border_color=C["border"], text_color=C["text"])
        self._search_entry.pack(side="left", padx=(0, 8))
        self._search_entry.bind("<KeyRelease>", lambda e: self._apply_filter())

        ctk.CTkButton(fbar, text="Apply", width=80, height=30,
                      font=FONTS["body"], fg_color=C["cyan"],
                      text_color=C["bg"], hover_color="#06b6d4",
                      command=self._load).pack(side="left", padx=(0, 14))

        # Summary tiles
        self._tiles = ctk.CTkFrame(self, fg_color="transparent")
        self._tiles.pack(fill="x", pady=(0, 12))

        # Table header
        hdr = ctk.CTkFrame(self, fg_color=C["bg3"], corner_radius=6, height=36)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        for col, w in [("Timestamp", 180), ("Event / Name", 360),
                       ("User", 160), ("Type", 140), ("Description", 260)]:
            ctk.CTkLabel(hdr, text=col, font=("Segoe UI", 12, "bold"),
                         text_color=C["text2"], width=w, anchor="w"
                         ).pack(side="left", padx=(14, 0))

        # Scrollable results
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color=C["bg2"], corner_radius=8)
        self._scroll.pack(fill="both", expand=True, pady=(4, 0))

        # Status
        self._status = ctk.CTkLabel(self, text="Loading...",
                                     font=FONTS["small"], text_color=C["text2"])
        self._status.pack(anchor="w", pady=(6, 0))

    # ── Data loading ───────────────────────────────────────────────────────────
    def _load(self):
        if self._loading:
            return
        self._loading = True
        self._refresh_btn.configure(state="disabled", text="Loading...")
        for w in self._scroll.winfo_children():
            w.destroy()
        self._status.configure(text="Querying CMS...")

        days = int(self._days_var.get() or 7)
        user = self._user_entry.get().strip() or None

        def _fetch():
            try:
                if not bo_session.connected:
                    self.after(0, lambda: self._show_error("Not connected to SAP BO."))
                    return
                records = bo_session.get_historical_audit(days=days, user=user)
                self.after(0, lambda: self._render(records))
            except Exception as e:
                self.after(0, lambda: self._show_error(str(e)))

        threading.Thread(target=_fetch, daemon=True).start()

    def _render(self, records):
        self._loading = False
        self._refresh_btn.configure(state="normal", text="⟳  Refresh")
        self._records = records

        # Update tiles
        for w in self._tiles.winfo_children():
            w.destroy()

        total   = len(records)
        users_s = set(r.get("user", "") for r in records if r.get("user"))
        kinds_s = set(r.get("kind", "") for r in records)

        self._tile(self._tiles, "Total Events",   str(total),         C["cyan"])
        self._tile(self._tiles, "Unique Users",   str(len(users_s)),  C["blue"])
        self._tile(self._tiles, "Event Types",    str(len(kinds_s)),  C["amber"])

        self._apply_filter()

    def _apply_filter(self):
        for w in self._scroll.winfo_children():
            w.destroy()

        search = self._search_entry.get().strip().lower()
        visible = [r for r in self._records
                   if not search
                   or search in str(r.get("name","")).lower()
                   or search in str(r.get("user","")).lower()
                   or search in str(r.get("kind","")).lower()
                   or search in str(r.get("description","")).lower()]

        if not visible:
            ctk.CTkLabel(self._scroll,
                         text="No audit events found for the selected period.\n"
                              "Audit events are only stored if the SAP BO Audit Server is enabled and configured.",
                         font=FONTS["body"], text_color=C["text2"],
                         justify="center").pack(pady=40)
            self._status.configure(text="0 events")
            return

        for r in visible[:500]:  # cap at 500 rows
            self._add_row(r)

        shown = min(500, len(visible))
        self._status.configure(
            text=f"Showing {shown} of {len(self._records)} event(s) "
                 f"(days={self._days_var.get()}, filtered={len(visible)})")

    def _add_row(self, rec):
        ts    = str(rec.get("timestamp", ""))[:19].replace("T", " ")
        name  = rec.get("name",        "")[:60]
        user  = rec.get("user",        "")
        kind  = rec.get("kind",        "")
        desc  = str(rec.get("description", ""))[:80]
        kind_color = KIND_COLORS.get(kind, C["text2"])

        row = ctk.CTkFrame(self._scroll, fg_color="transparent",
                           height=34, corner_radius=4)
        row.pack(fill="x", pady=1)
        row.bind("<Enter>", lambda e, r=row: r.configure(fg_color=C["bg3"]))
        row.bind("<Leave>", lambda e, r=row: r.configure(fg_color="transparent"))

        ctk.CTkLabel(row, text=ts,   font=FONTS["mono"], text_color=C["text2"],
                     width=180, anchor="w").pack(side="left", padx=(14, 0))
        ctk.CTkLabel(row, text=name, font=FONTS["body"], text_color=C["text"],
                     width=360, anchor="w").pack(side="left")
        ctk.CTkLabel(row, text=user, font=FONTS["small"], text_color=C["text2"],
                     width=160, anchor="w").pack(side="left")
        ctk.CTkLabel(row, text=kind, font=FONTS["small"], text_color=kind_color,
                     width=140, anchor="w").pack(side="left")
        ctk.CTkLabel(row, text=desc, font=FONTS["small"], text_color=C["text2"],
                     width=260, anchor="w").pack(side="left")

    def _tile(self, parent, label, value, color):
        t = ctk.CTkFrame(parent, fg_color=C["bg2"], corner_radius=8,
                          width=160, height=70)
        t.pack(side="left", padx=(0, 12))
        t.pack_propagate(False)
        ctk.CTkLabel(t, text=value, font=("Segoe UI", 28, "bold"),
                     text_color=color).pack(pady=(8, 0))
        ctk.CTkLabel(t, text=label, font=FONTS["small"],
                     text_color=C["text2"]).pack()

    def _show_error(self, msg):
        self._loading = False
        self._refresh_btn.configure(state="normal", text="⟳  Refresh")
        ctk.CTkLabel(self._scroll,
                     text=f"⚠  {msg}",
                     font=FONTS["body"], text_color=C["amber"],
                     wraplength=800, justify="left").pack(pady=30, padx=20, anchor="w")
        self._status.configure(text="Error")

    def _export_csv(self):
        if not self._records:
            return
        try:
            import csv, tkinter.filedialog as fd
            path = fd.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV", "*.csv")],
                initialfile="bo_audit_export.csv")
            if not path:
                return
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["timestamp","name","user","kind","description","status"])
                w.writeheader()
                w.writerows(self._records)
            self._status.configure(text=f"Exported {len(self._records)} rows → {path}")
        except Exception as e:
            self._status.configure(text=f"Export failed: {e}")
