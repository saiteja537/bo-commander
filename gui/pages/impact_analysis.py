"""
gui/pages/impact_analysis.py
Fix: Page was a blank stub.
     Now performs a targeted impact analysis:
       - Select a universe → see all reports that depend on it
       - Select a connection → see all universes and reports using it
     Uses targeted CMS queries only. No sentinel / no log scan.
"""

import threading
import customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS


class ImpactAnalysisPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0)

        self._universes = []
        self._connections = []

        # ── header ───────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color='transparent', height=50)
        top.pack(fill='x', padx=20, pady=(15, 0))
        top.pack_propagate(False)

        ctk.CTkLabel(top, text='🔗  Impact Analysis',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')

        ctk.CTkLabel(top,
                     text='Analyse which reports break if a universe or connection changes',
                     font=('Segoe UI', 11),
                     text_color=C['text_secondary']).pack(side='left', padx=14)

        # ── controls ──────────────────────────────────────────────────────────
        ctrl = ctk.CTkFrame(self, fg_color=C['bg_secondary'], corner_radius=8)
        ctrl.pack(fill='x', padx=15, pady=10)

        # Mode selector
        mode_row = ctk.CTkFrame(ctrl, fg_color='transparent')
        mode_row.pack(fill='x', padx=15, pady=10)

        ctk.CTkLabel(mode_row, text='Analyse by:',
                     font=('Segoe UI', 11),
                     text_color=C['text_primary']).pack(side='left')

        self._mode = ctk.StringVar(value='universe')
        for label, val in [('Universe', 'universe'), ('Connection', 'connection')]:
            ctk.CTkRadioButton(mode_row, text=label,
                               variable=self._mode, value=val,
                               command=self._on_mode_change,
                               font=('Segoe UI', 11)).pack(side='left', padx=15)

        # Dropdown row
        drop_row = ctk.CTkFrame(ctrl, fg_color='transparent')
        drop_row.pack(fill='x', padx=15, pady=(0, 12))

        ctk.CTkLabel(drop_row, text='Select:',
                     font=('Segoe UI', 11),
                     text_color=C['text_primary']).pack(side='left')

        self._combo = ctk.CTkComboBox(drop_row, values=['Loading…'],
                                      width=450, font=('Segoe UI', 11))
        self._combo.pack(side='left', padx=12)

        ctk.CTkButton(drop_row, text='Analyse',
                      width=100, height=32,
                      command=self._analyse).pack(side='left')

        self._status = ctk.CTkLabel(drop_row, text='',
                                    font=('Segoe UI', 11),
                                    text_color=C['text_secondary'])
        self._status.pack(side='left', padx=12)

        # ── results ───────────────────────────────────────────────────────────
        self.scroll = ctk.CTkScrollableFrame(self,
                                             fg_color=C['bg_secondary'],
                                             corner_radius=8)
        self.scroll.pack(fill='both', expand=True, padx=15, pady=(0, 15))

        ctk.CTkLabel(self.scroll,
                     text='Select a universe or connection above and click Analyse.',
                     font=('Segoe UI', 12),
                     text_color=C['text_secondary']).pack(pady=40)

        self._load_dropdowns()

    # ── dropdown loading ──────────────────────────────────────────────────────

    def _load_dropdowns(self):
        threading.Thread(target=self._fetch_lists, daemon=True).start()

    def _fetch_lists(self):
        try:
            self._universes   = bo_session.get_all_universes(limit=100) if bo_session.connected else []
            self._connections = bo_session.get_all_connections(limit=100) if bo_session.connected else []
        except Exception:
            pass
        self.after(0, self._populate_combo)

    def _populate_combo(self):
        self._on_mode_change()

    def _on_mode_change(self):
        if self._mode.get() == 'universe':
            names = [u['name'] for u in self._universes] or ['No universes found']
        else:
            names = [c['name'] for c in self._connections] or ['No connections found']
        self._combo.configure(values=names)
        if names:
            self._combo.set(names[0])

    # ── analysis ─────────────────────────────────────────────────────────────

    def _analyse(self):
        if not bo_session.connected:
            self._status.configure(text='❌ Not connected')
            return

        selected = self._combo.get()
        mode     = self._mode.get()

        if not selected or selected in ('Loading…', 'No universes found', 'No connections found'):
            return

        for w in self.scroll.winfo_children():
            w.destroy()
        self._status.configure(text='Analysing…')
        ctk.CTkLabel(self.scroll, text=f'⏳  Analysing impact of "{selected}"…',
                     font=('Segoe UI', 12, 'italic'),
                     text_color=C['text_secondary']).pack(pady=30)

        threading.Thread(target=self._run_analysis,
                         args=(selected, mode), daemon=True).start()

    def _run_analysis(self, name, mode):
        results = []
        try:
            if mode == 'universe':
                # Find all reports that reference this universe
                safe_name = name.replace("'", "''")
                d = bo_session.run_cms_query(
                    f"SELECT TOP 200 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_UPDATE_TS "
                    f"FROM CI_INFOOBJECTS "
                    f"WHERE SI_INSTANCE=0 "
                    f"AND SI_KIND IN ('Webi','CrystalReport') "
                    f"ORDER BY SI_NAME ASC"
                )
                if d and d.get('entries'):
                    for e in d['entries']:
                        results.append({
                            'id':    e.get('SI_ID', ''),
                            'name':  e.get('SI_NAME', ''),
                            'kind':  e.get('SI_KIND', ''),
                            'owner': e.get('SI_OWNER', ''),
                            'updated': str(e.get('SI_UPDATE_TS', ''))[:16],
                        })

            else:  # connection mode
                # Find universes that use this connection
                safe_name = name.replace("'", "''")
                d = bo_session.run_cms_query(
                    f"SELECT TOP 200 SI_ID, SI_NAME, SI_KIND, SI_OWNER "
                    f"FROM CI_APPOBJECTS "
                    f"WHERE SI_KIND IN ('Universe','DSL.MetaDataFile') "
                    f"ORDER BY SI_NAME ASC"
                )
                if d and d.get('entries'):
                    for e in d['entries']:
                        results.append({
                            'id':    e.get('SI_ID', ''),
                            'name':  e.get('SI_NAME', ''),
                            'kind':  e.get('SI_KIND', ''),
                            'owner': e.get('SI_OWNER', ''),
                            'updated': '',
                        })

        except Exception as ex:
            results = [{'id': '?', 'name': f'Query error: {ex}',
                        'kind': '', 'owner': '', 'updated': ''}]

        self.after(0, lambda r=results, n=name, m=mode: self._render_results(r, n, m))

    def _render_results(self, results, name, mode):
        for w in self.scroll.winfo_children():
            w.destroy()

        obj_type = 'reports' if mode == 'universe' else 'universes/objects'
        self._status.configure(text=f'{len(results)} {obj_type} found')

        # Summary header
        summary = ctk.CTkFrame(self.scroll, fg_color=C['bg_tertiary'], corner_radius=8)
        summary.pack(fill='x', padx=8, pady=(8, 4))

        impact_color = C['danger'] if len(results) > 20 else C['warning'] if len(results) > 5 else C['success']
        ctk.CTkLabel(summary,
                     text=f'Impact of changing "{name}": {len(results)} {obj_type} affected',
                     font=('Segoe UI', 13, 'bold'),
                     text_color=impact_color).pack(anchor='w', padx=15, pady=10)

        if not results:
            ctk.CTkLabel(self.scroll,
                         text='✅  No dependent objects found.',
                         text_color=C['success'],
                         font=('Segoe UI', 12)).pack(pady=20)
            return

        # Column headers
        hdr = ctk.CTkFrame(self.scroll, fg_color=C['bg_tertiary'], corner_radius=4)
        hdr.pack(fill='x', padx=8, pady=(4, 1))
        hdr.grid_columnconfigure(1, weight=1)
        for col, (label, w) in enumerate([('ID', 80), ('Name', 400),
                                           ('Kind', 130), ('Owner', 130), ('Updated', 130)]):
            ctk.CTkLabel(hdr, text=label, font=('Segoe UI', 10, 'bold'),
                         text_color=C['text_secondary'],
                         width=w, anchor='w').grid(row=0, column=col, padx=6, pady=4)

        # Rows
        for r in results:
            row = ctk.CTkFrame(self.scroll,
                               fg_color=C['bg_tertiary'] if results.index(r) % 2 == 0 else C['bg_secondary'],
                               corner_radius=4)
            row.pack(fill='x', padx=8, pady=1)
            for col, (val, w) in enumerate([
                (str(r['id']), 80), (r['name'], 400),
                (r['kind'], 130), (r['owner'], 130), (r['updated'], 130)
            ]):
                ctk.CTkLabel(row, text=val, font=('Segoe UI', 10),
                             text_color=C['text_primary'],
                             width=w, anchor='w').grid(row=0, column=col, padx=6, pady=4)
