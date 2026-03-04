"""
user_activity.py — User Activity Tracker & License Optimizer
Detect inactive users, never-logged-in users, license waste.
Shows management-ready license cleanup recommendations.
"""
import threading
import customtkinter as ctk
from datetime import datetime, timedelta
from config import Config
from core.sapbo_connection import bo_session
import logging

logger = logging.getLogger("UserActivity")


def _fmt_date(epoch_val):
    try:
        if not epoch_val or epoch_val == 0:
            return "Never"
        return datetime.fromtimestamp(int(epoch_val)).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return str(epoch_val)


def _days_since(epoch_val):
    try:
        if not epoch_val or epoch_val == 0:
            return 99999
        return int((datetime.now().timestamp() - int(epoch_val)) / 86400)
    except Exception:
        return 0


class UserActivityPage(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=Config.COLORS['bg_primary'], **kwargs)
        self._destroyed = False
        self._users     = []
        self._tab       = 'inactive'
        self._inactive_days = 90
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
        super().destroy()

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=Config.COLORS['bg_secondary'])
        hdr.pack(fill='x', padx=15, pady=(15, 5))
        left = ctk.CTkFrame(hdr, fg_color='transparent')
        left.pack(side='left', padx=12, pady=8)
        ctk.CTkLabel(left, text="👤  User Activity Tracker",
                     font=Config.FONTS['sub_header'],
                     text_color=Config.COLORS['text_primary']).pack(anchor='w')
        ctk.CTkLabel(left,
                     text="License optimization · Inactive user detection · Activity analysis",
                     font=Config.FONTS['small'],
                     text_color=Config.COLORS['text_secondary']).pack(anchor='w')
        btn_f = ctk.CTkFrame(hdr, fg_color='transparent')
        btn_f.pack(side='right', padx=10, pady=8)
        ctk.CTkLabel(btn_f, text="Inactive after (days):",
                     font=Config.FONTS['small'],
                     text_color=Config.COLORS['text_secondary']).pack(side='left', padx=5)
        self.days_entry = ctk.CTkEntry(btn_f, width=60)
        self.days_entry.insert(0, "90")
        self.days_entry.pack(side='left', padx=4)
        ctk.CTkButton(btn_f, text="⟳ Load", width=80,
                      fg_color=Config.COLORS['primary'],
                      command=self._load).pack(side='left', padx=6)

        # Stat cards
        stats = ctk.CTkFrame(self, fg_color=Config.COLORS['bg_secondary'])
        stats.pack(fill='x', padx=15, pady=(0, 5))
        self._stat_lbls = {}
        for key, label, color in [
            ('total',     '👥 Total Users',        Config.COLORS['primary']),
            ('inactive',  '💤 Inactive Users',     Config.COLORS['warning']),
            ('never',     '🚫 Never Logged In',    Config.COLORS['danger']),
            ('active',    '✅ Active (30 days)',   Config.COLORS['success']),
            ('savings',   '💰 License Savings',    '#A78BFA'),
        ]:
            card = ctk.CTkFrame(stats, fg_color=Config.COLORS['bg_tertiary'], width=160)
            card.pack(side='left', padx=5, pady=8, fill='y')
            card.pack_propagate(False)
            ctk.CTkLabel(card, text=label, font=Config.FONTS['small'],
                         text_color=Config.COLORS['text_secondary']).pack(pady=(6, 0))
            lbl = ctk.CTkLabel(card, text="—", font=('Segoe UI', 18, 'bold'),
                                text_color=color)
            lbl.pack(pady=(0, 6))
            self._stat_lbls[key] = lbl

        # Tab bar
        tab_f = ctk.CTkFrame(self, fg_color='transparent')
        tab_f.pack(fill='x', padx=15, pady=(0, 5))
        self._tab_btns = {}
        for tab_id, tab_label in [
            ('inactive', '💤 Inactive Users'),
            ('never',    '🚫 Never Logged In'),
            ('active',   '✅ Most Active'),
            ('all',      '📋 All Users'),
            ('report',   '📊 License Report'),
        ]:
            btn = ctk.CTkButton(tab_f, text=tab_label, width=140,
                                fg_color=Config.COLORS['primary'] if tab_id == self._tab
                                         else Config.COLORS['bg_tertiary'],
                                hover_color=Config.COLORS['primary_hover'],
                                command=lambda t=tab_id: self._switch_tab(t))
            btn.pack(side='left', padx=3)
            self._tab_btns[tab_id] = btn

        self.status_lbl = ctk.CTkLabel(self, text="Loading...",
                                        font=Config.FONTS['small'],
                                        text_color=Config.COLORS['text_secondary'])
        self.status_lbl.pack(anchor='w', padx=20, pady=(0, 4))
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=Config.COLORS['bg_secondary'])
        self.scroll.pack(fill='both', expand=True, padx=15, pady=(0, 15))

    def _load(self):
        if not bo_session.connected:
            self._set_status("⚠️  Not connected.")
            return
        try:
            self._inactive_days = int(self.days_entry.get())
        except Exception:
            self._inactive_days = 90
        self._set_status("⏳ Loading user activity data...")
        threading.Thread(target=self._fetch_thread, daemon=True).start()

    def _fetch_thread(self):
        try:
            query = (
                "SELECT SI_ID, SI_NAME, SI_FULLNAME, SI_EMAIL, "
                "SI_LASTLOGONTIME, SI_DISABLED, SI_NAMED_USER, "
                "SI_CONCURRENT_USER, SI_CREATION_TIME "
                "FROM CI_SYSTEMOBJECTS WHERE SI_KIND='User' "
                "ORDER BY SI_LASTLOGONTIME DESC"
            )
            rows = bo_session._query(query) if hasattr(bo_session, '_query') else []
            if not rows and hasattr(bo_session, 'get_users_detailed'):
                rows = bo_session.get_users_detailed()

            users = []
            for r in rows:
                last = r.get('SI_LASTLOGONTIME', r.get('last_logon', 0)) or 0
                users.append({
                    'id':         r.get('SI_ID', r.get('id', 0)),
                    'name':       r.get('SI_NAME', r.get('name', 'Unknown')),
                    'full_name':  r.get('SI_FULLNAME', r.get('full_name', '')),
                    'email':      r.get('SI_EMAIL', r.get('email', '')),
                    'last_logon': int(last),
                    'days_since': _days_since(last),
                    'disabled':   bool(r.get('SI_DISABLED', r.get('disabled', False))),
                    'named':      bool(r.get('SI_NAMED_USER', True)),
                    'created':    r.get('SI_CREATION_TIME', 0),
                })

            self._users = users
            self._safe_after(0, self._render)
        except Exception as e:
            logger.error(f"User activity fetch error: {e}")
            self._users = []
            self._safe_after(0, lambda: self._set_status(f"Error: {e}"))

    def _switch_tab(self, tab):
        self._tab = tab
        for t, btn in self._tab_btns.items():
            try:
                btn.configure(fg_color=Config.COLORS['primary'] if t == tab
                               else Config.COLORS['bg_tertiary'])
            except Exception:
                pass
        self._render()

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

        # Compute stats
        inactive = [u for u in self._users if u['days_since'] >= self._inactive_days and not u['disabled']]
        never    = [u for u in self._users if u['last_logon'] == 0]
        active   = [u for u in self._users if u['days_since'] <= 30 and not u['disabled']]
        cleanup  = len(inactive) + len(never)

        self._stat_lbls['total'].configure(text=str(len(self._users)))
        self._stat_lbls['inactive'].configure(text=str(len(inactive)))
        self._stat_lbls['never'].configure(text=str(len(never)))
        self._stat_lbls['active'].configure(text=str(len(active)))
        self._stat_lbls['savings'].configure(text=f"{cleanup} licenses")

        self._set_status(
            f"✅ {len(self._users)} users loaded — "
            f"{len(inactive)} inactive ({self._inactive_days}d+) · "
            f"{len(never)} never logged in · "
            f"{cleanup} potential license savings"
        )

        if self._tab == 'inactive':
            self._render_user_table(sorted(inactive, key=lambda u: u['days_since'], reverse=True),
                                     "💤 Inactive Users", Config.COLORS['warning'])
        elif self._tab == 'never':
            self._render_user_table(never, "🚫 Never Logged In", Config.COLORS['danger'])
        elif self._tab == 'active':
            self._render_user_table(sorted(active, key=lambda u: u['days_since']),
                                     "✅ Most Active Users", Config.COLORS['success'])
        elif self._tab == 'all':
            self._render_user_table(sorted(self._users, key=lambda u: u['days_since']),
                                     "📋 All Users", Config.COLORS['text_primary'])
        elif self._tab == 'report':
            self._render_license_report(inactive, never, active)

    def _render_user_table(self, users, title, color):
        ctk.CTkLabel(self.scroll, text=f"{title}  ({len(users)})",
                     font=('Segoe UI', 13, 'bold'),
                     text_color=color).pack(anchor='w', padx=5, pady=(8, 4))

        if not users:
            ctk.CTkLabel(self.scroll, text="✅  None found.",
                         text_color=Config.COLORS['success']).pack(pady=20)
            return

        # Column headers
        hdr = ctk.CTkFrame(self.scroll, fg_color=Config.COLORS['bg_tertiary'])
        hdr.pack(fill='x', pady=(0, 2))
        for col, w in [("Username", 180), ("Full Name", 160), ("Email", 220),
                        ("Last Login", 140), ("Days Ago", 80), ("Type", 90)]:
            ctk.CTkLabel(hdr, text=col, width=w, anchor='w',
                         font=('Segoe UI', 11, 'bold'),
                         text_color=Config.COLORS['text_secondary']).pack(side='left', padx=4, pady=5)

        for u in users:
            row = ctk.CTkFrame(self.scroll, fg_color=Config.COLORS['bg_secondary'], height=36)
            row.pack(fill='x', pady=1)
            row.pack_propagate(False)
            days = u['days_since']
            age_color = (Config.COLORS['danger'] if days > 365
                         else Config.COLORS['warning'] if days > 90
                         else Config.COLORS['success'])
            days_str = "Never" if days == 99999 else str(days)
            utype = "Named" if u['named'] else "Concurrent"
            if u['disabled']:
                utype = "Disabled"
            ctk.CTkLabel(row, text=str(u['name'])[:24],   width=180, anchor='w', text_color=Config.COLORS['text_primary']).pack(side='left', padx=4)
            ctk.CTkLabel(row, text=str(u['full_name'])[:20], width=160, anchor='w', text_color=Config.COLORS['text_secondary']).pack(side='left', padx=3)
            ctk.CTkLabel(row, text=str(u['email'])[:28],   width=220, anchor='w', text_color=Config.COLORS['text_secondary']).pack(side='left', padx=3)
            ctk.CTkLabel(row, text=_fmt_date(u['last_logon']), width=140, anchor='w', text_color=Config.COLORS['text_secondary']).pack(side='left', padx=3)
            ctk.CTkLabel(row, text=days_str,               width=80,  anchor='w', text_color=age_color, font=('Segoe UI', 11, 'bold')).pack(side='left', padx=3)
            ctk.CTkLabel(row, text=utype,                  width=90,  anchor='w', text_color=Config.COLORS['text_secondary']).pack(side='left', padx=3)

    def _render_license_report(self, inactive, never, active):
        report_items = [
            ("Total Users", len(self._users), Config.COLORS['primary']),
            (f"Inactive > {self._inactive_days} days", len(inactive), Config.COLORS['warning']),
            ("Never Logged In", len(never), Config.COLORS['danger']),
            ("Active Last 30 Days", len(active), Config.COLORS['success']),
            ("Disabled Accounts", sum(1 for u in self._users if u['disabled']), Config.COLORS['text_secondary']),
            ("Potential Removals", len(inactive) + len(never), '#A78BFA'),
        ]

        ctk.CTkLabel(self.scroll, text="📊  License Optimization Report",
                     font=('Segoe UI', 14, 'bold'),
                     text_color=Config.COLORS['text_primary']).pack(anchor='w', padx=5, pady=(8, 8))

        for label, value, color in report_items:
            row = ctk.CTkFrame(self.scroll, fg_color=Config.COLORS['bg_tertiary'], height=44)
            row.pack(fill='x', pady=2, padx=5)
            row.pack_propagate(False)
            ctk.CTkLabel(row, text=label, font=Config.FONTS['body'],
                         text_color=Config.COLORS['text_primary']).pack(side='left', padx=16)
            ctk.CTkLabel(row, text=str(value), font=('Segoe UI', 16, 'bold'),
                         text_color=color).pack(side='right', padx=16)

        # Recommendation
        cleanup = len(inactive) + len(never)
        rec_text = (
            f"💡 Recommendation: {cleanup} user account(s) are candidates for removal.\n"
            f"Disabling/removing these could free {cleanup} license(s) and reduce CMS overhead.\n"
            f"Review the 'Inactive Users' and 'Never Logged In' tabs before taking action."
        )
        rec = ctk.CTkFrame(self.scroll, fg_color=Config.COLORS['bg_tertiary'])
        rec.pack(fill='x', pady=8, padx=5)
        ctk.CTkLabel(rec, text=rec_text, font=Config.FONTS['body'],
                     text_color=Config.COLORS['accent'],
                     wraplength=900, justify='left').pack(padx=16, pady=12)

    def _set_status(self, text):
        if not self._destroyed:
            try:
                self.status_lbl.configure(text=text)
            except Exception:
                pass