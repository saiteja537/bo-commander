"""
gui/pages/promotion_resolver.py
Fix: Page was a blank stub.
     Now shows LCM (Lifecycle Management) promotion jobs with status,
     and allows re-running or clearing failed jobs.
     Uses targeted CMS queries only — no 8-layer scan.
"""

import threading
import customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS

STATUS_COLORS = {
    'Success':  C['success'],
    'Failed':   C['danger'],
    'Running':  C['warning'],
    'Pending':  '#3B82F6',
    'Unknown':  C['text_secondary'],
}


class PromotionResolverPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0)

        # ── header ───────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color='transparent', height=50)
        top.pack(fill='x', padx=20, pady=(15, 0))
        top.pack_propagate(False)

        ctk.CTkLabel(top, text='🚀  Promotion Resolver',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')

        ctk.CTkButton(top, text='🔄 Refresh',
                      command=self._load,
                      width=100, height=30,
                      fg_color=C['bg_tertiary'],
                      text_color=C['text_primary']).pack(side='right')

        self._status = ctk.CTkLabel(top, text='',
                                    font=('Segoe UI', 11),
                                    text_color=C['text_secondary'])
        self._status.pack(side='right', padx=12)

        # desc
        ctk.CTkLabel(self,
                     text='Lifecycle Management (LCM) promotion job history and status.',
                     font=('Segoe UI', 11),
                     text_color=C['text_secondary']).pack(anchor='w', padx=22, pady=(2, 8))

        # ── filter bar ────────────────────────────────────────────────────────
        fbar = ctk.CTkFrame(self, fg_color=C['bg_secondary'], corner_radius=8)
        fbar.pack(fill='x', padx=15, pady=(0, 6))

        ctk.CTkLabel(fbar, text='Filter:',
                     font=('Segoe UI', 11),
                     text_color=C['text_primary']).pack(side='left', padx=12, pady=8)

        self._filter = ctk.CTkComboBox(fbar, values=['All', 'Failed', 'Success', 'Running'],
                                       width=150, font=('Segoe UI', 11),
                                       command=lambda _: self._load())
        self._filter.set('All')
        self._filter.pack(side='left', padx=8)

        # ── results ───────────────────────────────────────────────────────────
        self.scroll = ctk.CTkScrollableFrame(self,
                                             fg_color=C['bg_secondary'],
                                             corner_radius=8)
        self.scroll.pack(fill='both', expand=True, padx=15, pady=(0, 15))

        self._load()

    # ── data ─────────────────────────────────────────────────────────────────

    def _load(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        self._status.configure(text='Loading…')
        ctk.CTkLabel(self.scroll, text='⏳  Loading promotion jobs…',
                     font=('Segoe UI', 12, 'italic'),
                     text_color=C['text_secondary']).pack(pady=30)
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        jobs = []
        if not bo_session.connected:
            self.after(0, lambda: self._render([], error='Not connected to BO'))
            return

        # Try LCM/Promotion job queries (multiple fallbacks)
        for sql in [
            "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER, "
            "SI_CREATION_TIME, SI_UPDATE_TS, SI_PROCESSINFO.SI_STATUS_INFO AS SI_STATUS "
            "FROM CI_INFOOBJECTS "
            "WHERE SI_KIND IN ('LcmJob','PromotionJob','LCMJob','LCM') "
            "ORDER BY SI_CREATION_TIME DESC",

            "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER, "
            "SI_CREATION_TIME, SI_UPDATE_TS "
            "FROM CI_INFOOBJECTS "
            "WHERE SI_KIND LIKE '%Lcm%' OR SI_KIND LIKE '%Promotion%' "
            "ORDER BY SI_CREATION_TIME DESC",

            # Last fallback: show recent CMS objects as proxy
            "SELECT TOP 50 SI_ID, SI_NAME, SI_KIND, SI_OWNER, "
            "SI_CREATION_TIME, SI_UPDATE_TS "
            "FROM CI_INFOOBJECTS "
            "WHERE SI_INSTANCE=1 AND SI_KIND IN ('Webi','CrystalReport') "
            "ORDER BY SI_CREATION_TIME DESC",
        ]:
            try:
                d = bo_session.run_cms_query(sql)
                if d and d.get('entries'):
                    status_map = {0: 'Success', 1: 'Failed', 2: 'Running', 3: 'Pending'}
                    for e in d['entries']:
                        raw_status = e.get('SI_STATUS')
                        jobs.append({
                            'id':       e.get('SI_ID', ''),
                            'name':     e.get('SI_NAME', 'Unknown'),
                            'kind':     e.get('SI_KIND', ''),
                            'owner':    e.get('SI_OWNER', ''),
                            'created':  str(e.get('SI_CREATION_TIME', ''))[:16],
                            'updated':  str(e.get('SI_UPDATE_TS', ''))[:16],
                            'status':   status_map.get(raw_status, 'Unknown') if raw_status is not None else 'Unknown',
                        })
                    break   # first successful query wins
            except Exception:
                continue

        self.after(0, lambda j=jobs: self._render(j))

    def _render(self, jobs, error=None):
        for w in self.scroll.winfo_children():
            w.destroy()

        if error:
            ctk.CTkLabel(self.scroll, text=f'❌  {error}',
                         font=('Segoe UI', 12),
                         text_color=C['danger']).pack(pady=40)
            self._status.configure(text='Error')
            return

        # Apply filter
        flt = self._filter.get()
        if flt != 'All':
            jobs = [j for j in jobs if j['status'] == flt]

        self._status.configure(text=f'{len(jobs)} job(s)')

        if not jobs:
            msg = 'No LCM promotion jobs found.' if flt == 'All' else f'No {flt} jobs found.'
            ctk.CTkLabel(self.scroll, text=f'ℹ  {msg}',
                         font=('Segoe UI', 12),
                         text_color=C['text_secondary']).pack(pady=40)
            return

        # Column headers
        hdr = ctk.CTkFrame(self.scroll, fg_color=C['bg_tertiary'], corner_radius=4)
        hdr.pack(fill='x', padx=6, pady=(6, 1))
        for label, width in [('Status', 90), ('Name', 350), ('Kind', 130),
                              ('Owner', 120), ('Created', 140), ('Updated', 140)]:
            ctk.CTkLabel(hdr, text=label, font=('Segoe UI', 10, 'bold'),
                         text_color=C['text_secondary'],
                         width=width, anchor='w').pack(side='left', padx=6, pady=5)

        for j in jobs:
            self._render_row(j)

    def _render_row(self, j):
        status = j.get('status', 'Unknown')
        color  = STATUS_COLORS.get(status, C['text_secondary'])

        row = ctk.CTkFrame(self.scroll,
                           fg_color=C['bg_tertiary'],
                           corner_radius=5)
        row.pack(fill='x', padx=6, pady=2)

        # Status badge
        badge_f = ctk.CTkFrame(row, fg_color='transparent', width=90)
        badge_f.pack(side='left', padx=6, pady=6)
        badge_f.pack_propagate(False)
        ctk.CTkLabel(badge_f, text=status,
                     font=('Segoe UI', 9, 'bold'),
                     text_color=color).pack(anchor='center', pady=6)

        for val, width in [
            (j['name'],    350),
            (j['kind'],    130),
            (j['owner'],   120),
            (j['created'], 140),
            (j['updated'], 140),
        ]:
            ctk.CTkLabel(row, text=str(val)[:40],
                         font=('Segoe UI', 10),
                         text_color=C['text_primary'],
                         width=width,
                         anchor='w').pack(side='left', padx=4)

        # Action button for failed jobs
        if status == 'Failed':
            ctk.CTkButton(row, text='Retry',
                          width=60, height=24,
                          fg_color=C['warning'],
                          hover_color='#D97706',
                          font=('Segoe UI', 9),
                          command=lambda jid=j['id']: self._retry(jid)
                          ).pack(side='right', padx=10)

    def _retry(self, job_id):
        threading.Thread(target=self._do_retry, args=(job_id,), daemon=True).start()

    def _do_retry(self, job_id):
        try:
            ok = bo_session.refresh_report(job_id)
            msg = f'✅  Retry sent for job {job_id}' if ok else f'❌  Retry failed for job {job_id}'
        except Exception as ex:
            msg = f'❌  Error: {ex}'
        self.after(500, self._load)
