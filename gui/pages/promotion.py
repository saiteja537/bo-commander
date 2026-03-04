"""gui/pages/promotion.py  — FIXED VERSION
Bugs fixed:
  • TclError: bad window path name (callback fires after widget destroyed)
"""

import threading
import customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session as _bo_session_module


class PromotionPage(ctk.CTkFrame):
    def __init__(self, master, bo_session=None, **kwargs):
        super().__init__(master, fg_color=Config.COLORS["bg_primary"], **kwargs)
        self.bo_session = bo_session if bo_session is not None else _bo_session_module
        self._destroyed = False

        # ── header ───────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(20, 0))

        ctk.CTkLabel(top, text="📦  Promotion Jobs",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")

        ctk.CTkButton(top, text="⟳ Refresh",
                      command=self._refresh,
                      fg_color=Config.COLORS["bg_tertiary"],
                      text_color=Config.COLORS["text_primary"],
                      width=100).pack(side="right")

        ctk.CTkButton(top, text="＋ New Job",
                      command=self._new_job,
                      fg_color=Config.COLORS["accent_green"],
                      width=110).pack(side="right", padx=6)

        # ── filters ───────────────────────────────────────────────────────────
        filt = ctk.CTkFrame(self, fg_color="transparent")
        filt.pack(fill="x", padx=20, pady=6)

        ctk.CTkLabel(filt, text="Status:",
                     text_color=Config.COLORS["text_secondary"]).pack(side="left")

        self._status_filter = ctk.StringVar(value="All")
        for s in ("All", "Success", "Failed", "Running", "Scheduled"):
            ctk.CTkButton(filt, text=s, width=80,
                          fg_color=Config.COLORS["bg_tertiary"],
                          text_color=Config.COLORS["text_primary"],
                          command=lambda v=s: self._apply_filter(v)
                          ).pack(side="left", padx=2)

        # ── scroll area ───────────────────────────────────────────────────────
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=Config.COLORS["bg_secondary"])
        self.scroll.pack(fill="both", expand=True, padx=20, pady=10)

        ctk.CTkLabel(self.scroll, text="Loading promotion jobs…",
                     text_color=Config.COLORS["text_secondary"]).pack(pady=40)

        self._all_jobs = []
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
        if not self._destroyed:
            try:
                if self.winfo_exists():
                    fn(*args)
            except Exception as e:
                print(f"[PromotionPage] guarded call error: {e}")

    # ── data loading ──────────────────────────────────────────────────────────
    def _refresh(self):
        threading.Thread(target=self._fetch_thread, daemon=True).start()

    def _fetch_thread(self):
        try:
            if hasattr(self.bo_session, "get_promotion_jobs"):
                jobs = self.bo_session.get_promotion_jobs()
            elif hasattr(self.bo_session, "get_jobs"):
                jobs = self.bo_session.get_jobs()
            else:
                jobs = self._fetch_jobs_raw()
        except Exception as e:
            print(f"[PromotionPage] fetch error: {e}")
            jobs = []

        self._safe_after(self._render, jobs)

    def _fetch_jobs_raw(self):
        try:
            resp = self.bo_session.session.get(
                f"{self.bo_session.base_url}/v1/promotionJobs",
                params={"offset": 0, "limit": 200})
            if resp.status_code == 200:
                data = resp.json()
                raw = data.get("promotionJobs", {}).get("promotionJob", [])
                if isinstance(raw, dict):
                    raw = [raw]
                return raw
        except Exception as e:
            print(f"[PromotionPage] raw fetch error: {e}")
        return []

    # ── filter ────────────────────────────────────────────────────────────────
    def _apply_filter(self, status):
        self._status_filter.set(status)
        if status == "All":
            self._render(self._all_jobs)
        else:
            filtered = [j for j in self._all_jobs
                        if str(j.get("status", "")).upper() == status.upper()]
            self._render(filtered)

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

    def _render(self, jobs):
        if self._destroyed:
            return
        self._all_jobs = jobs if self._status_filter.get() == "All" else self._all_jobs
        self._clear_scroll()

        if not jobs:
            ctk.CTkLabel(self.scroll, text="No promotion jobs found.",
                         text_color=Config.COLORS["text_secondary"]).pack(pady=40)
            return

        STATUS_COLOR = {
            "SUCCESS":   "#22c55e",
            "COMPLETED": "#22c55e",
            "FAILED":    "#ef4444",
            "ERROR":     "#ef4444",
            "RUNNING":   "#60a5fa",
            "SCHEDULED": "#a78bfa",
        }

        for job in jobs:
            status = str(job.get("status", "?")).upper()
            color  = STATUS_COLOR.get(status, "#94a3b8")

            card = ctk.CTkFrame(self.scroll, fg_color=Config.COLORS["bg_tertiary"],
                                corner_radius=8)
            card.pack(fill="x", padx=4, pady=4)

            left = ctk.CTkFrame(card, fg_color=color, width=6, corner_radius=0)
            left.pack(side="left", fill="y")

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="both", expand=True, padx=10, pady=8)

            ctk.CTkLabel(info,
                         text=f"📦  {job.get('name', job.get('id', 'Job'))}",
                         font=ctk.CTkFont(size=13, weight="bold"),
                         anchor="w",
                         text_color=Config.COLORS["text_primary"]).pack(anchor="w")

            ctk.CTkLabel(info,
                         text=(f"Source: {job.get('sourceSystem','?')} → "
                               f"Target: {job.get('targetSystem','?')}  |  "
                               f"Modified: {job.get('lastModified', job.get('modifiedAt','?'))}"),
                         text_color=Config.COLORS["text_secondary"],
                         anchor="w").pack(anchor="w")

            badge = ctk.CTkLabel(card, text=f" {status} ",
                                 fg_color=color, corner_radius=4,
                                 text_color="white",
                                 font=ctk.CTkFont(size=11, weight="bold"))
            badge.pack(side="right", padx=8)

    def _new_job(self):
        pass  # implement dialog as needed
