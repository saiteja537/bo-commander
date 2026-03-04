"""
gui/pages/sessions.py
Fixes applied:
  [1] KeyError: 'auth' — sessions.py used s['auth'] but old sapbo_connection didn't include that key.
      Fixed with .get() fallback chain: checks 'auth', 'auth_type', 'SI_AUTH_TYPE' in order.
  [2] KeyError: 'time' — similarly hardened with .get()
  [3] Kill Session now passes correct session id from the data dict
"""

import customtkinter as ctk
import threading
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS


class SessionsPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0)

        # ── header ────────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color='transparent', height=50)
        hdr.pack(fill='x', padx=20, pady=(15, 0))
        hdr.pack_propagate(False)

        ctk.CTkLabel(hdr, text='👥  Active Sessions',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')

        ctk.CTkButton(hdr, text='🔄 Refresh',
                      command=self.load,
                      width=100, height=30,
                      fg_color=C.get('bg_tertiary', '#2A2D3E'),
                      hover_color=C.get('bg_secondary', '#1E2130'),
                      text_color=C['text_primary']).pack(side='right')

        # ── summary label ─────────────────────────────────────────────────────
        self._count_var = ctk.StringVar(value='Loading…')
        ctk.CTkLabel(self, textvariable=self._count_var,
                     font=('Segoe UI', 11),
                     text_color=C['text_secondary']).pack(anchor='w', padx=20)

        # ── scrollable list ───────────────────────────────────────────────────
        self.scroll = ctk.CTkScrollableFrame(self,
                                             fg_color=C.get('bg_secondary', '#1E2130'))
        self.scroll.pack(fill='both', expand=True, padx=15, pady=10)

        self.load()

    # ── data loading ──────────────────────────────────────────────────────────

    def load(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        self._count_var.set('Loading…')
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        try:
            data = bo_session.get_active_sessions()
        except Exception:
            data = []
        self.after(0, lambda d=data: self._render(d))

    # ── render ────────────────────────────────────────────────────────────────

    def _render(self, data):
        for w in self.scroll.winfo_children():
            w.destroy()

        if not data:
            ctk.CTkLabel(self.scroll,
                         text='No active sessions found.',
                         font=('Segoe UI', 13),
                         text_color=C['text_secondary']).pack(pady=40)
            self._count_var.set('0 sessions')
            return

        self._count_var.set(f'{len(data)} active session(s)')

        for s in data:
            self._render_row(s)

    def _render_row(self, s):
        # ── Fix [1]: never use s['key'] directly — old sapbo may not have it ──
        #    Key map:  new sapbo → 'auth',  older → 'auth_type', raw → 'SI_AUTH_TYPE'
        auth   = s.get('auth') or s.get('auth_type') or s.get('SI_AUTH_TYPE') or 'Enterprise'
        time_  = s.get('time') or s.get('created') or s.get('SI_CREATION_TIME') or ''
        user   = s.get('user') or s.get('SI_NAME') or 'Unknown'
        sid    = s.get('id')   or s.get('SI_ID')   or 0
        desc   = s.get('description') or ''

        # Truncate time to 16 chars (YYYY-MM-DD HH:MM) safely
        time_str = str(time_)[:16] if time_ else '—'

        row = ctk.CTkFrame(self.scroll,
                           fg_color=C.get('bg_tertiary', '#2A2D3E'),
                           height=52,
                           corner_radius=6)
        row.pack(fill='x', pady=2, padx=4)
        row.pack_propagate(False)

        # User icon + name
        ctk.CTkLabel(row,
                     text=f'👤 {user}',
                     font=('Segoe UI', 12, 'bold'),
                     text_color=C['text_primary'],
                     width=200,
                     anchor='w').pack(side='left', padx=15)

        # Auth + time
        ctk.CTkLabel(row,
                     text=f'Auth: {auth}  |  {time_str}',
                     font=('Segoe UI', 11),
                     text_color=C['text_secondary']).pack(side='left', padx=5)

        # Description (if any)
        if desc:
            ctk.CTkLabel(row,
                         text=desc[:50],
                         font=('Segoe UI', 10),
                         text_color=C['text_secondary']).pack(side='left', padx=8)

        # Kill button
        ctk.CTkButton(row,
                      text='Kill Session',
                      fg_color=C.get('danger', '#EF4444'),
                      hover_color='#DC2626',
                      width=90,
                      height=28,
                      font=('Segoe UI', 10),
                      command=lambda _id=sid: self._kill(_id)
                      ).pack(side='right', padx=15)

    # ── actions ───────────────────────────────────────────────────────────────

    def _kill(self, session_id):
        if not session_id:
            return
        def _do():
            try:
                bo_session.kill_session(session_id)
            except Exception:
                pass
            self.after(500, self.load)   # refresh after kill
        threading.Thread(target=_do, daemon=True).start()
