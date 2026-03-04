"""gui/pages/reports.py  — FIXED VERSION
Bugs fixed:
  • TclError: bad window path name ".!ctkframe2…!ctkscrollableframe"
    (render callback fires after widget destroyed)
"""

import threading
import customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session as _bo_session_module


class ReportsPage(ctk.CTkFrame):
    def __init__(self, master, bo_session=None, **kwargs):
        super().__init__(master, fg_color=Config.COLORS["bg_primary"], **kwargs)
        self.bo_session = bo_session if bo_session is not None else _bo_session_module
        self._destroyed = False

        # ── header ───────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(20, 0))

        ctk.CTkLabel(top, text="📊  Reports",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")

        ctk.CTkButton(top, text="⟳ Refresh",
                      command=self._refresh,
                      fg_color=Config.COLORS["bg_tertiary"],
                      text_color=Config.COLORS["text_primary"],
                      width=100).pack(side="right")

        # ── search & filter ───────────────────────────────────────────────────
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=20, pady=6)

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_search())
        ctk.CTkEntry(bar, textvariable=self.search_var,
                     placeholder_text="🔍 Search reports…",
                     width=280).pack(side="left")

        self._type_filter = ctk.StringVar(value="All")
        for t in ("All", "Webi", "Crystal", "Deski"):
            ctk.CTkButton(bar, text=t, width=70,
                          fg_color=Config.COLORS["bg_tertiary"],
                          text_color=Config.COLORS["text_primary"],
                          command=lambda v=t: self._apply_type_filter(v)
                          ).pack(side="left", padx=2)

        # ── scroll area ───────────────────────────────────────────────────────
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=Config.COLORS["bg_secondary"])
        self.scroll.pack(fill="both", expand=True, padx=20, pady=10)

        ctk.CTkLabel(self.scroll, text="Loading reports…",
                     text_color=Config.COLORS["text_secondary"]).pack(pady=40)

        self._all_reports = []
        self._refresh()

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
        if self._destroyed:
            return
        try:
            if self.winfo_exists():
                fn(*args)
        except Exception as e:
            print(f"[ReportsPage] guarded call error: {e}")

    # ── data loading ──────────────────────────────────────────────────────────
    def _refresh(self):
        threading.Thread(target=self._fetch_thread, daemon=True).start()

    def _fetch_thread(self):
        try:
            if hasattr(self.bo_session, "get_reports"):
                reports = self.bo_session.get_reports()
            elif hasattr(self.bo_session, "get_report_list"):
                reports = self.bo_session.get_report_list()
            else:
                reports = self._fetch_reports_raw()
        except Exception as e:
            print(f"[ReportsPage] fetch error: {e}")
            reports = []

        self._safe_after(self._render_reports, reports)

    def _fetch_reports_raw(self):
        try:
            resp = self.bo_session.session.get(
                f"{self.bo_session.base_url}/v1/infoobjects",
                params={"type": "Webi,CrystalReport,Deski",
                        "offset": 0, "limit": 500,
                        "fields": "id,name,type,ownerid,lastruntime,status,parentid"})
            if resp.status_code == 200:
                body = resp.json()
                raw  = body.get("infoobjects", {}).get("infoobject", [])
                if isinstance(raw, dict):
                    raw = [raw]
                return raw
        except Exception as e:
            print(f"[ReportsPage] raw fetch error: {e}")
        return []

    # ── search / filter ───────────────────────────────────────────────────────
    def _apply_search(self):
        term = self.search_var.get().lower()
        filt = self._type_filter.get()
        self._redraw(term, filt)

    def _apply_type_filter(self, t):
        self._type_filter.set(t)
        self._apply_search()

    def _redraw(self, term, type_filter):
        data = self._all_reports
        if term:
            data = [r for r in data if term in str(r.get("name","")).lower()]
        if type_filter != "All":
            data = [r for r in data if type_filter.lower() in str(r.get("type","")).lower()]
        self._draw_rows(data)

    # ── render ────────────────────────────────────────────────────────────────
    def _clear_scroll(self):
        if self._destroyed:
            return
        try:
            if self.scroll.winfo_exists():
                for w in self.scroll.winfo_children():
                    w.destroy()
        except Exception:
            pass

    def _render_reports(self, reports):
        if self._destroyed:
            return
        self._all_reports = reports
        self._draw_rows(reports)

    def _draw_rows(self, reports):
        self._clear_scroll()

        if not reports:
            ctk.CTkLabel(self.scroll, text="No reports found.",
                         text_color=Config.COLORS["text_secondary"]).pack(pady=40)
            return

        TYPE_ICON = {"webi": "🌐", "crystalreport": "💎", "deski": "🖥", "": "📄"}

        for r in reports:
            rtype = str(r.get("type", "")).lower()
            icon  = TYPE_ICON.get(rtype, "📄")

            card = ctk.CTkFrame(self.scroll, fg_color=Config.COLORS["bg_tertiary"],
                                corner_radius=6)
            card.pack(fill="x", padx=4, pady=2)

            ctk.CTkLabel(card,
                         text=f"{icon}  {r.get('name','?')}",
                         font=ctk.CTkFont(size=13, weight="bold"),
                         anchor="w",
                         text_color=Config.COLORS["text_primary"]).pack(anchor="w", padx=12, pady=(6, 2))

            ctk.CTkLabel(card,
                         text=(f"ID: {r.get('id','?')}  |  "
                               f"Last run: {r.get('lastruntime', r.get('lastRun','N/A'))}  |  "
                               f"Status: {r.get('status','?')}"),
                         text_color=Config.COLORS["text_secondary"],
                         anchor="w").pack(anchor="w", padx=12, pady=(0, 6))
