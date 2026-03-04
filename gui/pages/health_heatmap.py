"""
gui/pages/health_heatmap.py
Fix: Page was a blank stub.
     Now shows a color-coded grid of all BO servers with status, failures, host.
     Uses ONE targeted CMS query (get_all_servers) — no 8-layer scan.
     Auto-refreshes every 30 seconds.
"""

import threading
import customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS


class HealthHeatmapPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0)
        self._after_id = None

        # ── header ───────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color='transparent', height=50)
        top.pack(fill='x', padx=20, pady=(15, 0))
        top.pack_propagate(False)

        ctk.CTkLabel(top, text='🌡  Health Heatmap',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')

        ctk.CTkButton(top, text='🔄 Refresh',
                      command=self._load,
                      width=100, height=30,
                      fg_color=C['bg_tertiary'],
                      text_color=C['text_primary']).pack(side='right')

        self._status_lbl = ctk.CTkLabel(top, text='',
                                        font=('Segoe UI', 11),
                                        text_color=C['text_secondary'])
        self._status_lbl.pack(side='right', padx=12)

        # ── legend ────────────────────────────────────────────────────────────
        legend = ctk.CTkFrame(self, fg_color='transparent')
        legend.pack(fill='x', padx=20, pady=(4, 0))
        for label, color in [('● Running', C['success']),
                              ('● Stopped', C['danger']),
                              ('● Warning (failures)', C['warning'])]:
            ctk.CTkLabel(legend, text=label, font=('Segoe UI', 11),
                         text_color=color).pack(side='left', padx=8)

        # ── summary bar ───────────────────────────────────────────────────────
        self._summary = ctk.CTkLabel(self, text='',
                                     font=('Segoe UI', 11),
                                     text_color=C['text_secondary'])
        self._summary.pack(anchor='w', padx=22, pady=(4, 0))

        # ── grid container ────────────────────────────────────────────────────
        self.grid_area = ctk.CTkScrollableFrame(self,
                                                fg_color=C['bg_secondary'],
                                                corner_radius=8)
        self.grid_area.pack(fill='both', expand=True, padx=15, pady=10)

        self._load()

    def destroy(self):
        if self._after_id:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
        super().destroy()

    # ── data ─────────────────────────────────────────────────────────────────

    def _load(self):
        for w in self.grid_area.winfo_children():
            w.destroy()
        self._status_lbl.configure(text='Loading…')
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        try:
            servers = bo_session.get_all_servers() if bo_session.connected else []
        except Exception:
            servers = []
        self.after(0, lambda s=servers: self._render(s))

    def _render(self, servers):
        for w in self.grid_area.winfo_children():
            w.destroy()

        if not servers:
            ctk.CTkLabel(self.grid_area,
                         text='No server data available.\nCheck connection.',
                         font=('Segoe UI', 13),
                         text_color=C['text_secondary']).pack(pady=40)
            self._status_lbl.configure(text='No data')
            return

        running  = sum(1 for s in servers if s.get('alive'))
        stopped  = len(servers) - running
        warnings = sum(1 for s in servers if s.get('failures', 0) > 0)

        self._status_lbl.configure(
            text=f'{running} running · {stopped} stopped · {warnings} with failures'
        )
        self._summary.configure(
            text=f'Total: {len(servers)} servers'
        )

        # Responsive grid: 3 columns
        cols = 3
        for idx, srv in enumerate(servers):
            row = idx // cols
            col = idx % cols
            self._render_card(srv, row, col)

        for c in range(cols):
            self.grid_area.grid_columnconfigure(c, weight=1)

        # Auto-refresh every 30s
        try:
            self._after_id = self.after(30000, self._load)
        except Exception:
            pass

    def _render_card(self, srv, row, col):
        alive    = srv.get('alive', False)
        failures = srv.get('failures', 0)

        if not alive:
            border_color = C['danger']
            status_text  = '● STOPPED'
            status_color = C['danger']
        elif failures > 0:
            border_color = C['warning']
            status_text  = f'● WARNING ({failures} failures)'
            status_color = C['warning']
        else:
            border_color = C['success']
            status_text  = '● RUNNING'
            status_color = C['success']

        card = ctk.CTkFrame(self.grid_area,
                            fg_color=C['bg_tertiary'],
                            corner_radius=8,
                            border_width=2,
                            border_color=border_color)
        card.grid(row=row, column=col, padx=6, pady=6, sticky='nsew')

        # Server name
        ctk.CTkLabel(card,
                     text=srv.get('name', 'Unknown'),
                     font=('Segoe UI', 11, 'bold'),
                     text_color=C['text_primary'],
                     wraplength=200,
                     anchor='w').pack(fill='x', padx=12, pady=(10, 2))

        # Status
        ctk.CTkLabel(card,
                     text=status_text,
                     font=('Segoe UI', 10),
                     text_color=status_color).pack(anchor='w', padx=12)

        # Kind + host
        kind = srv.get('kind', '')
        host = srv.get('host', 'localhost')
        ctk.CTkLabel(card,
                     text=f"{kind}  |  {host}",
                     font=('Segoe UI', 10),
                     text_color=C['text_secondary']).pack(anchor='w', padx=12, pady=(0, 10))
