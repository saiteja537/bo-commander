"""
gui/pages/self_healing.py
Fix: Page produced no output for 5+ minutes.
     Root cause: was triggering full 8-layer Sentinel scan for every action,
     which is slow and returns nothing to the UI.

Design: Self Healing uses TARGETED actions only:
  - Reschedule failed instances (CMS query + REST action)
  - Purge old instances (CMS query + REST delete)
  - Restart stopped servers (REST toggle_server_state)
  - No sentinel / no log scan — just direct CMS/REST operations.
"""

import threading
import customtkinter as ctk
from datetime import datetime
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS

ACTIONS = [
    {
        'id':    'reschedule_failed',
        'icon':  '🔁',
        'title': 'Reschedule Failed Instances',
        'desc':  'Finds all failed report instances and retriggers them.',
        'color': C['warning'],
    },
    {
        'id':    'purge_old_30',
        'icon':  '🗑',
        'title': 'Purge Instances > 30 Days',
        'desc':  'Deletes completed instances older than 30 days to free CMS space.',
        'color': '#F97316',
    },
    {
        'id':    'restart_stopped',
        'icon':  '▶',
        'title': 'Start Stopped Servers',
        'desc':  'Identifies stopped BO servers and sends a start command to each.',
        'color': C['primary'],
    },
    {
        'id':    'health_check',
        'icon':  '❤',
        'title': 'Quick Health Check',
        'desc':  'Counts failed instances, stopped servers, and missing universes.',
        'color': C['success'],
    },
]


class SelfHealingPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0)
        self._log_lines = []

        # ── header ───────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color='transparent', height=50)
        top.pack(fill='x', padx=20, pady=(15, 0))
        top.pack_propagate(False)

        ctk.CTkLabel(top, text='⚕  Self Healing',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')

        ctk.CTkLabel(top,
                     text='Targeted remediation actions — no full log scan required',
                     font=('Segoe UI', 11),
                     text_color=C['text_secondary']).pack(side='left', padx=15)

        # ── action cards ──────────────────────────────────────────────────────
        cards_frame = ctk.CTkFrame(self, fg_color='transparent')
        cards_frame.pack(fill='x', padx=15, pady=12)

        for i, action in enumerate(ACTIONS):
            self._build_action_card(cards_frame, action, col=i % 4)

        for c in range(4):
            cards_frame.grid_columnconfigure(c, weight=1)

        # ── output log ────────────────────────────────────────────────────────
        log_hdr = ctk.CTkFrame(self, fg_color='transparent')
        log_hdr.pack(fill='x', padx=20, pady=(5, 0))

        ctk.CTkLabel(log_hdr, text='📋  Activity Log',
                     font=('Segoe UI', 13, 'bold'),
                     text_color=C['text_primary']).pack(side='left')

        ctk.CTkButton(log_hdr, text='Clear Log', width=80, height=26,
                      fg_color=C['bg_tertiary'],
                      text_color=C['text_secondary'],
                      command=self._clear_log).pack(side='right')

        self.log_box = ctk.CTkScrollableFrame(self,
                                              fg_color=C['bg_secondary'],
                                              corner_radius=6)
        self.log_box.pack(fill='both', expand=True, padx=15, pady=(5, 15))

        self._log('ℹ  Self Healing ready. Select an action above.', C['text_secondary'])

    # ── card builder ─────────────────────────────────────────────────────────

    def _build_action_card(self, parent, action, col):
        card = ctk.CTkFrame(parent, fg_color=C['bg_secondary'],
                            corner_radius=10,
                            border_width=1,
                            border_color=C['bg_tertiary'])
        card.grid(row=0, column=col, padx=6, pady=6, sticky='nsew')

        # Icon
        icon_f = ctk.CTkFrame(card, fg_color=action['color'],
                              width=44, height=44, corner_radius=10)
        icon_f.pack(pady=(14, 6), padx=14, anchor='w')
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text=action['icon'],
                     font=('Segoe UI', 20)).place(relx=.5, rely=.5, anchor='center')

        ctk.CTkLabel(card, text=action['title'],
                     font=('Segoe UI', 11, 'bold'),
                     text_color=C['text_primary'],
                     wraplength=180, justify='left').pack(anchor='w', padx=14)

        ctk.CTkLabel(card, text=action['desc'],
                     font=('Segoe UI', 10),
                     text_color=C['text_secondary'],
                     wraplength=180, justify='left').pack(anchor='w', padx=14, pady=(2, 10))

        ctk.CTkButton(card, text='Run',
                      height=30,
                      fg_color=action['color'],
                      hover_color=action['color'],
                      command=lambda aid=action['id']: self._run_action(aid)
                      ).pack(fill='x', padx=14, pady=(0, 14))

    # ── actions ───────────────────────────────────────────────────────────────

    def _run_action(self, action_id):
        if not bo_session.connected:
            self._log('❌  Not connected to BO.', C['danger'])
            return
        self._log(f'⏳  Running: {action_id}…', C['warning'])
        threading.Thread(target=self._execute, args=(action_id,), daemon=True).start()

    def _execute(self, action_id):
        try:
            if action_id == 'reschedule_failed':
                count, msg = bo_session.reschedule_failed_instances()
                self.after(0, lambda: self._log(f'✅  {msg}', C['success']))

            elif action_id == 'purge_old_30':
                count, msg = bo_session.purge_old_instances(days=30)
                self.after(0, lambda: self._log(f'✅  {msg}', C['success']))

            elif action_id == 'restart_stopped':
                servers  = bo_session.get_all_servers()
                stopped  = [s for s in servers if not s.get('alive')]
                if not stopped:
                    self.after(0, lambda: self._log('✅  All servers are already running.', C['success']))
                    return
                ok = 0
                for s in stopped:
                    result, msg = bo_session.toggle_server_state(s['id'], 'start')
                    color = C['success'] if result else C['danger']
                    icon  = '✅' if result else '❌'
                    name  = s['name']
                    self.after(0, lambda i=icon, n=name, m=msg, c=color:
                               self._log(f'{i}  {n}: {m}', c))
                    if result:
                        ok += 1
                self.after(0, lambda: self._log(
                    f'▶  Start sent to {ok}/{len(stopped)} stopped servers.', C['primary']))

            elif action_id == 'health_check':
                stats    = bo_session.get_dashboard_stats()
                failed   = stats.get('failed_instances', 0)
                srv_tot  = stats.get('servers_total', 0)
                srv_run  = stats.get('servers_running', 0)
                reports  = stats.get('reports', 0)
                universes= stats.get('universes', 0)
                msgs = [
                    f"❤  Health check at {datetime.now().strftime('%H:%M:%S')}",
                    f"   Servers: {srv_run}/{srv_tot} running",
                    f"   Failed instances: {failed}",
                    f"   Reports: {reports}  |  Universes: {universes}",
                ]
                for m in msgs:
                    color = C['danger'] if failed > 0 and 'failed' in m.lower() else C['text_primary']
                    self.after(0, lambda msg=m, c=color: self._log(msg, c))

        except Exception as e:
            self.after(0, lambda err=str(e): self._log(f'❌  Error: {err}', C['danger']))

    # ── log helpers ───────────────────────────────────────────────────────────

    def _log(self, text, color=None):
        color = color or C['text_primary']
        lbl = ctk.CTkLabel(self.log_box,
                           text=f"[{datetime.now().strftime('%H:%M:%S')}]  {text}",
                           font=('Consolas', 11),
                           text_color=color,
                           anchor='w',
                           justify='left',
                           wraplength=1000)
        lbl.pack(fill='x', padx=10, pady=1)
        try:
            self.log_box._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _clear_log(self):
        for w in self.log_box.winfo_children():
            w.destroy()
