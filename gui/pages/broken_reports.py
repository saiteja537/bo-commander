"""
gui/pages/broken_reports.py
Fix: ImportError - cannot import name 'BrokenReportsPage'
     The file existed but had the wrong class name.

What "broken reports" means:
  - Reports whose last scheduled instance failed
  - Reports that haven't been refreshed in 90+ days (stale data)
  - Reports with zero instances (never ran)

Uses targeted CMS queries only — no 8-layer scan.
"""

import threading
import customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS

STATUS_COLORS = {
    'Failed':   '#EF4444',
    'Stale':    '#F59E0B',
    'Never Run':'#8B5CF6',
}


class BrokenReportsPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0)
        self._results = []

        # ── header ───────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color='transparent', height=50)
        top.pack(fill='x', padx=20, pady=(15, 0))
        top.pack_propagate(False)

        ctk.CTkLabel(top, text='📋  Broken Reports',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')

        self._scan_btn = ctk.CTkButton(top, text='⟳ Scan',
                                       width=100, height=34,
                                       command=self._scan)
        self._scan_btn.pack(side='right')

        self._status = ctk.CTkLabel(top, text='',
                                    font=('Segoe UI', 11),
                                    text_color=C['text_secondary'])
        self._status.pack(side='right', padx=12)

        ctk.CTkLabel(self,
                     text='Reports with failed instances, stale data (90+ days), or that have never run.',
                     font=('Segoe UI', 11),
                     text_color=C['text_secondary']).pack(anchor='w', padx=22, pady=(2, 8))

        # ── column headers ────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=C['bg_tertiary'], corner_radius=6)
        hdr.pack(fill='x', padx=15, pady=(0, 2))
        for label, width in [('Status', 110), ('Name', 360), ('Owner', 130),
                              ('Kind', 110), ('Last Run', 150), ('Folder', 180)]:
            ctk.CTkLabel(hdr, text=label, width=width, anchor='w',
                         font=('Segoe UI', 10, 'bold'),
                         text_color=C['text_secondary']).pack(side='left', padx=6, pady=6)

        # ── results ───────────────────────────────────────────────────────────
        self.scroll = ctk.CTkScrollableFrame(self,
                                             fg_color=C['bg_secondary'],
                                             corner_radius=8)
        self.scroll.pack(fill='both', expand=True, padx=15, pady=(0, 15))

        ctk.CTkLabel(self.scroll,
                     text='Click Scan to find broken reports.',
                     font=('Segoe UI', 12),
                     text_color=C['text_secondary']).pack(pady=40)

    # ── scan ─────────────────────────────────────────────────────────────────

    def _scan(self):
        if not bo_session.connected:
            self._status.configure(text='❌ Not connected')
            return
        self._scan_btn.configure(state='disabled', text='Scanning…')
        self._status.configure(text='Scanning…')
        for w in self.scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.scroll, text='⏳  Running CMS queries…',
                     font=('Segoe UI', 12, 'italic'),
                     text_color=C['text_secondary']).pack(pady=30)
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        results = []

        # Query 1: Reports with failed last instance
        try:
            failed = bo_session.get_instances(status='failed', limit=100)
            seen = set()
            for f in failed:
                pid = f.get('parent_id') or f.get('SI_PARENTID', 0)
                if pid and pid not in seen:
                    seen.add(pid)
                    results.append({
                        'id':       f.get('id', f.get('SI_ID', 0)),
                        'name':     f.get('name', f.get('SI_NAME', '')),
                        'kind':     f.get('kind', f.get('SI_KIND', '')),
                        'owner':    f.get('owner', f.get('SI_OWNER', '')),
                        'last_run': str(f.get('start_time', f.get('SI_STARTTIME', '')))[:16],
                        'folder':   '',
                        'status':   'Failed',
                    })
        except Exception:
            pass

        # Query 2: Reports with no instances at all (never ran)
        try:
            d = bo_session.run_cms_query(
                "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER, "
                "SI_UPDATE_TS, SI_PARENTID "
                "FROM CI_INFOOBJECTS "
                "WHERE SI_INSTANCE=0 "
                "AND SI_KIND IN ('Webi','CrystalReport') "
                "AND SI_NUM_INSTANCES=0 "
                "ORDER BY SI_UPDATE_TS ASC"
            )
            if d and d.get('entries'):
                for e in d['entries']:
                    results.append({
                        'id':       e.get('SI_ID', 0),
                        'name':     e.get('SI_NAME', ''),
                        'kind':     e.get('SI_KIND', ''),
                        'owner':    e.get('SI_OWNER', ''),
                        'last_run': 'Never',
                        'folder':   '',
                        'status':   'Never Run',
                    })
        except Exception:
            pass

        # Query 3: Stale reports — not updated in 90+ days
        try:
            d = bo_session.run_cms_query(
                "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER, "
                "SI_UPDATE_TS, SI_PARENTID "
                "FROM CI_INFOOBJECTS "
                "WHERE SI_INSTANCE=0 "
                "AND SI_KIND IN ('Webi','CrystalReport') "
                "AND SI_UPDATE_TS < '2024-12-01 00:00:00' "
                "ORDER BY SI_UPDATE_TS ASC"
            )
            if d and d.get('entries'):
                existing_ids = {r['id'] for r in results}
                for e in d['entries']:
                    eid = e.get('SI_ID', 0)
                    if eid not in existing_ids:
                        results.append({
                            'id':       eid,
                            'name':     e.get('SI_NAME', ''),
                            'kind':     e.get('SI_KIND', ''),
                            'owner':    e.get('SI_OWNER', ''),
                            'last_run': str(e.get('SI_UPDATE_TS', ''))[:16],
                            'folder':   '',
                            'status':   'Stale',
                        })
        except Exception:
            pass

        self.after(0, lambda r=results: self._render(r))

    # ── render ────────────────────────────────────────────────────────────────

    def _render(self, results):
        for w in self.scroll.winfo_children():
            w.destroy()
        self._scan_btn.configure(state='normal', text='⟳ Scan')
        self._results = results

        if not results:
            ctk.CTkLabel(self.scroll,
                         text='✅  No broken reports found.',
                         font=('Segoe UI', 13),
                         text_color=C['success']).pack(pady=40)
            self._status.configure(text='0 issues')
            return

        from collections import Counter
        counts = Counter(r['status'] for r in results)

        # Sort: Failed first
        order = {'Failed': 0, 'Never Run': 1, 'Stale': 2}
        results.sort(key=lambda x: order.get(x['status'], 9))

        self._status.configure(
            text='  '.join(f"{k}: {v}" for k, v in counts.items())
        )

        # Summary chips
        chip_row = ctk.CTkFrame(self.scroll, fg_color='transparent')
        chip_row.pack(fill='x', padx=8, pady=6)
        for status, cnt in sorted(counts.items(), key=lambda x: order.get(x[0], 9)):
            color = STATUS_COLORS.get(status, C['bg_tertiary'])
            chip = ctk.CTkFrame(chip_row, fg_color=color, corner_radius=6)
            chip.pack(side='left', padx=4)
            ctk.CTkLabel(chip, text=f'  {status}: {cnt}  ',
                         font=('Segoe UI', 10, 'bold'),
                         text_color='white').pack(pady=4)

        for r in results:
            self._render_row(r)

    def _render_row(self, r):
        status = r['status']
        color  = STATUS_COLORS.get(status, C['text_secondary'])

        row = ctk.CTkFrame(self.scroll,
                           fg_color=C['bg_tertiary'],
                           corner_radius=5)
        row.pack(fill='x', padx=6, pady=2)

        # Status badge
        badge_f = ctk.CTkFrame(row, fg_color=color, corner_radius=4, width=100)
        badge_f.pack(side='left', padx=(8, 4), pady=6)
        badge_f.pack_propagate(False)
        ctk.CTkLabel(badge_f, text=status,
                     font=('Segoe UI', 9, 'bold'),
                     text_color='white').pack(pady=5)

        for val, width in [
            (r['name'],     360),
            (r['owner'],    130),
            (r['kind'],     110),
            (r['last_run'], 150),
            (r['folder'],   180),
        ]:
            ctk.CTkLabel(row, text=str(val)[:50],
                         font=('Segoe UI', 10),
                         text_color=C['text_primary'],
                         width=width,
                         anchor='w').pack(side='left', padx=4)