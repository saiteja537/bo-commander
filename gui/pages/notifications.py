"""
gui/pages/notifications.py
Fix: Page was a blank stub — showed nothing.
     Now shows: Sentinel incidents + live BO alerts (failed instances, stopped servers).
     Does NOT trigger a full 8-layer scan. Reads already-computed sentinel.incidents
     and runs two targeted CMS queries only.
"""

import threading
import customtkinter as ctk
from datetime import datetime
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS


class NotificationsPage(ctk.CTkFrame):

    SEVERITY_COLORS = {
        'CRITICAL': '#EF4444',
        'HIGH':     '#F97316',
        'MEDIUM':   '#F59E0B',
        'LOW':      '#10B981',
    }

    def __init__(self, parent, sentinel=None):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0)
        self._sentinel = sentinel   # SentinelAgent instance (may be None)

        # ── header ───────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color='transparent', height=50)
        top.pack(fill='x', padx=20, pady=(15, 0))
        top.pack_propagate(False)

        ctk.CTkLabel(top, text='🔔  Notifications',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')

        ctk.CTkButton(top, text='🔄 Refresh',
                      command=self._load,
                      width=100, height=30,
                      fg_color=C['bg_tertiary'],
                      text_color=C['text_primary']).pack(side='right')

        self._badge = ctk.CTkLabel(top, text='',
                                   font=('Segoe UI', 11),
                                   text_color=C['text_secondary'])
        self._badge.pack(side='right', padx=10)

        # ── scrollable content ────────────────────────────────────────────────
        self.scroll = ctk.CTkScrollableFrame(self,
                                             fg_color=C['bg_secondary'],
                                             corner_radius=8)
        self.scroll.pack(fill='both', expand=True, padx=15, pady=10)

        self._load()

    # ── loading ───────────────────────────────────────────────────────────────

    def _load(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.scroll, text='Loading…',
                     text_color=C['text_secondary'],
                     font=('Segoe UI', 12, 'italic')).pack(pady=20)
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        notifications = []

        # ── Source 1: Sentinel incidents (already computed, no new scan) ─────
        if self._sentinel:
            try:
                for inc in self._sentinel.get_incidents(limit=20):
                    notifications.append({
                        'source':   '🤖 AI Sentinel',
                        'severity': inc.get('severity', 'MEDIUM'),
                        'title':    inc.get('title', 'Unknown incident'),
                        'detail':   inc.get('root_cause', '')[:120],
                        'time':     inc.get('timestamp', ''),
                        'type':     'sentinel',
                    })
            except Exception:
                pass

        # ── Source 2: Failed instances (targeted CMS query only) ─────────────
        if bo_session.connected:
            try:
                failed = bo_session.get_instances(status='failed', limit=10)
                for f in failed:
                    notifications.append({
                        'source':   '📋 Failed Instance',
                        'severity': 'HIGH',
                        'title':    f"Failed: {f.get('name','?')}",
                        'detail':   f"Owner: {f.get('owner','')} | "
                                    f"Started: {str(f.get('start_time',''))[:16]}",
                        'time':     str(f.get('start_time',''))[:16],
                        'type':     'instance',
                    })
            except Exception:
                pass

            # ── Source 3: Stopped servers ─────────────────────────────────────
            try:
                servers = bo_session.get_all_servers()
                for s in servers:
                    if not s.get('alive', True):
                        notifications.append({
                            'source':   '🖥 Server Alert',
                            'severity': 'CRITICAL',
                            'title':    f"Server Stopped: {s.get('name','?')}",
                            'detail':   f"Failures: {s.get('failures',0)} | "
                                        f"Host: {s.get('host','')}",
                            'time':     '',
                            'type':     'server',
                        })
            except Exception:
                pass

        self.after(0, lambda n=notifications: self._render(n))

    def _render(self, notifications):
        for w in self.scroll.winfo_children():
            w.destroy()

        if not notifications:
            frame = ctk.CTkFrame(self.scroll, fg_color=C['bg_tertiary'],
                                 corner_radius=8)
            frame.pack(fill='x', padx=10, pady=20)
            ctk.CTkLabel(frame,
                         text='✅  No notifications — system looks healthy!',
                         font=('Segoe UI', 13),
                         text_color=C['success']).pack(pady=30)
            self._badge.configure(text='0 notifications')
            return

        self._badge.configure(text=f'{len(notifications)} notification(s)')

        # Sort by severity
        order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
        notifications.sort(key=lambda x: order.get(x['severity'], 9))

        for n in notifications:
            self._render_card(n)

    def _render_card(self, n):
        sev   = n['severity']
        color = self.SEVERITY_COLORS.get(sev, C['bg_tertiary'])

        card = ctk.CTkFrame(self.scroll, fg_color=C['bg_tertiary'],
                            corner_radius=8)
        card.pack(fill='x', padx=8, pady=4)

        # Left severity bar
        bar = ctk.CTkFrame(card, fg_color=color, width=5, corner_radius=3)
        bar.pack(side='left', fill='y', padx=(0, 10))
        bar.pack_propagate(False)

        content = ctk.CTkFrame(card, fg_color='transparent')
        content.pack(side='left', fill='both', expand=True, pady=10)

        # Top row: source + severity badge + time
        top_row = ctk.CTkFrame(content, fg_color='transparent')
        top_row.pack(fill='x')

        ctk.CTkLabel(top_row, text=n['source'],
                     font=('Segoe UI', 10),
                     text_color=C['text_secondary']).pack(side='left')

        ctk.CTkLabel(top_row,
                     text=f' {sev} ',
                     fg_color=color,
                     corner_radius=4,
                     font=('Segoe UI', 9, 'bold'),
                     text_color='white').pack(side='left', padx=6)

        if n.get('time'):
            ctk.CTkLabel(top_row, text=n['time'],
                         font=('Segoe UI', 10),
                         text_color=C['text_secondary']).pack(side='right', padx=10)

        # Title
        ctk.CTkLabel(content, text=n['title'],
                     font=('Segoe UI', 12, 'bold'),
                     text_color=C['text_primary'],
                     anchor='w').pack(fill='x', pady=(2, 0))

        # Detail
        if n.get('detail'):
            ctk.CTkLabel(content, text=n['detail'],
                         font=('Segoe UI', 11),
                         text_color=C['text_secondary'],
                         anchor='w',
                         wraplength=800).pack(fill='x')
