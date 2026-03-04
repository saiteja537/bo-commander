"""
gui/pages/connection_manager.py
Unified SAP BO Connection Manager
──────────────────────────────────────────────────────────────────────────────
Handles all 4 source types with type-aware UI:

  1. SAP BW       → OLAP (BICS/MDX) — no universe needed
  2. SAP HANA     → OLAP or Relational — OLAP: no universe / Relational: universe
  3. SAP S/4HANA  → BW Query / HANA View / CDS Views
  4. Non-SAP      → Relational only — always needs universe

Features per connection:
  • View & browse all connections grouped by source type
  • Test / validate (colour-coded live status dots)
  • Create new connection (type-aware form)
  • Edit properties
  • Delete with confirmation
  • Browse linked objects (universes / BEx queries / calc views / CDS views)
  • Health summary cards per source type
──────────────────────────────────────────────────────────────────────────────
"""

import threading
from tkinter import ttk, messagebox
import customtkinter as ctk
from datetime import datetime
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS

# ── Source type definitions ───────────────────────────────────────────────────
SOURCE_TYPES = [
    {
        'id':        'bw',
        'label':     'SAP BW',
        'icon':      '🔷',
        'color':     '#3B82F6',
        'subtitle':  'OLAP (BICS / MDX)',
        'badge':     'No universe needed',
        'badge_ok':  True,
        'kinds':     {'OlapConnection', 'BWConnection', 'OlapMDXConnection',
                      'BICSConnection', 'MDXConnection', 'BW', 'OLAP'},
        'name_hints':['BW', 'BEx', 'BICS', 'MDX'],
        'protocol_options': ['BICS (BW/4HANA recommended)', 'MDX (classic BW)', 'RFC (direct)'],
        'connects_to': 'InfoProviders · BEx Queries',
        'tools':     'WebI · Analysis for OLAP · Crystal Reports for Enterprise',
    },
    {
        'id':        'hana_olap',
        'label':     'SAP HANA (OLAP)',
        'icon':      '🟣',
        'color':     '#8B5CF6',
        'subtitle':  'OLAP — Calculation Views (Star Join)',
        'badge':     'No universe needed',
        'badge_ok':  True,
        'kinds':     {'HANAOlapConnection', 'HANAConnection', 'HanaOlapConnection'},
        'name_hints':['HANA', 'SAP HANA'],
        'protocol_options': ['OLAP (Calculation View / Star Join)'],
        'connects_to': 'HANA Calculation Views · Star Joins',
        'tools':     'WebI (via OLAP) · Analysis for OLAP',
    },
    {
        'id':        'hana_rel',
        'label':     'SAP HANA (Relational)',
        'icon':      '🟤',
        'color':     '#F59E0B',
        'subtitle':  'Relational → Universe (.unx)',
        'badge':     'Universe required',
        'badge_ok':  False,
        'kinds':     {'HANARelationalConnection', 'JDBCConnection', 'ODBCConnection'},
        'name_hints':['HANA_REL', 'HANA_JDBC'],
        'protocol_options': ['JDBC', 'ODBC', 'Native HANA Client'],
        'connects_to': 'HANA Tables · Views (via universe)',
        'tools':     'Web Intelligence (full join flexibility)',
    },
    {
        'id':        's4hana',
        'label':     'SAP S/4HANA',
        'icon':      '🟢',
        'color':     '#10B981',
        'subtitle':  'BW Query · HANA Calc View · CDS View',
        'badge':     'Mixed (depends on method)',
        'badge_ok':  None,
        'kinds':     {'S4HANAConnection', 'S4Connection', 'EmbeddedBWConnection'},
        'name_hints':['S4', 'S/4', 'S4HANA', 'CDS'],
        'protocol_options': ['BW Query (embedded BW → same as BW)',
                             'HANA Calculation View (→ OLAP connection)',
                             'CDS View (→ relational + universe)'],
        'connects_to': 'BW Queries · Calc Views · CDS Views',
        'tools':     'WebI · Analysis for OLAP (depending on method)',
    },
    {
        'id':        'nonsap',
        'label':     'Non-SAP (Oracle / SQL / etc.)',
        'icon':      '⚫',
        'color':     '#64748B',
        'subtitle':  'Relational connection only',
        'badge':     'Universe always required',
        'badge_ok':  False,
        'kinds':     {'OracleConnection', 'SQLServerConnection', 'MySQLConnection',
                      'PostgreSQLConnection', 'DB2Connection', 'TeradataConnection',
                      'GenericJDBC', 'GenericODBC', 'Connection'},
        'name_hints':['Oracle', 'SQL', 'MySQL', 'Postgres', 'Teradata', 'DB2'],
        'protocol_options': ['Oracle', 'SQL Server', 'MySQL', 'PostgreSQL',
                             'DB2', 'Teradata', 'JDBC (generic)', 'ODBC (generic)'],
        'connects_to': 'Relational tables (via universe)',
        'tools':     'Web Intelligence',
    },
]

# Map kind string → source type id
_KIND_MAP = {}
for _st in SOURCE_TYPES:
    for _k in _st['kinds']:
        _KIND_MAP[_k.lower()] = _st['id']

ALL_TYPE_IDS = ['all'] + [s['id'] for s in SOURCE_TYPES]


def _classify(conn):
    """Return source type id for a connection dict."""
    kind = conn.get('kind', '').lower()
    if kind in _KIND_MAP:
        return _KIND_MAP[kind]
    name = conn.get('name', '').upper()
    for st in SOURCE_TYPES:
        for hint in st['name_hints']:
            if hint.upper() in name:
                return st['id']
    return 'nonsap'   # default: relational


def _source_meta(type_id):
    return next((s for s in SOURCE_TYPES if s['id'] == type_id), SOURCE_TYPES[-1])


# ── background helper ─────────────────────────────────────────────────────────
_ROOT = [None]

def _bg(fn, cb):
    root = _ROOT[0]
    def _w():
        try:    r = fn()
        except Exception: r = None
        if root:
            try: root.after(0, lambda res=r: cb(res))
            except Exception: pass
    threading.Thread(target=_w, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
#  Create / Edit dialog  — type-aware
# ─────────────────────────────────────────────────────────────────────────────

class _ConnDialog(ctk.CTkToplevel):

    # Fields per source type
    _FIELDS = {
        'bw': [
            ('name',         'Connection Name *',             True),
            ('bw_host',      'BW Application Server (host)',  False),
            ('bw_client',    'BW Client (e.g. 800)',          False),
            ('bw_system_id', 'System ID (SID)',               False),
            ('bw_logon_grp', 'Logon Group (blank = SPACE)',   False),
            ('bex_query',    'Default BEx Query Tech. Name',  False),
            ('description',  'Description',                   False),
        ],
        'hana_olap': [
            ('name',         'Connection Name *',             True),
            ('hana_host',    'HANA Host:Port (e.g. hana01:30215)', False),
            ('hana_schema',  'Default Schema / Package',      False),
            ('calc_view',    'Default Calculation View',      False),
            ('description',  'Description',                   False),
        ],
        'hana_rel': [
            ('name',         'Connection Name *',             True),
            ('hana_host',    'HANA Host:Port',                False),
            ('hana_schema',  'Default Schema',                False),
            ('driver',       'Driver (JDBC / ODBC / Native)', False),
            ('description',  'Description',                   False),
        ],
        's4hana': [
            ('name',         'Connection Name *',             True),
            ('host',         'S/4HANA Host / BW Query URL',   False),
            ('client',       'Client',                        False),
            ('method',       'Method (BW Query / HANA View / CDS)', False),
            ('description',  'Description',                   False),
        ],
        'nonsap': [
            ('name',         'Connection Name *',             True),
            ('host',         'Database Host',                 False),
            ('database',     'Database / SID / Schema',       False),
            ('driver',       'Driver',                        False),
            ('description',  'Description',                   False),
        ],
    }

    def __init__(self, parent, type_id='bw', conn_data=None):
        super().__init__(parent)
        self._type_id  = type_id
        self._conn_data = conn_data
        self.result    = None
        is_edit        = conn_data is not None
        meta           = _source_meta(type_id)

        self.title(f'{"Edit" if is_edit else "New"} {meta["label"]} Connection')
        self.geometry('540x560')
        self.configure(fg_color=C['bg_primary'])
        self.resizable(False, False)
        self.grab_set()

        self._vars     = {}
        self._proto_var = ctk.StringVar(value=meta['protocol_options'][0])
        self._build_ui(meta, is_edit)
        if is_edit and conn_data:
            self._prefill(conn_data)

    def _build_ui(self, meta, is_edit):
        # Title strip
        title_bar = ctk.CTkFrame(self, fg_color=meta['color'],
                                 corner_radius=0, height=52)
        title_bar.pack(fill='x')
        title_bar.pack_propagate(False)
        ctk.CTkLabel(title_bar,
                     text=f'{meta["icon"]}  {meta["label"]} Connection',
                     font=('Segoe UI', 15, 'bold'),
                     text_color='white').pack(side='left', padx=16)

        # Badge
        badge_color = '#10B981' if meta['badge_ok'] else '#EF4444' if meta['badge_ok'] is False else '#F59E0B'
        ctk.CTkLabel(title_bar, text=meta['badge'],
                     font=('Segoe UI', 9, 'bold'),
                     fg_color=badge_color,
                     corner_radius=4,
                     text_color='white').pack(side='right', padx=12)

        # Info line
        ctk.CTkLabel(self,
                     text=f'Connects to: {meta["connects_to"]}   |   Tools: {meta["tools"]}',
                     font=('Segoe UI', 9),
                     text_color=C['text_secondary'],
                     wraplength=510).pack(anchor='w', padx=16, pady=(10, 4))

        # Protocol selector
        ctk.CTkLabel(self, text='Protocol / Method', font=('Segoe UI', 10),
                     text_color=C['text_secondary']).pack(anchor='w', padx=16, pady=(4, 1))
        ctk.CTkOptionMenu(self, values=meta['protocol_options'],
                          variable=self._proto_var,
                          fg_color=C['bg_secondary'],
                          button_color=meta['color'],
                          text_color=C['text_primary'],
                          height=30).pack(fill='x', padx=16, pady=(0, 8))

        # Form fields
        form = ctk.CTkScrollableFrame(self, fg_color='transparent', corner_radius=0)
        form.pack(fill='both', expand=True, padx=16, pady=(0, 4))

        fields = self._FIELDS.get(self._type_id, self._FIELDS['nonsap'])
        for key, label, required in fields:
            ctk.CTkLabel(form, text=label, font=('Segoe UI', 10),
                         text_color=C['text_secondary']).pack(anchor='w', pady=(5, 1))
            var = ctk.StringVar()
            self._vars[key] = var
            ctk.CTkEntry(form, textvariable=var, height=30,
                         fg_color=C['bg_secondary'],
                         border_color=meta['color'] if required else C['bg_tertiary'],
                         text_color=C['text_primary'],
                         font=('Segoe UI', 11)).pack(fill='x', pady=(0, 2))

        # Buttons
        btns = ctk.CTkFrame(self, fg_color='transparent', height=50)
        btns.pack(fill='x', padx=16, pady=(4, 12))
        btns.pack_propagate(False)
        ctk.CTkButton(btns, text='Cancel', width=90, height=34,
                      fg_color=C['bg_tertiary'], text_color=C['text_primary'],
                      command=self.destroy).pack(side='right')
        ctk.CTkButton(btns,
                      text='💾 Save' if is_edit else '➕ Create',
                      width=120, height=34,
                      fg_color=meta['color'],
                      command=self._submit).pack(side='right', padx=(0, 6))

    def _prefill(self, data):
        for key in self._vars:
            if key in data:
                self._vars[key].set(str(data.get(key, '')))

    def _submit(self):
        name = self._vars.get('name', ctk.StringVar()).get().strip()
        if not name:
            messagebox.showwarning('Required', 'Connection Name is required.', parent=self)
            return
        self.result = {k: v.get().strip() for k, v in self._vars.items()}
        self.result['protocol'] = self._proto_var.get()
        self.result['source_type'] = self._type_id
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
#  Linked Objects browser
# ─────────────────────────────────────────────────────────────────────────────

class _LinkedObjectsWindow(ctk.CTkToplevel):
    """Browse universes / BEx queries / calc views / CDS views linked to a connection."""

    _COLS = [
        ('name', 'Name / Technical Name', 300, True),
        ('type', 'Type',                  140, False),
        ('owner','Owner',                 110, False),
        ('desc', 'Description',           280, True),
    ]

    def __init__(self, parent, conn):
        super().__init__(parent)
        meta = _source_meta(_classify(conn))
        self.title(f'🔍  Linked Objects — {conn["name"]}')
        self.geometry('860x520')
        self.configure(fg_color=C['bg_primary'])
        self._conn = conn
        self._all  = []
        self._build_ui(meta)
        threading.Thread(target=self._load, daemon=True).start()

    def _build_ui(self, meta):
        hdr = ctk.CTkFrame(self, fg_color=meta['color'],
                           corner_radius=0, height=48)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=f'{meta["icon"]}  {self._conn["name"]}  →  Linked Objects',
                     font=('Segoe UI', 13, 'bold'),
                     text_color='white').pack(side='left', padx=14)
        self._status_lbl = ctk.CTkLabel(hdr, text='⏳ Loading…',
                                        font=('Segoe UI', 10),
                                        text_color='white')
        self._status_lbl.pack(side='right', padx=14)

        ctk.CTkButton(hdr, text='🔄', width=36, height=28,
                      fg_color='rgba(255,255,255,0.15)',
                      command=lambda: threading.Thread(
                          target=self._load, daemon=True).start()
                      ).pack(side='right')

        # Info strip
        strip = ctk.CTkFrame(self, fg_color=C['bg_secondary'],
                             corner_radius=0, height=36)
        strip.pack(fill='x')
        strip.pack_propagate(False)
        ctk.CTkLabel(strip,
                     text=f'Connects to: {meta["connects_to"]}   •   {meta["badge"]}',
                     font=('Segoe UI', 9),
                     text_color=C['text_secondary']).pack(side='left', padx=14)

        # Tree
        tv_frame = ctk.CTkFrame(self, fg_color=C['bg_secondary'], corner_radius=8)
        tv_frame.pack(fill='both', expand=True, padx=12, pady=10)

        sn = f'LO{id(self)}'
        s = ttk.Style()
        s.configure(sn, background=C['bg_secondary'], foreground=C['text_primary'],
                    fieldbackground=C['bg_secondary'], rowheight=30,
                    font=('Segoe UI', 10), borderwidth=0)
        s.configure(f'{sn}.Heading', background=C['bg_tertiary'],
                    foreground=C['text_secondary'],
                    font=('Segoe UI', 10, 'bold'), relief='flat')
        s.map(sn, background=[('selected', C['primary'])],
              foreground=[('selected', 'white')])
        s.layout(sn, [('Treeview.treearea', {'sticky': 'nswe'})])

        self._tv = ttk.Treeview(tv_frame, style=sn, show='headings',
                                columns=[c[0] for c in self._COLS])
        for cid, hd, w, st in self._COLS:
            self._tv.heading(cid, text=hd)
            self._tv.column(cid, width=w, minwidth=40, stretch=st)

        vsb = ctk.CTkScrollbar(tv_frame, orientation='vertical', command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        self._tv.pack(fill='both', expand=True, padx=8, pady=8)

    def _load(self):
        items = bo_session.get_connection_linked_objects(self._conn['id'])
        self._all = items or []
        if hasattr(self, '_tv'):
            self.after(0, self._render)

    def _render(self):
        for row in self._tv.get_children():
            self._tv.delete(row)
        for item in self._all:
            self._tv.insert('', 'end',
                            values=(item.get('name', ''), item.get('type', ''),
                                    item.get('owner', ''), item.get('desc', '')))
        n = len(self._all)
        self._status_lbl.configure(
            text=f'{n} linked object{"s" if n != 1 else ""}')


# ─────────────────────────────────────────────────────────────────────────────
#  Main page
# ─────────────────────────────────────────────────────────────────────────────

class ConnectionManagerPage(ctk.CTkFrame):

    _COLS = [
        ('dot',     '●',               30,  False),
        ('source',  'Source',          90,  False),
        ('name',    'Connection Name', 220, True),
        ('protocol','Protocol / Kind', 130, False),
        ('host',    'Host / Server',   150, False),
        ('owner',   'Owner',           100, False),
        ('universe','Universe?',        78, False),
        ('updated', 'Last Updated',    135, False),
    ]

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0, **kw)
        _ROOT[0] = self.winfo_toplevel()
        self._all_conns     = []   # raw list of all connections
        self._test_results  = {}   # id → True/False/None
        self._active_filter = 'all'
        self._destroyed     = False
        self._build_ui()
        threading.Thread(target=self._load, daemon=True).start()

    def destroy(self):
        self._destroyed = True
        super().destroy()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color='transparent', height=56)
        hdr.pack(fill='x', padx=16, pady=(14, 0))
        hdr.pack_propagate(False)

        ctk.CTkLabel(hdr, text='🔌  Connection Manager',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')

        ctk.CTkButton(hdr, text='🔄 Refresh', width=88, height=34,
                      fg_color=C['bg_tertiary'], text_color=C['text_primary'],
                      command=lambda: threading.Thread(
                          target=self._load, daemon=True).start()
                      ).pack(side='right')

        ctk.CTkButton(hdr, text='⚡ Test All', width=88, height=34,
                      fg_color='#7C3AED', hover_color='#6D28D9',
                      command=self._test_all).pack(side='right', padx=(0, 6))

        # Source-type filter tabs
        tabs = ctk.CTkFrame(self, fg_color=C['bg_secondary'],
                            corner_radius=8, height=46)
        tabs.pack(fill='x', padx=16, pady=(8, 4))
        tabs.pack_propagate(False)

        self._tab_btns = {}
        tab_defs = [('all', '🔌', 'All', '#3B82F6')] + [
            (s['id'], s['icon'], s['label'], s['color']) for s in SOURCE_TYPES
        ]
        for tid, icon, label, color in tab_defs:
            btn = ctk.CTkButton(tabs, text=f'{icon} {label}',
                                height=30, corner_radius=6,
                                fg_color=color if tid == 'all' else C['bg_tertiary'],
                                hover_color=color,
                                text_color='white',
                                font=('Segoe UI', 10),
                                command=lambda t=tid, c=color: self._set_filter(t, c))
            btn.pack(side='left', padx=4, pady=8)
            self._tab_btns[tid] = (btn, color)

        # Summary cards
        self._cards_frame = ctk.CTkFrame(self, fg_color='transparent', height=80)
        self._cards_frame.pack(fill='x', padx=16, pady=(2, 6))
        self._cards_frame.pack_propagate(False)
        self._card_lbls = {}
        card_defs = [
            ('total',   'Total',         '#3B82F6'),
            ('bw',      'SAP BW',        '#3B82F6'),
            ('hana',    'HANA',          '#8B5CF6'),
            ('s4hana',  'S/4HANA',       '#10B981'),
            ('nonsap',  'Non-SAP',       '#64748B'),
            ('ok',      'Tested OK',     '#10B981'),
            ('failed',  'Failed',        '#EF4444'),
        ]
        for key, label, color in card_defs:
            card = ctk.CTkFrame(self._cards_frame,
                                fg_color=C['bg_secondary'],
                                corner_radius=8)
            card.pack(side='left', padx=(0, 6), fill='both', expand=True)
            ctk.CTkLabel(card, text=label, font=('Segoe UI', 9),
                         text_color=C['text_secondary']).pack(pady=(6, 0))
            lbl = ctk.CTkLabel(card, text='—',
                               font=('Segoe UI', 18, 'bold'),
                               text_color=color)
            lbl.pack(pady=(0, 6))
            self._card_lbls[key] = lbl

        # Search + action bar
        abar = ctk.CTkFrame(self, fg_color='transparent', height=36)
        abar.pack(fill='x', padx=16, pady=(0, 4))
        abar.pack_propagate(False)

        self._q_var = ctk.StringVar()
        self._q_var.trace_add('write', lambda *_: self._render())
        ctk.CTkEntry(abar, textvariable=self._q_var,
                     placeholder_text='🔎  Filter connections…',
                     width=240, height=30,
                     fg_color=C['bg_secondary'],
                     border_color=C['bg_tertiary'],
                     text_color=C['text_primary'],
                     font=('Segoe UI', 11)).pack(side='left', padx=(0, 8))

        # New Connection dropdown per type
        self._new_type_var = ctk.StringVar(value='SAP BW')
        ctk.CTkLabel(abar, text='New:', font=('Segoe UI', 10),
                     text_color=C['text_secondary']).pack(side='left')
        ctk.CTkOptionMenu(abar,
                          values=['SAP BW', 'HANA OLAP', 'HANA Relational',
                                  'S/4HANA', 'Non-SAP (Oracle/SQL/etc.)'],
                          variable=self._new_type_var,
                          width=190, height=30,
                          fg_color=C['bg_secondary'],
                          button_color='#10B981',
                          text_color=C['text_primary'],
                          font=('Segoe UI', 10)).pack(side='left', padx=4)
        ctk.CTkButton(abar, text='➕', width=36, height=30,
                      fg_color='#10B981', hover_color='#059669',
                      command=self._create_conn).pack(side='left', padx=(0, 10))

        for label, color, cmd in [
            ('🔌 Test',   '#7C3AED', self._test_selected),
            ('🔍 Browse', '#0EA5E9', self._browse_selected),
            ('✏️ Edit',   '#F59E0B', self._edit_selected),
            ('🗑 Delete', C['danger'], self._delete_selected),
        ]:
            ctk.CTkButton(abar, text=label, width=88, height=30,
                          fg_color=color, hover_color=color,
                          font=('Segoe UI', 10),
                          command=cmd).pack(side='left', padx=2)

        self._status_lbl = ctk.CTkLabel(abar, text='',
                                        font=('Segoe UI', 10),
                                        text_color=C['text_secondary'])
        self._status_lbl.pack(side='right')

        # Treeview
        tv_outer = ctk.CTkFrame(self, fg_color=C['bg_secondary'], corner_radius=8)
        tv_outer.pack(fill='both', expand=True, padx=16, pady=(0, 14))

        sn = f'CM{id(self)}.TV'
        s = ttk.Style()
        s.configure(sn, background=C['bg_secondary'], foreground=C['text_primary'],
                    fieldbackground=C['bg_secondary'], rowheight=34,
                    font=('Segoe UI', 11), borderwidth=0)
        s.configure(f'{sn}.Heading', background=C['bg_tertiary'],
                    foreground=C['text_secondary'],
                    font=('Segoe UI', 10, 'bold'), relief='flat')
        s.map(sn, background=[('selected', C['primary'])],
              foreground=[('selected', 'white')])
        s.layout(sn, [('Treeview.treearea', {'sticky': 'nswe'})])

        self._tv = ttk.Treeview(tv_outer, style=sn, show='headings',
                                selectmode='browse',
                                columns=[c[0] for c in self._COLS])
        for cid, hd, w, st in self._COLS:
            self._tv.heading(cid, text=hd)
            self._tv.column(cid, width=w, minwidth=24, stretch=st)

        self._tv.tag_configure('ok',      foreground='#10B981')
        self._tv.tag_configure('failed',  foreground='#EF4444')
        self._tv.tag_configure('unknown', foreground='#9AA0B4')

        vsb = ctk.CTkScrollbar(tv_outer, orientation='vertical', command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y', padx=(0, 4), pady=8)
        self._tv.pack(fill='both', expand=True, padx=8, pady=8)
        self._tv.bind('<Double-1>', lambda e: self._browse_selected())

    # ── Filter tabs ───────────────────────────────────────────────────────────

    def _set_filter(self, type_id, color):
        self._active_filter = type_id
        for tid, (btn, col) in self._tab_btns.items():
            btn.configure(fg_color=col if tid == type_id else C['bg_tertiary'])
        self._render()

    # ── Load data ─────────────────────────────────────────────────────────────

    def _load(self):
        self.after(0, lambda: self._status_lbl.configure(
            text='⏳ Loading connections…'))
        conns = bo_session.get_all_connections_typed()
        if not self._destroyed:
            self.after(0, lambda c=conns: self._on_loaded(c))

    def _on_loaded(self, conns):
        self._all_conns    = conns or []
        self._test_results = {c['id']: None for c in self._all_conns}
        self._render()
        self._update_cards()

    def _render(self):
        q   = self._q_var.get().lower()
        flt = self._active_filter

        shown = []
        for conn in self._all_conns:
            if q and q not in conn.get('name', '').lower() \
                  and q not in conn.get('kind', '').lower() \
                  and q not in conn.get('host', '').lower():
                continue
            ct = _classify(conn)
            if flt != 'all':
                # hana_olap + hana_rel both show under 'hana' tab
                if flt == 'hana' and ct not in ('hana_olap', 'hana_rel'):
                    continue
                elif flt not in ('hana',) and ct != flt:
                    continue
            shown.append((conn, ct))

        for row in self._tv.get_children():
            self._tv.delete(row)

        for conn, ct in shown:
            meta     = _source_meta(ct)
            cid      = str(conn['id'])
            tested   = self._test_results.get(conn['id'])
            tag      = 'ok' if tested is True else 'failed' if tested is False else 'unknown'
            dot      = '●'
            univ_req = '✅ No' if meta['badge_ok'] is True \
                else '❌ Yes' if meta['badge_ok'] is False else '⚠ Mixed'

            self._tv.insert('', 'end', iid=cid, tags=(tag,),
                            values=(dot,
                                    f'{meta["icon"]} {meta["label"]}',
                                    conn.get('name', ''),
                                    conn.get('kind', ''),
                                    conn.get('host', conn.get('server', ''))[:35],
                                    conn.get('owner', ''),
                                    univ_req,
                                    conn.get('updated', '')))

        self._status_lbl.configure(
            text=f'{len(self._all_conns)} total  |  showing {len(shown)}')

    def _update_cards(self):
        types = [_classify(c) for c in self._all_conns]
        ok      = sum(1 for v in self._test_results.values() if v is True)
        failed  = sum(1 for v in self._test_results.values() if v is False)
        hana_n  = sum(1 for t in types if t in ('hana_olap', 'hana_rel'))
        self._card_lbls['total'].configure(text=str(len(self._all_conns)))
        self._card_lbls['bw'].configure(text=str(types.count('bw')))
        self._card_lbls['hana'].configure(text=str(hana_n))
        self._card_lbls['s4hana'].configure(text=str(types.count('s4hana')))
        self._card_lbls['nonsap'].configure(text=str(types.count('nonsap')))
        self._card_lbls['ok'].configure(text=str(ok))
        self._card_lbls['failed'].configure(text=str(failed))

    # ── Selection helper ──────────────────────────────────────────────────────

    def _get_selected(self):
        sel = self._tv.selection()
        if not sel:
            messagebox.showinfo('Select', 'Select a connection first.', parent=self)
            return None
        iid = sel[0]
        return next((c for c in self._all_conns if str(c['id']) == iid), None)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _test_selected(self):
        conn = self._get_selected()
        if not conn: return
        self._status_lbl.configure(text=f'⏳ Testing {conn["name"]}…')
        def _do():
            ok, msg = bo_session.test_connection_typed(conn['id'])
            self._test_results[conn['id']] = ok
            self.after(0, lambda: (self._render(), self._update_cards(),
                                   self._status_lbl.configure(
                                       text=f'{"✅" if ok else "❌"} {conn["name"]}: {msg}'),
                                   messagebox.showinfo('Test Result',
                                       f'{"✅" if ok else "❌"}  {conn["name"]}\n\n{msg}',
                                       parent=self)))
        threading.Thread(target=_do, daemon=True).start()

    def _test_all(self):
        if not self._all_conns:
            return
        self._status_lbl.configure(text='⏳ Testing all connections…')
        def _do():
            for conn in self._all_conns:
                ok, _ = bo_session.test_connection_typed(conn['id'])
                self._test_results[conn['id']] = ok
            self.after(0, lambda: (self._render(), self._update_cards(),
                                   self._status_lbl.configure(
                                       text=f'Tests done — '
                                            f'{sum(1 for v in self._test_results.values() if v)} OK  |  '
                                            f'{sum(1 for v in self._test_results.values() if v is False)} failed')))
        threading.Thread(target=_do, daemon=True).start()

    def _browse_selected(self):
        conn = self._get_selected()
        if not conn: return
        _LinkedObjectsWindow(self, conn)

    def _create_conn(self):
        label_map = {
            'SAP BW':                    'bw',
            'HANA OLAP':                 'hana_olap',
            'HANA Relational':           'hana_rel',
            'S/4HANA':                   's4hana',
            'Non-SAP (Oracle/SQL/etc.)': 'nonsap',
        }
        type_id = label_map.get(self._new_type_var.get(), 'bw')
        dlg = _ConnDialog(self, type_id=type_id)
        self.wait_window(dlg)
        if not dlg.result: return
        self._status_lbl.configure(text='⏳ Creating…')
        def _do():
            ok, msg = bo_session.create_connection_typed(dlg.result)
            self.after(0, lambda: self._on_create(ok, msg, dlg.result.get('name', '')))
        threading.Thread(target=_do, daemon=True).start()

    def _on_create(self, ok, msg, name):
        if ok:
            messagebox.showinfo('Created', f'✅ Created:\n{name}\n\n{msg}', parent=self)
            threading.Thread(target=self._load, daemon=True).start()
        else:
            messagebox.showerror('Error', f'❌ Create failed:\n{msg}', parent=self)
        self._status_lbl.configure(text='')

    def _edit_selected(self):
        conn = self._get_selected()
        if not conn: return
        ct  = _classify(conn)
        dlg = _ConnDialog(self, type_id=ct, conn_data=conn)
        self.wait_window(dlg)
        if not dlg.result: return
        self._status_lbl.configure(text='⏳ Saving…')
        def _do():
            ok, msg = bo_session.update_connection_typed(conn['id'], dlg.result)
            self.after(0, lambda: self._on_edit(ok, msg, dlg.result.get('name', '')))
        threading.Thread(target=_do, daemon=True).start()

    def _on_edit(self, ok, msg, name):
        if ok:
            messagebox.showinfo('Saved', f'✅ Updated:\n{name}', parent=self)
            threading.Thread(target=self._load, daemon=True).start()
        else:
            messagebox.showerror('Error', f'❌ Update failed:\n{msg}', parent=self)
        self._status_lbl.configure(text='')

    def _delete_selected(self):
        conn = self._get_selected()
        if not conn: return
        meta = _source_meta(_classify(conn))
        if not messagebox.askyesno(
                'Confirm Delete',
                f'Delete connection:\n  {meta["icon"]} {conn["name"]}\n\n'
                f'⚠  All reports and universes using this connection will break.',
                parent=self):
            return
        def _do():
            ok, msg = bo_session.delete_connection_typed(conn['id'])
            self.after(0, lambda: self._on_delete(ok, msg, conn['name']))
        threading.Thread(target=_do, daemon=True).start()

    def _on_delete(self, ok, msg, name):
        if ok:
            messagebox.showinfo('Deleted', f'✅ Deleted:\n{name}', parent=self)
            threading.Thread(target=self._load, daemon=True).start()
        else:
            messagebox.showerror('Error', f'❌ Delete failed:\n{msg}', parent=self)
