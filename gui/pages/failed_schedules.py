"""
failed_schedules.py — Failed Schedule Analyzer
Real-time view of all failed BO scheduled jobs with root cause, retry, and pattern detection.
"""
import threading
import customtkinter as ctk
from collections import Counter
from datetime import datetime
from config import Config
from core.sapbo_connection import bo_session
import logging

logger = logging.getLogger("FailedSchedules")


def _fmt_date(epoch_val):
    try:
        if not epoch_val or epoch_val == 0:
            return "N/A"
        return datetime.fromtimestamp(int(epoch_val)).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return str(epoch_val)


def _detect_cause(status_info: str) -> tuple[str, str]:
    """Detect root cause from status info text. Returns (cause, fix)."""
    if not status_info:
        return "Unknown error", "Check server logs"
    si = status_info.lower()

    causes = [
        ("connection refused",           "DB Connection Failed",     "Check database server and connection strings in CMC"),
        ("authentication failed",        "Authentication Error",      "Verify report credentials in CMC → Connections"),
        ("universe not found",           "Universe Missing",          "Restore universe or update report connection"),
        ("prompt",                       "Missing Prompt Value",      "Set default values for report prompts"),
        ("memory",                       "Out of Memory",             "Increase Java heap size or reduce data volume"),
        ("timeout",                      "Query Timeout",             "Optimize query or increase timeout limit"),
        ("server stopped",               "Server Down",               "Restart the job server in CMC → Servers"),
        ("server unavailable",           "Server Unavailable",        "Check server status and restart if needed"),
        ("file not found",               "Missing File/Resource",     "Verify input file paths and FRS availability"),
        ("database",                     "Database Error",            "Check database connectivity and permissions"),
        ("invalid credentials",          "Invalid Credentials",       "Update credentials in Connections or report"),
        ("disk",                         "Disk Space Issue",          "Free disk space on BO server or FileStore"),
        ("access denied",                "Access Denied",             "Check user permissions on the report/folder"),
        ("report failed",                "Report Processing Error",   "Open report manually to identify issue"),
    ]
    for keyword, cause_name, fix in causes:
        if keyword in si:
            return cause_name, fix
    return "Processing Error", "Review error details and server logs"


class FailedSchedulesPage(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=Config.COLORS['bg_primary'], **kwargs)
        self._destroyed = False
        self._failures  = []
        self._view      = 'list'  # 'list' or 'patterns'
        self._build_ui()
        self._load()

    def _safe_after(self, ms, fn):
        if not self._destroyed:
            try:
                self.after(ms, fn)
            except Exception:
                pass

    def destroy(self):
        self._destroyed = True
        super().destroy()

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=Config.COLORS['bg_secondary'])
        hdr.pack(fill='x', padx=15, pady=(15, 5))
        left = ctk.CTkFrame(hdr, fg_color='transparent')
        left.pack(side='left', padx=12, pady=8)
        ctk.CTkLabel(left, text="❌  Failed Schedule Analyzer",
                     font=Config.FONTS['sub_header'],
                     text_color=Config.COLORS['text_primary']).pack(anchor='w')
        ctk.CTkLabel(left,
                     text="Detect, diagnose, and fix failed BO scheduled jobs in one view",
                     font=Config.FONTS['small'],
                     text_color=Config.COLORS['text_secondary']).pack(anchor='w')
        btn_f = ctk.CTkFrame(hdr, fg_color='transparent')
        btn_f.pack(side='right', padx=10, pady=8)
        ctk.CTkButton(btn_f, text="⟳ Refresh", width=100,
                      fg_color=Config.COLORS['primary'],
                      command=self._load).pack(side='left', padx=4)
        ctk.CTkButton(btn_f, text="📊 Patterns", width=110,
                      fg_color=Config.COLORS['secondary'],
                      command=self._show_patterns).pack(side='left', padx=4)
        ctk.CTkButton(btn_f, text="↩ List View", width=100,
                      fg_color=Config.COLORS['bg_tertiary'],
                      command=self._show_list).pack(side='left', padx=4)

        # Stat cards
        stats = ctk.CTkFrame(self, fg_color=Config.COLORS['bg_secondary'])
        stats.pack(fill='x', padx=15, pady=(0, 5))
        self._stat_lbls = {}
        for key, label, color in [
            ('total',   '❌ Total Failed',      Config.COLORS['danger']),
            ('today',   '📅 Failed Today',      Config.COLORS['warning']),
            ('reports', '📊 Unique Reports',    Config.COLORS['primary']),
            ('pattern', '🔁 Repeat Offenders', Config.COLORS['secondary']),
        ]:
            card = ctk.CTkFrame(stats, fg_color=Config.COLORS['bg_tertiary'], width=175)
            card.pack(side='left', padx=6, pady=8, fill='y')
            card.pack_propagate(False)
            ctk.CTkLabel(card, text=label, font=Config.FONTS['small'],
                         text_color=Config.COLORS['text_secondary']).pack(pady=(6, 0))
            lbl = ctk.CTkLabel(card, text="—", font=('Segoe UI', 18, 'bold'),
                                text_color=color)
            lbl.pack(pady=(0, 6))
            self._stat_lbls[key] = lbl

        self.status_lbl = ctk.CTkLabel(self, text="Loading...",
                                        font=Config.FONTS['small'],
                                        text_color=Config.COLORS['text_secondary'])
        self.status_lbl.pack(anchor='w', padx=20, pady=(0, 4))
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=Config.COLORS['bg_secondary'])
        self.scroll.pack(fill='both', expand=True, padx=15, pady=(0, 15))

    def _load(self):
        if not bo_session.connected:
            self._set_status("⚠️  Not connected to BO server.")
            return
        self._set_status("⏳ Loading failed schedules...")
        threading.Thread(target=self._fetch_thread, daemon=True).start()

    def _fetch_thread(self):
        try:
            query = (
                "SELECT SI_ID, SI_NAME, SI_OWNERID, SI_OWNER, "
                "SI_CREATION_TIME, SI_STARTTIME, SI_ENDTIME, "
                "SI_SCHEDULE_STATUS, SI_STATUSINFO, SI_PARENTID "
                "FROM CI_INFOOBJECTS WHERE SI_INSTANCE=1 "
                "AND SI_SCHEDULE_STATUS=3 "
                "ORDER BY SI_STARTTIME DESC"
            )
            rows = bo_session._query(query) if hasattr(bo_session, '_query') else []

            failures = []
            for r in rows:
                info = str(r.get('SI_STATUSINFO', '') or '')
                cause, fix = _detect_cause(info)
                failures.append({
                    'id':        r.get('SI_ID', 0),
                    'name':      r.get('SI_NAME', 'Unknown'),
                    'owner':     r.get('SI_OWNER', str(r.get('SI_OWNERID', 'N/A'))),
                    'started':   r.get('SI_STARTTIME', 0),
                    'ended':     r.get('SI_ENDTIME', 0),
                    'created':   r.get('SI_CREATION_TIME', 0),
                    'parent_id': r.get('SI_PARENTID', 0),
                    'info':      info,
                    'cause':     cause,
                    'fix':       fix,
                })

            self._failures = failures
            self._safe_after(0, self._render_list)

        except Exception as e:
            logger.error(f"Failed schedules fetch error: {e}")
            self._failures = []
            self._safe_after(0, lambda: self._set_status(f"Error: {e}"))

    def _compute_stats(self):
        today_start = datetime.now().replace(hour=0, minute=0, second=0).timestamp()
        today_count   = sum(1 for f in self._failures if (f['started'] or 0) >= today_start)
        unique_reports = len(set(f['parent_id'] for f in self._failures if f['parent_id']))
        name_counts    = Counter(f['name'] for f in self._failures)
        repeats        = sum(1 for c in name_counts.values() if c > 1)
        return today_count, unique_reports, repeats

    def _update_stats(self):
        today, unique, repeats = self._compute_stats()
        self._stat_lbls['total'].configure(text=str(len(self._failures)))
        self._stat_lbls['today'].configure(text=str(today))
        self._stat_lbls['reports'].configure(text=str(unique))
        self._stat_lbls['pattern'].configure(text=str(repeats))

    def _show_list(self):
        self._view = 'list'
        self._render_list()

    def _show_patterns(self):
        self._view = 'patterns'
        self._render_patterns()

    def _render_list(self):
        if self._destroyed:
            return
        try:
            if not self.scroll.winfo_exists():
                return
            for w in self.scroll.winfo_children():
                w.destroy()
        except Exception:
            return

        self._update_stats()
        self._set_status(
            f"✅ {len(self._failures)} failed instance(s) found." if self._failures
            else "✅ No failed schedules! All jobs are healthy."
        )

        if not self._failures:
            ctk.CTkLabel(self.scroll,
                         text="✅  No failed scheduled jobs found.",
                         text_color=Config.COLORS['success'],
                         font=Config.FONTS['body']).pack(pady=40)
            return

        # Column headers
        hdr = ctk.CTkFrame(self.scroll, fg_color=Config.COLORS['bg_tertiary'])
        hdr.pack(fill='x', pady=(0, 2))
        for col, w in [("Report Name", 230), ("Root Cause", 170), ("Owner", 110),
                        ("Failed At", 130), ("Fix", 230), ("Actions", 140)]:
            ctk.CTkLabel(hdr, text=col, width=w, anchor='w',
                         font=('Segoe UI', 11, 'bold'),
                         text_color=Config.COLORS['text_secondary']).pack(side='left', padx=4, pady=5)

        for f in self._failures:
            self._render_failure_row(f)

    def _render_failure_row(self, f):
        row = ctk.CTkFrame(self.scroll, fg_color=Config.COLORS['bg_secondary'], height=44)
        row.pack(fill='x', pady=1)
        row.pack_propagate(False)

        ctk.CTkLabel(row, text=str(f['name'])[:30], width=230, anchor='w',
                     text_color=Config.COLORS['text_primary']).pack(side='left', padx=4)
        ctk.CTkLabel(row, text=str(f['cause'])[:22], width=170, anchor='w',
                     text_color=Config.COLORS['danger'],
                     font=('Segoe UI', 11, 'bold')).pack(side='left', padx=3)
        ctk.CTkLabel(row, text=str(f['owner'])[:14], width=110, anchor='w',
                     text_color=Config.COLORS['text_secondary']).pack(side='left', padx=3)
        ctk.CTkLabel(row, text=_fmt_date(f['started']), width=130, anchor='w',
                     text_color=Config.COLORS['text_secondary']).pack(side='left', padx=3)
        ctk.CTkLabel(row, text=str(f['fix'])[:30], width=230, anchor='w',
                     text_color=Config.COLORS['accent']).pack(side='left', padx=3)

        act_f = ctk.CTkFrame(row, fg_color='transparent')
        act_f.pack(side='left', padx=3)
        ctk.CTkButton(act_f, text="↩ Retry", width=64, height=26,
                      fg_color=Config.COLORS['primary'],
                      command=lambda fid=f['parent_id']: self._retry(fid)).pack(side='left', padx=2)
        ctk.CTkButton(act_f, text="📄 Log", width=54, height=26,
                      fg_color=Config.COLORS['bg_tertiary'],
                      command=lambda fi=f: self._show_log(fi)).pack(side='left', padx=2)

    def _render_patterns(self):
        if self._destroyed:
            return
        try:
            if not self.scroll.winfo_exists():
                return
            for w in self.scroll.winfo_children():
                w.destroy()
        except Exception:
            return

        name_counts  = Counter(f['name'] for f in self._failures)
        cause_counts = Counter(f['cause'] for f in self._failures)
        owner_counts = Counter(f['owner'] for f in self._failures)

        def _section(title, data, color):
            sec = ctk.CTkFrame(self.scroll, fg_color=Config.COLORS['bg_tertiary'])
            sec.pack(fill='x', pady=4, padx=5)
            ctk.CTkLabel(sec, text=title, font=('Segoe UI', 13, 'bold'),
                         text_color=color).pack(anchor='w', padx=12, pady=(8, 4))
            for name, count in data.most_common(8):
                row = ctk.CTkFrame(sec, fg_color=Config.COLORS['bg_secondary'])
                row.pack(fill='x', padx=8, pady=2)
                ctk.CTkLabel(row, text=str(name)[:60], anchor='w',
                             text_color=Config.COLORS['text_primary']).pack(side='left', padx=10, pady=5)
                ctk.CTkLabel(row, text=f"×{count}", font=('Segoe UI', 12, 'bold'),
                             text_color=color).pack(side='right', padx=10)

        ctk.CTkLabel(self.scroll, text="🔁  Repeat Offenders — Pattern Analysis",
                     font=('Segoe UI', 14, 'bold'),
                     text_color=Config.COLORS['text_primary']).pack(anchor='w', padx=5, pady=(8, 4))

        _section("📊 Most Failing Reports",      name_counts,  Config.COLORS['danger'])
        _section("🔍 Most Common Root Causes",   cause_counts, Config.COLORS['warning'])
        _section("👤 Users With Most Failures",  owner_counts, Config.COLORS['secondary'])

    def _retry(self, parent_id):
        if not parent_id or not bo_session.connected:
            return
        def _do():
            try:
                if hasattr(bo_session, 'schedule_report'):
                    bo_session.schedule_report(parent_id)
                elif hasattr(bo_session, '_query'):
                    bo_session._query(
                        f"SCHEDULE SI_OBJECTS WHERE SI_ID={parent_id}"
                    )
                self._safe_after(1500, self._load)
            except Exception as e:
                logger.warning(f"Retry {parent_id} failed: {e}")
        threading.Thread(target=_do, daemon=True).start()

    def _show_log(self, failure):
        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Error Log — {failure['name'][:40]}")
        dlg.geometry("700x400")
        dlg.configure(fg_color=Config.COLORS['bg_primary'])
        ctk.CTkLabel(dlg, text=f"📄  {failure['name']}",
                     font=('Segoe UI', 14, 'bold'),
                     text_color=Config.COLORS['text_primary']).pack(padx=15, pady=(15, 5), anchor='w')
        info_area = ctk.CTkTextbox(dlg, fg_color=Config.COLORS['bg_secondary'],
                                    text_color=Config.COLORS['text_primary'],
                                    font=('Consolas', 11))
        info_area.pack(fill='both', expand=True, padx=15, pady=(0, 15))
        content = (
            f"Report:    {failure['name']}\n"
            f"Instance:  {failure['id']}\n"
            f"Owner:     {failure['owner']}\n"
            f"Failed At: {_fmt_date(failure['started'])}\n"
            f"Root Cause:{failure['cause']}\n"
            f"Fix:       {failure['fix']}\n\n"
            f"--- Error Details ---\n{failure['info'] or 'No details available'}"
        )
        info_area.insert('0.0', content)
        info_area.configure(state='disabled')

    def _set_status(self, text):
        if not self._destroyed:
            try:
                self.status_lbl.configure(text=text)
            except Exception:
                pass
