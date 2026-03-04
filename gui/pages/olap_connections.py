"""gui/pages/olap_connections.py — OLAP/BICS Connections viewer"""
import threading
import customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS


class OLAPConnectionsPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0)

        top = ctk.CTkFrame(self, fg_color='transparent', height=50)
        top.pack(fill='x', padx=20, pady=(15, 0))
        top.pack_propagate(False)
        ctk.CTkLabel(top, text='🔗  OLAP Connections',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')
        ctk.CTkButton(top, text='🔄 Refresh', width=100, height=30,
                      fg_color=C['bg_tertiary'], text_color=C['text_primary'],
                      command=self._load).pack(side='right')
        self._status = ctk.CTkLabel(top, text='', font=('Segoe UI', 11),
                                    text_color=C['text_secondary'])
        self._status.pack(side='right', padx=12)

        ctk.CTkLabel(self, text='OLAP, BICS, HANA, and BW connections registered in this BO system.',
                     font=('Segoe UI', 11), text_color=C['text_secondary']).pack(anchor='w', padx=22, pady=(2,8))

        # Headers
        hdr = ctk.CTkFrame(self, fg_color=C['bg_tertiary'], corner_radius=6)
        hdr.pack(fill='x', padx=15, pady=(0, 2))
        for label, width in [('Name', 300), ('Type', 140), ('Server/URL', 280),
                              ('Database', 160), ('Owner', 120)]:
            ctk.CTkLabel(hdr, text=label, width=width, anchor='w',
                         font=('Segoe UI', 10, 'bold'),
                         text_color=C['text_secondary']).pack(side='left', padx=6, pady=6)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=C['bg_secondary'], corner_radius=8)
        self.scroll.pack(fill='both', expand=True, padx=15, pady=(0, 15))
        self._load()

    def _load(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        self._status.configure(text='Loading…')
        ctk.CTkLabel(self.scroll, text='⏳ Loading OLAP connections…',
                     font=('Segoe UI', 12, 'italic'),
                     text_color=C['text_secondary']).pack(pady=30)
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        rows = []
        if not bo_session.connected:
            self.after(0, lambda: self._render([], 'Not connected'))
            return
        try:
            d = bo_session.run_cms_query(
                "SELECT TOP 200 SI_ID, SI_NAME, SI_KIND, SI_OWNER, "
                "SI_PROCESSINFO.SI_SHORTCUT_DATA AS SI_SHORTCUT "
                "FROM CI_APPOBJECTS "
                "WHERE SI_KIND IN ('OlapConnection','BicsConnection','HanaConnection',"
                "'BwConnection','OlapBicsConnection') "
                "ORDER BY SI_NAME ASC"
            )
            if d and d.get('entries'):
                for e in d['entries']:
                    sc = e.get('SI_SHORTCUT', {}) or {}
                    rows.append({
                        'name':   e.get('SI_NAME', ''),
                        'kind':   e.get('SI_KIND', ''),
                        'server': sc.get('SI_SERVER', sc.get('SI_URL', '')),
                        'db':     sc.get('SI_DATABASE', sc.get('SI_CATALOG', '')),
                        'owner':  e.get('SI_OWNER', ''),
                    })
        except Exception:
            # Fallback: list all app objects and filter
            try:
                d = bo_session.run_cms_query(
                    "SELECT TOP 200 SI_ID, SI_NAME, SI_KIND, SI_OWNER "
                    "FROM CI_APPOBJECTS "
                    "WHERE SI_KIND LIKE '%Connection%' OR SI_KIND LIKE '%Olap%' "
                    "ORDER BY SI_NAME ASC"
                )
                if d and d.get('entries'):
                    for e in d['entries']:
                        rows.append({'name': e.get('SI_NAME',''), 'kind': e.get('SI_KIND',''),
                                     'server': '', 'db': '', 'owner': e.get('SI_OWNER','')})
            except Exception:
                pass
        self.after(0, lambda r=rows: self._render(r))

    def _render(self, rows, error=None):
        for w in self.scroll.winfo_children():
            w.destroy()
        if error:
            ctk.CTkLabel(self.scroll, text=f'❌ {error}', text_color=C['danger'],
                         font=('Segoe UI', 12)).pack(pady=40)
            self._status.configure(text='Error')
            return
        if not rows:
            ctk.CTkLabel(self.scroll, text='ℹ  No OLAP connections found in this BO system.',
                         font=('Segoe UI', 12), text_color=C['text_secondary']).pack(pady=40)
            self._status.configure(text='0 connections')
            return
        self._status.configure(text=f'{len(rows)} OLAP connection(s)')
        for i, r in enumerate(rows):
            row = ctk.CTkFrame(self.scroll,
                               fg_color=C['bg_tertiary'] if i % 2 == 0 else C['bg_secondary'],
                               corner_radius=4)
            row.pack(fill='x', padx=6, pady=1)
            for val, width in [(r['name'],300),(r['kind'],140),(r['server'],280),(r['db'],160),(r['owner'],120)]:
                ctk.CTkLabel(row, text=str(val)[:50], width=width, anchor='w',
                             font=('Segoe UI', 10), text_color=C['text_primary']
                             ).pack(side='left', padx=6, pady=6)
