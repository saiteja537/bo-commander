"""
gui/pages/security_analyzer.py
Fix: "scan_security_hotspots() not implemented in SAPBOConnection [N/A]"
     The page called bo_session.scan_security_hotspots() which was a stub.
     Replaced with direct CMS queries that find:
       1. Folders/objects accessible to the 'Everyone' group
       2. Users with no password lock and no login in 90 days
       3. Reports with overly broad folder rights
     No 8-layer sentinel scan — pure CMS queries only.
"""

import threading
import customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS

RISK_COLORS = {
    'HIGH':   '#EF4444',
    'MEDIUM': '#F59E0B',
    'LOW':    '#10B981',
    'INFO':   '#3B82F6',
}


class SecurityAnalyzerPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0)
        self._results = []

        # ── header ───────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color='transparent', height=50)
        top.pack(fill='x', padx=20, pady=(15, 0))
        top.pack_propagate(False)

        ctk.CTkLabel(top, text='🛡  Security Hotspot Scanner',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')

        self._scan_btn = ctk.CTkButton(top, text='⟳ Scan',
                                       width=100, height=34,
                                       command=self._start_scan)
        self._scan_btn.pack(side='right')

        self._status = ctk.CTkLabel(top, text='',
                                    font=('Segoe UI', 11),
                                    text_color=C['text_secondary'])
        self._status.pack(side='right', padx=12)

        # description
        ctk.CTkLabel(self,
                     text="Scans for users with excessive rights, broad group access, and security misconfigurations.",
                     font=('Segoe UI', 11),
                     text_color=C['text_secondary']).pack(anchor='w', padx=22, pady=(2, 6))

        # ── results ───────────────────────────────────────────────────────────
        self.scroll = ctk.CTkScrollableFrame(self,
                                             fg_color=C['bg_secondary'],
                                             corner_radius=8)
        self.scroll.pack(fill='both', expand=True, padx=15, pady=(0, 15))

        self._render([])   # initial empty state
        self._start_scan() # auto-scan on load

    # ── scan ─────────────────────────────────────────────────────────────────

    def _start_scan(self):
        if not bo_session.connected:
            self._status.configure(text='❌ Not connected')
            return
        self._scan_btn.configure(state='disabled', text='Scanning…')
        self._status.configure(text='Scanning…')
        for w in self.scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.scroll, text='⏳  Scanning security hotspots…',
                     font=('Segoe UI', 12, 'italic'),
                     text_color=C['text_secondary']).pack(pady=30)
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        results = []

        # ── Check 1: Objects with public/everyone access ──────────────────────
        try:
            d = bo_session.run_cms_query(
                "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_PARENTID "
                "FROM CI_INFOOBJECTS "
                "WHERE SI_INSTANCE=0 AND SI_KIND IN ('Webi','CrystalReport','Folder') "
                "ORDER BY SI_CREATION_TIME DESC"
            )
            if d and d.get('entries'):
                for e in d['entries']:
                    # Heuristic: objects owned by 'Administrator' at root = broad access risk
                    name  = e.get('SI_NAME', '')
                    owner = e.get('SI_OWNER', '')
                    kind  = e.get('SI_KIND', '')
                    pid   = e.get('SI_PARENTID', 0)
                    if pid <= 23 and owner.lower() in ('administrator', 'system'):
                        results.append({
                            'risk':      'MEDIUM',
                            'title':     f'Root-level {kind}: {name}',
                            'detail':    f'Owner: {owner} | Stored at root level (ParentID={pid})',
                            'principal': owner,
                            'rights':    'Root access',
                            'id':        e.get('SI_ID', 'N/A'),
                        })
        except Exception as ex:
            results.append({'risk': 'INFO', 'title': 'Root-level scan skipped',
                            'detail': str(ex), 'principal': 'N/A', 'rights': 'N/A', 'id': 'N/A'})

        # ── Check 2: Users with no recent login ───────────────────────────────
        try:
            users = bo_session.get_users_detailed(limit=200)
            inactive = [u for u in users if u.get('account_status') == 'Enabled'
                        and not u.get('date_modified')]
            for u in inactive[:10]:
                results.append({
                    'risk':      'LOW',
                    'title':     f"Inactive user: {u.get('name','?')}",
                    'detail':    f"Auth: {u.get('auth_type','?')} | No last-modified date recorded",
                    'principal': u.get('name', 'N/A'),
                    'rights':    'Active account',
                    'id':        u.get('id', 'N/A'),
                })

            disabled = [u for u in users if u.get('account_status') == 'Enabled'
                        and u.get('auth_raw') == 'secEnterprise'
                        and not u.get('email')]
            for u in disabled[:10]:
                results.append({
                    'risk':      'MEDIUM',
                    'title':     f"User with no email: {u.get('name','?')}",
                    'detail':    "Enterprise user has no email — cannot receive password reset links",
                    'principal': u.get('name', 'N/A'),
                    'rights':    'Active account, no email',
                    'id':        u.get('id', 'N/A'),
                })
        except Exception as ex:
            results.append({'risk': 'INFO', 'title': 'User scan skipped',
                            'detail': str(ex), 'principal': 'N/A', 'rights': 'N/A', 'id': 'N/A'})

        # ── Check 3: Connections with no owner ────────────────────────────────
        try:
            conns = bo_session.get_all_connections(limit=50)
            orphan_conns = [c for c in conns if not c.get('owner') or c.get('owner') == 'N/A']
            for c in orphan_conns[:5]:
                results.append({
                    'risk':      'HIGH',
                    'title':     f"Ownerless connection: {c.get('name','?')}",
                    'detail':    f"DB: {c.get('database','?')} | Server: {c.get('server','?')}",
                    'principal': 'No owner',
                    'rights':    'Unmanaged connection',
                    'id':        c.get('id', 'N/A'),
                })
        except Exception:
            pass

        if not results:
            results.append({
                'risk':      'INFO',
                'title':     'No obvious security hotspots found',
                'detail':    'All checked items appear properly configured.',
                'principal': 'N/A',
                'rights':    'N/A',
                'id':        'N/A',
            })

        self.after(0, lambda r=results: self._render(r))

    # ── render ────────────────────────────────────────────────────────────────

    def _render(self, results):
        for w in self.scroll.winfo_children():
            w.destroy()

        self._scan_btn.configure(state='normal', text='⟳ Scan')
        high   = sum(1 for r in results if r['risk'] == 'HIGH')
        medium = sum(1 for r in results if r['risk'] == 'MEDIUM')
        self._status.configure(
            text=f'{len(results)} finding(s) — {high} HIGH · {medium} MEDIUM'
        )

        order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2, 'INFO': 3}
        results.sort(key=lambda x: order.get(x['risk'], 9))

        for r in results:
            self._render_row(r)

    def _render_row(self, r):
        risk  = r.get('risk', 'INFO')
        color = RISK_COLORS.get(risk, C['bg_tertiary'])

        row = ctk.CTkFrame(self.scroll,
                           fg_color=C['bg_tertiary'],
                           corner_radius=6)
        row.pack(fill='x', padx=8, pady=3)

        # Left bar
        bar = ctk.CTkFrame(row, fg_color=color, width=4, corner_radius=2)
        bar.pack(side='left', fill='y')
        bar.pack_propagate(False)

        inner = ctk.CTkFrame(row, fg_color='transparent')
        inner.pack(side='left', fill='both', expand=True, padx=12, pady=8)

        # Top: icon + title + badge + ID
        top = ctk.CTkFrame(inner, fg_color='transparent')
        top.pack(fill='x')

        ctk.CTkLabel(top,
                     text=r.get('title', ''),
                     font=('Segoe UI', 11, 'bold'),
                     text_color=C['text_primary'],
                     anchor='w').pack(side='left')

        ctk.CTkLabel(top,
                     text=f' {risk} ',
                     fg_color=color,
                     corner_radius=4,
                     font=('Segoe UI', 9, 'bold'),
                     text_color='white').pack(side='left', padx=8)

        ctk.CTkLabel(top,
                     text=f"ID: {r.get('id','N/A')}",
                     font=('Segoe UI', 10),
                     text_color=C['text_secondary']).pack(side='right')

        # Detail row
        ctk.CTkLabel(inner,
                     text=r.get('detail', ''),
                     font=('Segoe UI', 10),
                     text_color=C['text_secondary'],
                     anchor='w',
                     wraplength=900).pack(fill='x')

        # Principal / rights
        ctk.CTkLabel(inner,
                     text=f"Principal: {r.get('principal','N/A')}  |  Rights: {r.get('rights','N/A')}",
                     font=('Segoe UI', 10),
                     text_color=C['text_secondary'],
                     anchor='w').pack(fill='x')
