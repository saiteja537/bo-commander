"""gui/pages/web_services.py — BO Web Services (QaaWS / REST) viewer"""
import threading
import customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS


class WebServicesPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0)

        top = ctk.CTkFrame(self, fg_color='transparent', height=50)
        top.pack(fill='x', padx=20, pady=(15, 0))
        top.pack_propagate(False)
        ctk.CTkLabel(top, text='🌐  Web Services',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')
        ctk.CTkButton(top, text='🔄 Refresh', width=100, height=30,
                      fg_color=C['bg_tertiary'], text_color=C['text_primary'],
                      command=self._load).pack(side='right')
        self._status = ctk.CTkLabel(top, text='', font=('Segoe UI', 11),
                                    text_color=C['text_secondary'])
        self._status.pack(side='right', padx=12)

        ctk.CTkLabel(self, text='QaaWS and RESTful web services published from this BO system.',
                     font=('Segoe UI', 11), text_color=C['text_secondary']).pack(anchor='w', padx=22, pady=(2,8))

        # WSDL url hint
        host = 'localhost'
        try:
            host = bo_session.cms_details.get('host', 'localhost')
        except Exception:
            pass
        ctk.CTkLabel(self,
                     text=f'ℹ  WSDL endpoint: http://{host}:8080/dswsbobje/qaawsservices/biws?WSDL=1',
                     font=('Segoe UI', 10), text_color=C['text_secondary']).pack(anchor='w', padx=22)

        hdr = ctk.CTkFrame(self, fg_color=C['bg_tertiary'], corner_radius=6)
        hdr.pack(fill='x', padx=15, pady=(8, 2))
        for label, width in [('Name', 320), ('Kind', 180), ('Owner', 140), ('Modified', 160)]:
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
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        rows = []
        if not bo_session.connected:
            self.after(0, lambda: self._render([])); return
        for sql in [
            # QaaWS services live in CI_APPOBJECTS
            "SELECT TOP 200 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_UPDATE_TS "
            "FROM CI_APPOBJECTS "
            "WHERE SI_KIND IN ('QaaWS','WebService','RESTService','WebI.QTService') "
            "ORDER BY SI_NAME ASC",
            # Fallback: anything with 'service' in kind
            "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_UPDATE_TS "
            "FROM CI_APPOBJECTS "
            "WHERE LOWER(SI_KIND) LIKE '%service%' "
            "ORDER BY SI_NAME ASC",
        ]:
            try:
                d = bo_session.run_cms_query(sql)
                if d and d.get('entries'):
                    for e in d['entries']:
                        rows.append({
                            'name':     e.get('SI_NAME', ''),
                            'kind':     e.get('SI_KIND', ''),
                            'owner':    e.get('SI_OWNER', ''),
                            'modified': str(e.get('SI_UPDATE_TS', ''))[:16],
                        })
                    break
            except Exception:
                continue
        self.after(0, lambda r=rows: self._render(r))

    def _render(self, rows):
        for w in self.scroll.winfo_children():
            w.destroy()
        if not rows:
            ctk.CTkLabel(self.scroll,
                         text='ℹ  No web services found.\n'
                              'Web services are created via the CMC → Web Services section.',
                         font=('Segoe UI', 12), text_color=C['text_secondary'],
                         justify='center').pack(pady=50)
            self._status.configure(text='0 web services')
            return
        self._status.configure(text=f'{len(rows)} web service(s)')
        for i, r in enumerate(rows):
            row = ctk.CTkFrame(self.scroll,
                               fg_color=C['bg_tertiary'] if i % 2 == 0 else C['bg_secondary'],
                               corner_radius=4)
            row.pack(fill='x', padx=6, pady=1)
            for val, width in [(r['name'],320),(r['kind'],180),(r['owner'],140),(r['modified'],160)]:
                ctk.CTkLabel(row, text=str(val)[:55], width=width, anchor='w',
                             font=('Segoe UI', 10), text_color=C['text_primary']
                             ).pack(side='left', padx=6, pady=6)
