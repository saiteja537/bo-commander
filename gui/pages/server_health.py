"""
server_health.py — Server Health Dashboard
Real-time BO server monitoring: status, backlog, memory, restarts.
Detects zombie/overloaded servers and provides 1-click fix actions.
"""
import threading
import customtkinter as ctk
from datetime import datetime
from config import Config
from core.sapbo_connection import bo_session
import logging

logger = logging.getLogger("ServerHealth")

# Server status → color
STATUS_COLORS = {
    'running':  '#10B981',
    'stopped':  '#EF4444',
    'starting': '#F59E0B',
    'stopping': '#F59E0B',
    'failed':   '#DC2626',
    'unknown':  '#6B7280',
}

# Server type → icon
SERVER_ICONS = {
    'cms':            '🏛️',
    'webi':           '📊',
    'crystal':        '💎',
    'adaptive':       '⚙️',
    'tomcat':         '🌐',
    'sia':            '🤖',
    'job':            '📋',
    'file':           '📁',
    'connection':     '🔌',
    'event':          '📡',
    'cache':          '⚡',
    'destination':    '📤',
    'audit':          '🔍',
}


def _get_icon(name: str) -> str:
    n = name.lower()
    for key, icon in SERVER_ICONS.items():
        if key in n:
            return icon
    return '🖥️'


class ServerHealthPage(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=Config.COLORS['bg_primary'], **kwargs)
        self._destroyed  = False
        self._servers    = []
        self._auto_refresh = ctk.BooleanVar(value=False)
        self._refresh_job = None
        self._build_ui()
        self._load()

    def _safe_after(self, ms, fn):
        if not self._destroyed:
            try:
                self.after(ms, fn)
            except Exception:
                pass

    def destroy(self):
        self._destroyed = True
        if self._refresh_job:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
        super().destroy()

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=Config.COLORS['bg_secondary'])
        hdr.pack(fill='x', padx=15, pady=(15, 5))
        left = ctk.CTkFrame(hdr, fg_color='transparent')
        left.pack(side='left', padx=12, pady=8)
        ctk.CTkLabel(left, text="🖥️  Server Health Dashboard",
                     font=Config.FONTS['sub_header'],
                     text_color=Config.COLORS['text_primary']).pack(anchor='w')
        ctk.CTkLabel(left,
                     text="Real-time BO server status · Detect zombie/overloaded servers · 1-click restart",
                     font=Config.FONTS['small'],
                     text_color=Config.COLORS['text_secondary']).pack(anchor='w')
        btn_f = ctk.CTkFrame(hdr, fg_color='transparent')
        btn_f.pack(side='right', padx=10, pady=8)
        ctk.CTkButton(btn_f, text="⟳ Refresh", width=90,
                      fg_color=Config.COLORS['primary'],
                      command=self._load).pack(side='left', padx=3)
        ctk.CTkButton(btn_f, text="▶ Start All", width=90,
                      fg_color=Config.COLORS['accent'],
                      command=self._start_all).pack(side='left', padx=3)
        ctk.CTkButton(btn_f, text="🔄 Restart All", width=100,
                      fg_color=Config.COLORS['warning'],
                      command=self._restart_all).pack(side='left', padx=3)
        ctk.CTkCheckBox(btn_f, text="Auto (30s)", variable=self._auto_refresh,
                        text_color=Config.COLORS['text_secondary'],
                        command=self._toggle_auto).pack(side='left', padx=8)

        # Health summary bar
        self.health_bar = ctk.CTkFrame(self, fg_color=Config.COLORS['bg_secondary'])
        self.health_bar.pack(fill='x', padx=15, pady=(0, 5))
        self._health_lbls = {}
        for key, label, color in [
            ('running',  '✅ Running',   Config.COLORS['success']),
            ('stopped',  '❌ Stopped',   Config.COLORS['danger']),
            ('zombies',  '🧟 Zombies',   '#F97316'),
            ('overload', '🔥 Overloaded', Config.COLORS['warning']),
            ('total',    '📊 Total',     Config.COLORS['primary']),
        ]:
            card = ctk.CTkFrame(self.health_bar, fg_color=Config.COLORS['bg_tertiary'], width=140)
            card.pack(side='left', padx=5, pady=8, fill='y')
            card.pack_propagate(False)
            ctk.CTkLabel(card, text=label, font=Config.FONTS['small'],
                         text_color=Config.COLORS['text_secondary']).pack(pady=(6, 0))
            lbl = ctk.CTkLabel(card, text="—", font=('Segoe UI', 20, 'bold'),
                                text_color=color)
            lbl.pack(pady=(0, 6))
            self._health_lbls[key] = lbl

        self.status_lbl = ctk.CTkLabel(self, text="Loading...",
                                        font=Config.FONTS['small'],
                                        text_color=Config.COLORS['text_secondary'])
        self.status_lbl.pack(anchor='w', padx=20, pady=(0, 4))

        # Col headers
        col_hdr = ctk.CTkFrame(self, fg_color=Config.COLORS['bg_tertiary'])
        col_hdr.pack(fill='x', padx=15, pady=(0, 1))
        for col, w in [("Server", 280), ("Status", 100), ("Type", 160),
                        ("Failures", 80), ("Last Start", 140), ("Actions", 180)]:
            ctk.CTkLabel(col_hdr, text=col, width=w, anchor='w',
                         font=('Segoe UI', 11, 'bold'),
                         text_color=Config.COLORS['text_secondary']).pack(side='left', padx=5, pady=5)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=Config.COLORS['bg_secondary'])
        self.scroll.pack(fill='both', expand=True, padx=15, pady=(0, 15))

    def _load(self):
        if not bo_session.connected:
            self._set_status("⚠️  Not connected to BO server.")
            return
        threading.Thread(target=self._fetch_thread, daemon=True).start()

    def _fetch_thread(self):
        try:
            if hasattr(bo_session, 'get_all_servers'):
                servers = bo_session.get_all_servers()
            elif hasattr(bo_session, '_query'):
                rows = bo_session._query(
                    "SELECT SI_ID, SI_NAME, SI_KIND, SI_SERVER_IS_RUNNING, "
                    "SI_SERVER_NUMCONNECTION, SI_FAILURES, SI_STARTTIME, "
                    "SI_SERVER_DESCRIPTION, SI_PROCESSID "
                    "FROM CI_SYSTEMOBJECTS WHERE SI_KIND='Server' ORDER BY SI_NAME"
                )
                servers = []
                for r in rows:
                    running = bool(r.get('SI_SERVER_IS_RUNNING', False))
                    servers.append({
                        'id':          r.get('SI_ID', 0),
                        'name':        r.get('SI_NAME', 'Unknown'),
                        'status':      'Running' if running else 'Stopped',
                        'kind':        r.get('SI_KIND', 'Server'),
                        'connections': r.get('SI_SERVER_NUMCONNECTION', 0),
                        'failures':    r.get('SI_FAILURES', 0),
                        'start_time':  r.get('SI_STARTTIME', 0),
                        'pid':         r.get('SI_PROCESSID', 0),
                    })
            else:
                servers = []

            self._servers = servers
            self._safe_after(0, self._render)
        except Exception as e:
            logger.error(f"Server health fetch error: {e}")
            self._servers = []
            self._safe_after(0, lambda: self._set_status(f"Error: {e}"))

    def _render(self):
        if self._destroyed:
            return
        try:
            if not self.scroll.winfo_exists():
                return
            for w in self.scroll.winfo_children():
                w.destroy()
        except Exception:
            return

        servers  = self._servers
        running  = sum(1 for s in servers if 'running' in str(s.get('status', '')).lower())
        stopped  = len(servers) - running
        zombies  = sum(1 for s in servers if int(s.get('failures', 0) or 0) > 10)
        overload = sum(1 for s in servers if int(s.get('connections', 0) or 0) > 100)

        self._health_lbls['running'].configure(text=str(running))
        self._health_lbls['stopped'].configure(text=str(stopped),
                                                text_color=Config.COLORS['danger'] if stopped else Config.COLORS['success'])
        self._health_lbls['zombies'].configure(text=str(zombies),
                                                text_color='#F97316' if zombies else Config.COLORS['success'])
        self._health_lbls['overload'].configure(text=str(overload),
                                                 text_color=Config.COLORS['warning'] if overload else Config.COLORS['success'])
        self._health_lbls['total'].configure(text=str(len(servers)))

        ts = datetime.now().strftime('%H:%M:%S')
        self._set_status(
            f"✅ {running}/{len(servers)} servers running — "
            f"{stopped} stopped, {zombies} zombie, {overload} overloaded  (updated {ts})"
        )

        if not servers:
            ctk.CTkLabel(self.scroll, text="No server data available.",
                         text_color=Config.COLORS['text_secondary']).pack(pady=30)
            return

        # Sort: stopped first, then by failures desc
        servers_sorted = sorted(servers,
                                 key=lambda s: (0 if 'running' not in str(s.get('status','')).lower() else 1,
                                                -int(s.get('failures', 0) or 0)))

        for s in servers_sorted:
            self._render_server_row(s)

    def _render_server_row(self, s):
        status  = str(s.get('status', 'Unknown'))
        sc      = STATUS_COLORS.get(status.lower(), '#6B7280')
        fail    = int(s.get('failures', 0) or 0)
        name    = str(s.get('name', 'Unknown'))
        icon    = _get_icon(name)
        is_zombie   = fail > 10
        is_overload = int(s.get('connections', 0) or 0) > 100

        bg = Config.COLORS['bg_secondary']
        if is_zombie:
            bg = '#1C1008'
        elif 'stopped' in status.lower():
            bg = '#1A0808'

        row = ctk.CTkFrame(self.scroll, fg_color=bg, height=44)
        row.pack(fill='x', pady=1)
        row.pack_propagate(False)

        # Name + icon
        name_f = ctk.CTkFrame(row, fg_color='transparent', width=280)
        name_f.pack(side='left', padx=5)
        name_f.pack_propagate(False)
        display = f"{icon}  {name[:32]}"
        if is_zombie:
            display += "  🧟"
        if is_overload:
            display += "  🔥"
        ctk.CTkLabel(name_f, text=display, anchor='w',
                     text_color=Config.COLORS['text_primary']).pack(fill='x', padx=3, pady=10)

        ctk.CTkLabel(row, text=status, width=100, anchor='w',
                     text_color=sc, font=('Segoe UI', 11, 'bold')).pack(side='left', padx=3)
        ctk.CTkLabel(row, text=str(s.get('kind', 'Server'))[:22], width=160, anchor='w',
                     text_color=Config.COLORS['text_secondary']).pack(side='left', padx=3)
        fc = Config.COLORS['danger'] if fail > 5 else (Config.COLORS['warning'] if fail > 0 else Config.COLORS['success'])
        ctk.CTkLabel(row, text=str(fail), width=80, anchor='w',
                     text_color=fc, font=('Segoe UI', 11, 'bold')).pack(side='left', padx=3)
        ctk.CTkLabel(row, text=self._fmt_date(s.get('start_time', 0)), width=140, anchor='w',
                     text_color=Config.COLORS['text_secondary']).pack(side='left', padx=3)

        # Action buttons
        act_f = ctk.CTkFrame(row, fg_color='transparent')
        act_f.pack(side='left', padx=4)
        sid = s.get('id')
        ctk.CTkButton(act_f, text="▶", width=34, height=26,
                      fg_color=Config.COLORS['accent'],
                      command=lambda i=sid: self._server_action(i, 'start')).pack(side='left', padx=2)
        ctk.CTkButton(act_f, text="⏹", width=34, height=26,
                      fg_color=Config.COLORS['danger'],
                      command=lambda i=sid: self._server_action(i, 'stop')).pack(side='left', padx=2)
        ctk.CTkButton(act_f, text="↺", width=34, height=26,
                      fg_color=Config.COLORS['warning'],
                      command=lambda i=sid: self._server_action(i, 'restart')).pack(side='left', padx=2)
        ctk.CTkButton(act_f, text="ℹ️", width=34, height=26,
                      fg_color=Config.COLORS['bg_tertiary'],
                      command=lambda sv=s: self._show_detail(sv)).pack(side='left', padx=2)

    def _server_action(self, server_id, action):
        if not server_id:
            return
        def _do():
            try:
                method = getattr(bo_session, f'{action}_server', None)
                if method:
                    method(server_id)
                self._safe_after(1500, self._load)
            except Exception as e:
                logger.error(f"Server {action} error: {e}")
        threading.Thread(target=_do, daemon=True).start()
        self._set_status(f"{'▶ Starting' if action=='start' else '⏹ Stopping' if action=='stop' else '↺ Restarting'} server...")

    def _start_all(self):
        if hasattr(bo_session, 'start_all_servers'):
            threading.Thread(target=lambda: (bo_session.start_all_servers(),
                                              self._safe_after(2000, self._load)), daemon=True).start()

    def _restart_all(self):
        if hasattr(bo_session, 'restart_all_servers'):
            threading.Thread(target=lambda: (bo_session.restart_all_servers(),
                                              self._safe_after(3000, self._load)), daemon=True).start()

    def _toggle_auto(self):
        if self._auto_refresh.get():
            self._schedule_auto()
        elif self._refresh_job:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass

    def _schedule_auto(self):
        if self._auto_refresh.get() and not self._destroyed:
            self._load()
            self._refresh_job = self.after(30000, self._schedule_auto)

    def _show_detail(self, s):
        dlg = ctk.CTkToplevel(self)
        dlg.title(f"Server Detail — {s.get('name','?')[:40]}")
        dlg.geometry("500x350")
        dlg.configure(fg_color=Config.COLORS['bg_primary'])
        tb = ctk.CTkTextbox(dlg, fg_color=Config.COLORS['bg_secondary'],
                             text_color=Config.COLORS['text_primary'],
                             font=('Consolas', 11))
        tb.pack(fill='both', expand=True, padx=15, pady=15)
        lines = "\n".join(f"  {k}: {v}" for k, v in s.items())
        tb.insert('0.0', lines)
        tb.configure(state='disabled')

    def _fmt_date(self, epoch_val):
        try:
            if not epoch_val or epoch_val == 0:
                return "N/A"
            return datetime.fromtimestamp(int(epoch_val)).strftime('%Y-%m-%d %H:%M')
        except Exception:
            return str(epoch_val)

    def _set_status(self, text):
        if not self._destroyed:
            try:
                self.status_lbl.configure(text=text)
            except Exception:
                pass
