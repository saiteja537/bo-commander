"""
gui/tabs/_base.py — Shared constants, colors, threading helper
Used by every tab. Import like:  from gui.tabs._base import *
"""
import threading
import customtkinter as ctk
from tkinter import ttk, messagebox
from core.sapbo_connection import bo_session

# ── Color palette ─────────────────────────────────────────────────────────────
BG0    = "#0F172A"   # deep navy       — page background
BG1    = "#1E293B"   # slate           — panels, cards
BG2    = "#334155"   # lighter slate   — inputs, headers
CYAN   = "#22d3ee"   # primary accent
BLUE   = "#3B82F6"   # info / primary
VIOLET = "#8B5CF6"   # secondary
GREEN  = "#10B981"   # success
AMBER  = "#F59E0B"   # warning
RED    = "#EF4444"   # danger / error
TEAL   = "#14b8a6"
TEXT   = "#F1F5F9"   # primary text
TEXT2  = "#94A3B8"   # secondary text
GLASS  = "#1a2744"   # card bg

# ── Fonts ─────────────────────────────────────────────────────────────────────
F_H1   = ("Segoe UI", 20, "bold")
F_H2   = ("Segoe UI", 14, "bold")
F_H3   = ("Segoe UI", 12, "bold")
F_BODY = ("Segoe UI", 11)
F_SM   = ("Segoe UI", 10)
F_XS   = ("Segoe UI", 9)
F_MONO = ("Consolas", 10)

# ── Status colors ─────────────────────────────────────────────────────────────
STATUS_COLOR = {
    "Running": GREEN, "Success": GREEN, "success": GREEN,
    "Stopped": RED,   "Failed":  RED,   "failed":  RED,   "Error": RED,
    "Running": AMBER, "running": AMBER,
    "Pending": TEXT2, "pending": TEXT2,
    "Scheduled": BLUE, "scheduled": BLUE,
}


def status_color(s: str) -> str:
    s = str(s)
    if s.lower() in ("running", "started"):           return AMBER
    if s.lower() in ("success", "completed", "ok"):   return GREEN
    if s.lower() in ("failed", "error", "stopped"):   return RED
    if s.lower() in ("pending", "scheduled", "paused"): return BLUE
    return TEXT2


# ── Threaded background runner ────────────────────────────────────────────────
def bg(fn, callback, root_widget):
    """Run fn() in a daemon thread, then call callback(result) on the GUI thread."""
    def _run():
        try:
            result = fn()
        except Exception as exc:
            result = None
        try:
            root_widget.after(0, lambda r=result: callback(r))
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


# ── TTK Treeview factory ──────────────────────────────────────────────────────
_STYLE_COUNTER = [0]

def make_tree(parent, columns, heights=30, multi=True):
    """Create a styled dark Treeview with scrollbars. Returns (tree, frame)."""
    _STYLE_COUNTER[0] += 1
    sn = f"BOTree{_STYLE_COUNTER[0]}"

    s = ttk.Style()
    s.theme_use("default")
    s.configure(sn,
                background=BG1, foreground=TEXT,
                fieldbackground=BG1, rowheight=heights,
                font=("Segoe UI", 10), borderwidth=0)
    s.configure(f"{sn}.Heading",
                background=BG2, foreground=TEXT2,
                font=("Segoe UI", 10, "bold"), relief="flat")
    s.map(sn,
          background=[("selected", BLUE)],
          foreground=[("selected", "white")])
    s.layout(sn, [("Treeview.treearea", {"sticky": "nswe"})])

    outer = ctk.CTkFrame(parent, fg_color=BG1, corner_radius=8)

    sel = "extended" if multi else "browse"
    tree = ttk.Treeview(outer, style=sn, show="headings",
                        columns=[c[0] for c in columns],
                        selectmode=sel)
    for cid, heading, width in columns:
        tree.heading(cid, text=heading)
        tree.column(cid, width=width, minwidth=40)

    vsb = ctk.CTkScrollbar(outer, orientation="vertical", command=tree.yview,
                            button_color=BG2, button_hover_color=BLUE)
    hsb = ctk.CTkScrollbar(outer, orientation="horizontal", command=tree.xview,
                            button_color=BG2, button_hover_color=BLUE)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    vsb.pack(side="right", fill="y")
    hsb.pack(side="bottom", fill="x")
    tree.pack(fill="both", expand=True)

    return tree, outer


# ── Small reusable widgets ────────────────────────────────────────────────────
def stat_tile(parent, title: str, value: str, color: str, icon: str = ""):
    """Compact KPI tile. Returns the value label so it can be updated."""
    card = ctk.CTkFrame(parent, fg_color=BG1, corner_radius=10,
                         border_color=color, border_width=1)
    strip = ctk.CTkFrame(card, fg_color=color, height=3, corner_radius=0)
    strip.pack(fill="x")
    inner = ctk.CTkFrame(card, fg_color="transparent")
    inner.pack(fill="both", expand=True, padx=10, pady=6)
    if icon:
        ctk.CTkLabel(inner, text=icon, font=("Segoe UI", 16),
                     text_color=color).pack(anchor="w")
    val_lbl = ctk.CTkLabel(inner, text=value,
                            font=("Segoe UI", 24, "bold"),
                            text_color=color)
    val_lbl.pack(anchor="w")
    ctk.CTkLabel(inner, text=title, font=F_XS,
                 text_color=TEXT2).pack(anchor="w")
    return card, val_lbl


def section_header(parent, text: str, color=CYAN):
    ctk.CTkLabel(parent, text=text, font=F_H2, text_color=color,
                 anchor="w").pack(fill="x", pady=(10, 2))
    ctk.CTkFrame(parent, fg_color=BG2, height=1).pack(fill="x", pady=(0, 6))


def confirm(title: str, message: str, parent=None) -> bool:
    return messagebox.askyesno(title, message, parent=parent, icon="warning")


def show_error(title: str, msg: str, parent=None):
    messagebox.showerror(title, msg, parent=parent)


def show_info(title: str, msg: str, parent=None):
    messagebox.showinfo(title, msg, parent=parent)


# ── Base tab class ────────────────────────────────────────────────────────────
class BaseTab(ctk.CTkFrame):
    """All tabs inherit from this. Provides status bar + consistent layout."""

    def __init__(self, master, **kw):
        super().__init__(master, fg_color=BG0, corner_radius=0, **kw)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header row (overridden by subclasses via _build_header)
        self._hdr = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=60)
        self._hdr.grid(row=0, column=0, sticky="ew")
        self._hdr.pack_propagate(False)
        self._hdr.grid_propagate(False)

        # Body (subclass puts content here)
        self._body = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self._body.grid(row=1, column=0, sticky="nsew")
        self._body.grid_columnconfigure(0, weight=1)
        self._body.grid_rowconfigure(0, weight=1)

        # Status bar
        self._sbar = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=26)
        self._sbar.grid(row=2, column=0, sticky="ew")
        self._sbar.pack_propagate(False)
        self._status_lbl = ctk.CTkLabel(self._sbar, text="", font=F_XS,
                                         text_color=TEXT2, anchor="w")
        self._status_lbl.pack(side="left", padx=12)
        self._status_r   = ctk.CTkLabel(self._sbar, text="", font=F_XS,
                                         text_color=TEXT2, anchor="e")
        self._status_r.pack(side="right", padx=12)

    def set_status(self, msg: str, color=None, right: str = ""):
        self._status_lbl.configure(text=msg,
                                    text_color=color or TEXT2)
        self._status_r.configure(text=right)

    def _page_header(self, title: str, icon: str, subtitle: str = ""):
        """Standard page header — title on left, action buttons added by subclass."""
        ctk.CTkLabel(self._hdr,
                     text=f"{icon}  {title}",
                     font=F_H1, text_color=CYAN,
                     anchor="w").pack(side="left", padx=18)
        if subtitle:
            ctk.CTkLabel(self._hdr,
                         text=subtitle,
                         font=F_XS, text_color=TEXT2).pack(side="left")
        # Returns the right-side frame for action buttons
        right = ctk.CTkFrame(self._hdr, fg_color="transparent")
        right.pack(side="right", padx=12)
        return right
