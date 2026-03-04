"""gui/pages/services.py — BO Windows/SIA services viewer"""
import threading
import subprocess
import customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS

STATUS_COLORS = {
    'Running':  C['success'],
    'Stopped':  C['danger'],
    'Unknown':  C['text_secondary'],
}


class ServicesPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0)

        top = ctk.CTkFrame(self, fg_color='transparent', height=50)
        top.pack(fill='x', padx=20, pady=(15, 0))
        top.pack_propagate(False)
        ctk.CTkLabel(top, text='⚙  Services',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')
        ctk.CTkButton(top, text='🔄 Refresh', width=100, height=30,
                      fg_color=C['bg_tertiary'], text_color=C['text_primary'],
                      command=self._load).pack(side='right')
        self._status = ctk.CTkLabel(top, text='', font=('Segoe UI', 11),
                                    text_color=C['text_secondary'])
        self._status.pack(side='right', padx=12)

        ctk.CTkLabel(self, text='SAP BO Windows services and SIA server process status.',
                     font=('Segoe UI', 11), text_color=C['text_secondary']).pack(anchor='w', padx=22, pady=(2,8))

        # Summary row
        self._summary = ctk.CTkLabel(self, text='', font=('Segoe UI', 11),
                                     text_color=C['text_secondary'])
        self._summary.pack(anchor='w', padx=22)

        hdr = ctk.CTkFrame(self, fg_color=C['bg_tertiary'], corner_radius=6)
        hdr.pack(fill='x', padx=15, pady=(6, 2))
        for label, width in [('Status', 90), ('Server Name', 360), ('Kind', 200), ('Host', 160), ('Failures', 80)]:
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
        if bo_session.connected:
            try:
                servers = bo_session.get_all_servers()
                for s in servers:
                    rows.append({
                        'name':     s.get('name', ''),
                        'kind':     s.get('kind', ''),
                        'host':     s.get('host', 'localhost'),
                        'alive':    s.get('alive', False),
                        'failures': s.get('failures', 0),
                    })
            except Exception:
                pass
        self.after(0, lambda r=rows: self._render(r))

    def _render(self, rows):
        for w in self.scroll.winfo_children():
            w.destroy()

        if not rows:
            ctk.CTkLabel(self.scroll, text='ℹ  No server data. Check connection.',
                         font=('Segoe UI', 12), text_color=C['text_secondary']).pack(pady=40)
            self._status.configure(text='No data')
            return

        running  = sum(1 for r in rows if r['alive'])
        stopped  = len(rows) - running
        self._status.configure(text=f'{len(rows)} services')
        self._summary.configure(
            text=f'● {running} Running   ● {stopped} Stopped',
        )

        # Sort: stopped first
        rows.sort(key=lambda x: (x['alive'], x['name']))

        for i, r in enumerate(rows):
            status_text  = 'Running' if r['alive'] else 'Stopped'
            status_color = STATUS_COLORS[status_text]
            fail_color   = C['warning'] if r['failures'] > 0 else C['text_secondary']

            row = ctk.CTkFrame(self.scroll,
                               fg_color=C['bg_tertiary'] if i % 2 == 0 else C['bg_secondary'],
                               corner_radius=4)
            row.pack(fill='x', padx=6, pady=1)

            # Status dot
            st_f = ctk.CTkFrame(row, fg_color='transparent', width=90)
            st_f.pack(side='left', padx=6)
            st_f.pack_propagate(False)
            ctk.CTkLabel(st_f, text=f'● {status_text}',
                         font=('Segoe UI', 10, 'bold'),
                         text_color=status_color).pack(anchor='w', pady=7)

            for val, width in [(r['name'],360),(r['kind'],200),(r['host'],160)]:
                ctk.CTkLabel(row, text=str(val)[:55], width=width, anchor='w',
                             font=('Segoe UI', 10), text_color=C['text_primary']
                             ).pack(side='left', padx=4, pady=6)

            ctk.CTkLabel(row, text=str(r['failures']), width=80, anchor='w',
                         font=('Segoe UI', 10), text_color=fail_color
                         ).pack(side='left', padx=4)
