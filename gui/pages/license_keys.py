"""
gui/pages/license_keys.py
License Keys page — shows SAP BO license information from CMS.
Calls: bo_session.get_license_keys()
"""
import customtkinter as ctk
from core.sapbo_connection import bo_session

C = {
    "bg":    "#0d1824", "bg2": "#112030", "bg3": "#1a2e42",
    "border":"#1e3a52", "cyan":"#22d3ee", "blue":"#3b82f6",
    "green": "#22c55e", "amber":"#f59e0b","red": "#ef4444",
    "text":  "#e2eaf4", "text2":"#8fafc8",
}
FONTS = {
    "header": ("Segoe UI", 18, "bold"),
    "sub":    ("Segoe UI", 14, "bold"),
    "body":   ("Segoe UI", 13),
    "small":  ("Segoe UI", 11),
    "mono":   ("Courier New", 12),
}


class LicenseKeysPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._build()
        self._load()

    def _build(self):
        # Header
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(0, 16))

        ctk.CTkLabel(top, text="🔑  License Keys",
                     font=FONTS["header"], text_color=C["cyan"]).pack(side="left")

        ctk.CTkButton(top, text="⟳  Refresh", width=110, height=34,
                      font=FONTS["body"], fg_color=C["bg3"],
                      border_color=C["border"], border_width=1,
                      hover_color=C["bg2"],
                      command=self._load).pack(side="right")

        # Summary tiles row
        self._tiles_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._tiles_frame.pack(fill="x", pady=(0, 16))

        # Cards container
        self._cards_scroll = ctk.CTkScrollableFrame(
            self, fg_color=C["bg2"], corner_radius=8)
        self._cards_scroll.pack(fill="both", expand=True)

        # Status
        self._status = ctk.CTkLabel(self, text="", font=FONTS["small"],
                                     text_color=C["text2"])
        self._status.pack(anchor="w", pady=(6, 0))

    def _load(self):
        for w in self._tiles_frame.winfo_children():
            w.destroy()
        for w in self._cards_scroll.winfo_children():
            w.destroy()

        if not bo_session.connected:
            self._show_error("Not connected to SAP BO. Please log in first.")
            return

        try:
            licenses = bo_session.get_license_keys()
        except Exception as e:
            self._show_error(f"Failed to load license data: {e}")
            return

        if not licenses:
            self._show_empty()
            return

        # Summary tiles
        active  = sum(1 for l in licenses if str(l.get("status","")).upper() != "EXPIRED")
        expired = len(licenses) - active
        self._add_tile(self._tiles_frame, "Total Licenses", str(len(licenses)), C["cyan"])
        self._add_tile(self._tiles_frame, "Active",  str(active),  C["green"])
        self._add_tile(self._tiles_frame, "Expired", str(expired), C["red"] if expired else C["text2"])

        # License cards
        for lic in licenses:
            self._add_card(lic)

        self._status.configure(text=f"{len(licenses)} license(s) retrieved from CMS")

    def _add_tile(self, parent, label, value, color):
        tile = ctk.CTkFrame(parent, fg_color=C["bg2"], corner_radius=8,
                             width=160, height=70)
        tile.pack(side="left", padx=(0, 12))
        tile.pack_propagate(False)
        ctk.CTkLabel(tile, text=value, font=("Segoe UI", 28, "bold"),
                     text_color=color).pack(pady=(8, 0))
        ctk.CTkLabel(tile, text=label, font=FONTS["small"],
                     text_color=C["text2"]).pack()

    def _add_card(self, lic):
        status = str(lic.get("status", "Active"))
        is_exp = "EXPIR" in status.upper()
        border_col = C["red"] if is_exp else C["border"]

        card = ctk.CTkFrame(self._cards_scroll, fg_color=C["bg3"],
                             corner_radius=8,
                             border_color=border_col, border_width=1)
        card.pack(fill="x", padx=4, pady=6)

        # Card header
        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 6))

        product = lic.get("product", "SAP BusinessObjects")
        lic_type = lic.get("type", "Standard")
        status_col = C["red"] if is_exp else C["green"]

        ctk.CTkLabel(hdr, text=product, font=FONTS["sub"],
                     text_color=C["text"]).pack(side="left")
        ctk.CTkLabel(hdr, text=f"● {status}", font=FONTS["small"],
                     text_color=status_col).pack(side="right")

        # Divider
        ctk.CTkFrame(card, height=1, fg_color=C["border"]).pack(fill="x", padx=16)

        # Details grid
        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=10)

        fields = [
            ("License Type",  lic_type),
            ("License Key",   lic.get("key",         "N/A")),
            ("Named Users",   str(lic.get("seats",       "N/A"))),
            ("Concurrent",    str(lic.get("concurrent",  "N/A"))),
            ("Expiry Date",   str(lic.get("expiry",      "N/A"))),
        ]

        for i, (label, value) in enumerate(fields):
            col = i % 3
            row_frame = grid if col == 0 else grid
            sub = ctk.CTkFrame(grid, fg_color="transparent")
            sub.pack(side="left", padx=(0, 28), pady=2, anchor="n")
            ctk.CTkLabel(sub, text=label, font=FONTS["small"],
                         text_color=C["text2"]).pack(anchor="w")
            ctk.CTkLabel(sub, text=value, font=("Segoe UI", 13, "bold"),
                         text_color=C["text"]).pack(anchor="w")
            if col == 2:
                ctk.CTkFrame(card, height=0, fg_color="transparent").pack()

        ctk.CTkFrame(card, height=1, fg_color="transparent").pack(pady=(0, 4))

    def _show_error(self, msg):
        ctk.CTkLabel(self._cards_scroll,
                     text=f"⚠  {msg}", font=FONTS["body"],
                     text_color=C["amber"], wraplength=700,
                     justify="left").pack(pady=30, padx=20, anchor="w")
        self._status.configure(text="Error loading license data")

    def _show_empty(self):
        ctk.CTkLabel(self._cards_scroll,
                     text="No license data found in CMS.\nCheck CMC → License Keys for details.",
                     font=FONTS["body"], text_color=C["text2"],
                     justify="center").pack(pady=40)
        self._status.configure(text="No license data")
