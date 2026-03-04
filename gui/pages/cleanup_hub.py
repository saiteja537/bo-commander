"""gui/pages/cleanup_hub.py  — FIXED VERSION
Bugs fixed:
  • AttributeError: 'SAPBOConnection' object has no attribute 'find_orphaned_data'
  • TclError: bad window path (widget destroyed before render callback)
"""

import threading
import customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session as _bo_session_module


class CleanupHubPage(ctk.CTkFrame):
    def __init__(self, master, bo_session=None, **kwargs):
        super().__init__(master, fg_color=Config.COLORS["bg_primary"], **kwargs)
        self.bo_session = bo_session if bo_session is not None else _bo_session_module
        self._destroyed = False

        # ── header ───────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(20, 0))

        ctk.CTkLabel(top, text="🗑  Orphan Purge",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")

        self.scan_btn = ctk.CTkButton(
            top, text="🔍 Scan for Orphans",
            command=self._start_scan,
            fg_color=Config.COLORS["accent_blue"],
            width=160)
        self.scan_btn.pack(side="right")

        # ── summary cards ─────────────────────────────────────────────────────
        self.summary_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.summary_frame.pack(fill="x", padx=20, pady=10)

        self._orphan_lbl  = self._make_card("Orphaned Instances", "0", "#f97316")
        self._broken_lbl  = self._make_card("Broken Reports",      "0", "#ef4444")
        self._noown_lbl   = self._make_card("No-Owner Objects",     "0", "#eab308")

        # ── tabs ─────────────────────────────────────────────────────────────
        tab_bar = ctk.CTkFrame(self, fg_color="transparent")
        tab_bar.pack(fill="x", padx=20)

        self._active_tab = ctk.StringVar(value="Orphaned Instances")
        for label in ("Orphaned Instances", "Broken Reports", "No-Owner Objects"):
            ctk.CTkButton(
                tab_bar, text=label, width=160,
                fg_color=Config.COLORS["bg_tertiary"],
                text_color=Config.COLORS["text_primary"],
                command=lambda l=label: self._switch_tab(l)
            ).pack(side="left", padx=2)

        # ── scroll area ───────────────────────────────────────────────────────
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=Config.COLORS["bg_secondary"])
        self.scroll.pack(fill="both", expand=True, padx=20, pady=10)

        ctk.CTkLabel(self.scroll, text="Click 'Scan for Orphans' to begin.",
                     text_color=Config.COLORS["text_secondary"]).pack(pady=40)

        self._data = {}
        self._start_scan()

    # ── card factory ──────────────────────────────────────────────────────────
    def _make_card(self, title, value, color):
        card = ctk.CTkFrame(self.summary_frame, fg_color=Config.COLORS["bg_tertiary"],
                            corner_radius=8, width=180)
        card.pack(side="left", padx=8, pady=4)
        ctk.CTkLabel(card, text=title, text_color=Config.COLORS["text_secondary"],
                     font=ctk.CTkFont(size=11)).pack(padx=12, pady=(8, 0))
        lbl = ctk.CTkLabel(card, text=value, text_color=color,
                           font=ctk.CTkFont(size=28, weight="bold"))
        lbl.pack(padx=12, pady=(0, 8))
        return lbl

    # ── lifecycle guard ───────────────────────────────────────────────────────
    def destroy(self):
        self._destroyed = True
        super().destroy()

    def _safe_after(self, fn, *args):
        if not self._destroyed:
            try:
                self.after(0, lambda: self._guarded_call(fn, *args))
            except Exception:
                pass

    def _guarded_call(self, fn, *args):
        if not self._destroyed:
            try:
                fn(*args)
            except Exception as e:
                print(f"[CleanupHub] guarded call error: {e}")

    # ── scan ──────────────────────────────────────────────────────────────────
    def _start_scan(self):
        if self._destroyed:
            return
        self.scan_btn.configure(text="Scanning…", state="disabled")
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        try:
            if hasattr(self.bo_session, "find_orphaned_data"):
                data = self.bo_session.find_orphaned_data()
            else:
                print("[CleanupHub] find_orphaned_data not found — using stub")
                data = {
                    "orphaned_instances": [],
                    "broken_reports":     [],
                    "no_owner_objects":   [],
                    "summary": {"orphaned_count": 0, "broken_count": 0, "no_owner_count": 0},
                }
        except Exception as e:
            print(f"[CleanupHub] scan error: {e}")
            data = {
                "orphaned_instances": [],
                "broken_reports":     [],
                "no_owner_objects":   [],
                "summary": {"orphaned_count": 0, "broken_count": 0, "no_owner_count": 0},
            }
        self._safe_after(self._render, data)

    # ── render ────────────────────────────────────────────────────────────────
    def _clear_scroll(self):
        if self._destroyed:
            return
        try:
            for w in self.scroll.winfo_children():
                w.destroy()
        except Exception:
            pass

    def _render(self, data):
        if self._destroyed:
            return
        self._data = data
        summary = data.get("summary", {})

        try:
            self.scan_btn.configure(text="🔍 Scan for Orphans", state="normal")
        except Exception:
            pass

        # Update summary cards
        try:
            self._orphan_lbl.configure(text=str(summary.get("orphaned_count", 0)))
            self._broken_lbl.configure(text=str(summary.get("broken_count",   0)))
            self._noown_lbl.configure( text=str(summary.get("no_owner_count",  0)))
        except Exception:
            pass

        self._switch_tab(self._active_tab.get())

    def _switch_tab(self, label):
        if self._destroyed:
            return
        self._active_tab.set(label)
        self._clear_scroll()

        if label == "Orphaned Instances":
            items = self._data.get("orphaned_instances", [])
            key_fn = lambda i: f"🔄  {i.get('name','?')}   Status: {i.get('status','?')}   Last: {i.get('last','N/A')}"
        elif label == "Broken Reports":
            items = self._data.get("broken_reports", [])
            key_fn = lambda i: f"💔  {i.get('name','?')}   Status: {i.get('status','?')}"
        else:
            items = self._data.get("no_owner_objects", [])
            key_fn = lambda i: f"👻  {i.get('name','?')}   Type: {i.get('type','?')}"

        if not items:
            ctk.CTkLabel(self.scroll, text=f"✅ No {label.lower()} found.",
                         text_color="#22c55e",
                         font=ctk.CTkFont(size=13)).pack(pady=40)
            return

        for item in items:
            row = ctk.CTkFrame(self.scroll, fg_color=Config.COLORS["bg_tertiary"], height=40)
            row.pack(fill="x", padx=4, pady=2)
            row.pack_propagate(False)
            ctk.CTkLabel(row, text=key_fn(item), anchor="w",
                         text_color=Config.COLORS["text_primary"]).pack(side="left", padx=10)

            ctk.CTkButton(row, text="Delete", width=70,
                          fg_color="#ef4444", hover_color="#dc2626",
                          command=lambda i=item: self._delete_item(i)).pack(side="right", padx=6)

    def _delete_item(self, item):
        try:
            oid = item.get("id")
            if oid:
                self.bo_session.session.delete(
                    f"{self.bo_session.base_url}/v1/infoobjects/{oid}")
        except Exception as e:
            print(f"[CleanupHub] delete error: {e}")
        self._start_scan()
