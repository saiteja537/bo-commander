"""
gui/pages/bw_connections.py
SAP BW → BO Connections Manager
──────────────────────────────────────────────────────────────────────────────
Features:
  • View/browse all BW OLAP connections (BICS / MDX / BW / OlapConnection)
  • Test / validate each connection via BO REST API
  • Create new BW connections (name, BW system, client, logon group, BEx query)
  • Edit connection properties (name, description, owner)
  • Delete / disable connections
  • Browse InfoProviders & BEx queries linked to a selected connection
  • Connection health summary panel
──────────────────────────────────────────────────────────────────────────────
"""

import threading
from tkinter import ttk, messagebox, simpledialog
import customtkinter as ctk
from datetime import datetime
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS
F = Config.FONTS

# BW connection types recognised in BO CMS
BW_KINDS = {'OlapConnection', 'BW', 'OLAP', 'MDXConnection',
            'BWConnection', 'OlapMDXConnection', 'BICSConnection'}

# ── background thread helper ──────────────────────────────────────────────────
_ROOT_REF = [None]

def _bg(fn, cb):
    root = _ROOT_REF[0]
    def _w():
        try:    result = fn()
        except Exception as e: result = None
        if root:
            try: root.after(0, lambda r=result: cb(r))
            except Exception: pass
    threading.Thread(target=_w, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
#  Create / Edit dialog
# ─────────────────────────────────────────────────────────────────────────────

class _BWConnDialog(ctk.CTkToplevel):
    """
    Modal dialog for creating or editing a BW OLAP connection.
    For a NEW connection:  conn_data = None
    For EDIT:             conn_data = dict with existing values
    """

    FIELDS = [
        ('name',         'Connection Name *',   True),
        ('bw_host',      'BW Application Server (host)',  False),
        ('bw_client',    'BW Client (e.g. 800)',           False),
        ('bw_system_id', 'BW System ID (SID)',              False),
        ('bw_logon_grp', 'Logon Group (SPACE = default)',   False),
        ('bex_query',    'Default BEx Query Technical Name',False),
        ('description',  'Description',                      False),
    ]

    def __init__(self, parent, conn_data=None):
        super().__init__(parent)
        self._conn_data = conn_data
        self.result     = None
        is_edit         = conn_data is not None
        self.title('Edit BW Connection' if is_edit else 'Create New BW Connection')
        self.geometry('520x520')
        self.configure(fg_color=C['bg_primary'])
        self.resizable(False, False)
        self.grab_set()

        self._vars = {}
        self._build_ui(is_edit)
        if is_edit:
            self._prefill(conn_data)

    def _build_ui(self, is_edit):
        ctk.CTkLabel(self, text='🔗  BW OLAP Connection',
                     font=('Segoe UI', 16, 'bold'),
                     text_color=C['text_primary']).pack(anchor='w', padx=20, pady=(18, 4))
        ctk.CTkLabel(self,
                     text='Connection type: OLAP (BICS/MDX) — connects directly to BW InfoProviders & BEx Queries',
                     font=('Segoe UI', 9), text_color=C['text_secondary'],
                     wraplength=480).pack(anchor='w', padx=20, pady=(0, 12))

        form = ctk.CTkScrollableFrame(self, fg_color='transparent', corner_radius=0)
        form.pack(fill='both', expand=True, padx=20, pady=(0, 4))

        for key, label, required in self.FIELDS:
            ctk.CTkLabel(form, text=label, font=('Segoe UI', 10),
                         text_color=C['text_secondary']).pack(anchor='w', pady=(6, 1))
            var = ctk.StringVar()
            self._vars[key] = var
            entry = ctk.CTkEntry(form, textvariable=var, height=30,
                                 fg_color=C['bg_secondary'],
                                 border_color=C['primary'] if required else C['bg_tertiary'],
                                 text_color=C['text_primary'],
                                 font=('Segoe UI', 11))
            entry.pack(fill='x', pady=(0, 2))

        # Connection type selector (new only)
        if not is_edit:
            ctk.CTkLabel(form, text='OLAP Protocol', font=('Segoe UI', 10),
                         text_color=C['text_secondary']).pack(anchor='w', pady=(6, 1))
            self._protocol_var = ctk.StringVar(value='BICS (recommended for BW/4HANA)')
            ctk.CTkOptionMenu(form,
                              values=['BICS (recommended for BW/4HANA)',
                                      'MDX (classic BW)',
                                      'RFC (direct BW connection)'],
                              variable=self._protocol_var,
                              fg_color=C['bg_secondary'],
                              button_color=C['primary'],
                              text_color=C['text_primary'],
                              height=30).pack(fill='x', pady=(0, 2))
        else:
            self._protocol_var = ctk.StringVar(value='BICS (recommended for BW/4HANA)')

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color='transparent', height=48)
        btn_row.pack(fill='x', padx=20, pady=(4, 12))
        btn_row.pack_propagate(False)

        ctk.CTkButton(btn_row, text='Cancel', width=100, height=34,
                      fg_color=C['bg_tertiary'], text_color=C['text_primary'],
                      command=self.destroy).pack(side='right')
        ctk.CTkButton(btn_row,
                      text='💾  Save' if is_edit else '➕  Create',
                      width=120, height=34,
                      fg_color=C['primary'], hover_color=C['accent'],
                      command=self._submit).pack(side='right', padx=(0, 8))

    def _prefill(self, data):
        for key, *_ in self.FIELDS:
            if key in data and key in self._vars:
                self._vars[key].set(str(data.get(key, '')))

    def _submit(self):
        name = self._vars['name'].get().strip()
        if not name:
            messagebox.showwarning('Required', 'Connection Name is required.', parent=self)
            return
        self.result = {k: v.get().strip() for k, v in self._vars.items()}
        self.result['protocol'] = self._protocol_var.get()
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
#  InfoProvider / BEx Browser popup
# ─────────────────────────────────────────────────────────────────────────────

class _BExBrowserWindow(ctk.CTkToplevel):
    """Shows InfoProviders and BEx Queries linked to a connection."""

    _COLS = [
        ('name',  'Technical Name / Query',  280, True),
        ('type',  'Type',                    120, False),
        ('desc',  'Description',             300, True),
    ]

    def __init__(self, parent, conn_name, conn_id):
        super().__init__(parent)
        self.title(f'🔍  BEx Browser — {conn_name}')
        self.geometry('820x560')
        self.configure(fg_color=C['bg_primary'])
        self._conn_id   = conn_id
        self._conn_name = conn_name
        self._build_ui()
        threading.Thread(target=self._load, daemon=True).start()

    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color=C['bg_secondary'], height=50, corner_radius=0)
        top.pack(fill='x')
        top.pack_propagate(False)

        ctk.CTkLabel(top, text=f'🔍  BEx & InfoProvider Browser',
                     font=('Segoe UI', 14, 'bold'),
                     text_color=C['text_primary']).pack(side='left', padx=16)

        self._status_lbl = ctk.CTkLabel(top, text='⏳ Loading…',
                                        font=('Segoe UI', 11),
                                        text_color=C['text_secondary'])
        self._status_lbl.pack(side='right', padx=16)

        ctk.CTkButton(top, text='🔄 Refresh', width=90, height=30,
                      fg_color=C['bg_tertiary'],
                      command=lambda: threading.Thread(target=self._load, daemon=True).start()
                      ).pack(side='right', padx=8)

        # Type filter tabs
        tab_row = ctk.CTkFrame(self, fg_color='transparent', height=38)
        tab_row.pack(fill='x', padx=12, pady=(8, 0))
        tab_row.pack_propagate(False)

        self._type_filter = ctk.StringVar(value='All')
        for label in ['All', 'InfoProvider', 'BEx Query', 'InfoCube', 'MultiProvider', 'DSO']:
            ctk.CTkButton(tab_row, text=label, width=100, height=28,
                          fg_color=C['bg_tertiary'], hover_color=C['primary'],
                          font=('Segoe UI', 10),
                          command=lambda l=label: self._set_filter(l)
                          ).pack(side='left', padx=3)

        # Tree
        tree_frame = ctk.CTkFrame(self, fg_color=C['bg_secondary'], corner_radius=8)
        tree_frame.pack(fill='both', expand=True, padx=12, pady=8)

        sn = f'BEX{id(self)}'
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

        self._tv = ttk.Treeview(tree_frame, style=sn, show='headings',
                                columns=[c[0] for c in self._COLS])
        for cid, hd, w, st in self._COLS:
            self._tv.heading(cid, text=hd)
            self._tv.column(cid, width=w, minwidth=40, stretch=st)

        vsb = ctk.CTkScrollbar(tree_frame, orientation='vertical', command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        self._tv.pack(fill='both', expand=True, padx=8, pady=8)

        self._all_items = []

    def _set_filter(self, label):
        self._type_filter.set(label)
        self._render(self._all_items)

    def _load(self):
        items = bo_session.get_bw_infoproviders(self._conn_id)
        self._all_items = items or []
        if hasattr(self, '_tv'):
            self.after(0, lambda: self._render(self._all_items))

    def _render(self, items):
        f = self._type_filter.get()
        shown = [i for i in items if f == 'All' or f.lower() in i.get('type', '').lower()]
        for row in self._tv.get_children():
            self._tv.delete(row)
        for item in shown:
            self._tv.insert('', 'end',
                            values=(item.get('name', ''),
                                    item.get('type', ''),
                                    item.get('desc', '')))
        self._status_lbl.configure(
            text=f'{len(self._all_items)} total  |  showing {len(shown)}')


# ─────────────────────────────────────────────────────────────────────────────
#  Main BW Connections Page
# ─────────────────────────────────────────────────────────────────────────────

class BWConnectionsPage(ctk.CTkFrame):

    # Treeview columns: (id, header, width, stretch)
    _COLS = [
        ('status', '●',              32,  False),
        ('name',   'Connection Name', 240, True),
        ('kind',   'Protocol / Type', 130, False),
        ('owner',  'Owner',           110, False),
        ('desc',   'Description',     260, True),
        ('updated','Last Updated',    140, False),
    ]

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0, **kw)
        _ROOT_REF[0] = self.winfo_toplevel()
        self._conns     = []
        self._destroyed = False
        self._test_results = {}   # conn_id → True/False/None

        self._build_ui()
        threading.Thread(target=self._load, daemon=True).start()

    def destroy(self):
        self._destroyed = True
        super().destroy()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color='transparent', height=58)
        hdr.pack(fill='x', padx=16, pady=(14, 0))
        hdr.pack_propagate(False)

        ctk.CTkLabel(hdr, text='🔗  SAP BW → BO Connections',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')

        ctk.CTkButton(hdr, text='➕  New Connection', width=140, height=34,
                      fg_color='#10B981', hover_color='#059669',
                      font=('Segoe UI', 11, 'bold'),
                      command=self._create_conn).pack(side='right')

        ctk.CTkButton(hdr, text='🔄  Refresh', width=90, height=34,
                      fg_color=C['bg_tertiary'], text_color=C['text_primary'],
                      command=lambda: threading.Thread(
                          target=self._load, daemon=True).start()
                      ).pack(side='right', padx=(0, 6))

        ctk.CTkButton(hdr, text='⚡  Test All', width=90, height=34,
                      fg_color='#7C3AED', hover_color='#6D28D9',
                      command=self._test_all).pack(side='right', padx=(0, 6))

        # ── Info banner ───────────────────────────────────────────────────────
        banner = ctk.CTkFrame(self, fg_color=C['bg_secondary'],
                              corner_radius=8, height=46)
        banner.pack(fill='x', padx=16, pady=(8, 6))
        banner.pack_propagate(False)

        ctk.CTkLabel(banner,
                     text='⬛  OLAP/BICS connections — connect directly to BW InfoProviders & BEx Queries. '
                          'No universe required.  ✅ Multidimensional  ✅ Real-time',
                     font=('Segoe UI', 10),
                     text_color=C['text_secondary']).pack(side='left', padx=14)

        self._status_lbl = ctk.CTkLabel(banner, text='',
                                        font=('Segoe UI', 10),
                                        text_color=C['text_secondary'])
        self._status_lbl.pack(side='right', padx=14)

        # ── Search + action bar ───────────────────────────────────────────────
        action_bar = ctk.CTkFrame(self, fg_color='transparent', height=38)
        action_bar.pack(fill='x', padx=16, pady=(0, 4))
        action_bar.pack_propagate(False)

        ctk.CTkLabel(action_bar, text='🔎', font=('Segoe UI', 13)).pack(side='left')
        self._q_var = ctk.StringVar()
        self._q_var.trace_add('write', lambda *_: self._filter())
        ctk.CTkEntry(action_bar, textvariable=self._q_var,
                     placeholder_text='Filter connections…',
                     width=260, height=30,
                     fg_color=C['bg_secondary'],
                     border_color=C['bg_tertiary'],
                     text_color=C['text_primary'],
                     font=('Segoe UI', 11)).pack(side='left', padx=6)

        # Per-row action buttons (operate on selected row)
        for label, color, cmd in [
            ('🔌 Test',    '#7C3AED', self._test_selected),
            ('🔍 Browse',  '#0EA5E9', self._browse_selected),
            ('✏️ Edit',    '#F59E0B', self._edit_selected),
            ('🗑 Delete',  C['danger'], self._delete_selected),
        ]:
            ctk.CTkButton(action_bar, text=label, width=95, height=30,
                          fg_color=color, hover_color=color,
                          font=('Segoe UI', 10),
                          command=cmd).pack(side='left', padx=3)

        # ── Health summary cards ──────────────────────────────────────────────
        self._cards_frame = ctk.CTkFrame(self, fg_color='transparent', height=74)
        self._cards_frame.pack(fill='x', padx=16, pady=(0, 6))
        self._cards_frame.pack_propagate(False)
        self._card_lbls = {}
        for key, label, color in [
            ('total',  'Total Connections', '#3B82F6'),
            ('ok',     'Tested OK',          '#10B981'),
            ('failed', 'Failed',             '#EF4444'),
            ('untested','Not Tested',        '#9AA0B4'),
        ]:
            card = ctk.CTkFrame(self._cards_frame,
                                fg_color=C['bg_secondary'],
                                corner_radius=8, width=160)
            card.pack(side='left', padx=(0, 8), fill='y')
            card.pack_propagate(False)
            ctk.CTkLabel(card, text=label, font=('Segoe UI', 9),
                         text_color=C['text_secondary']).pack(pady=(8, 0))
            lbl = ctk.CTkLabel(card, text='—', font=('Segoe UI', 20, 'bold'),
                               text_color=color)
            lbl.pack(pady=(0, 8))
            self._card_lbls[key] = lbl

        # ── Treeview ──────────────────────────────────────────────────────────
        tv_outer = ctk.CTkFrame(self, fg_color=C['bg_secondary'], corner_radius=8)
        tv_outer.pack(fill='both', expand=True, padx=16, pady=(0, 16))

        sn = f'BW{id(self)}.TV'
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
            self._tv.column(cid, width=w, minwidth=28, stretch=st)

        # Colour tags for status indicator
        self._tv.tag_configure('ok',      foreground='#10B981')
        self._tv.tag_configure('failed',  foreground='#EF4444')
        self._tv.tag_configure('unknown', foreground='#9AA0B4')

        vsb = ctk.CTkScrollbar(tv_outer, orientation='vertical', command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y', padx=(0, 4), pady=8)
        self._tv.pack(fill='both', expand=True, padx=8, pady=8)
        self._tv.bind('<Double-1>', lambda e: self._browse_selected())

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load(self):
        self.after(0, lambda: self._status_lbl.configure(
            text='⏳ Loading BW connections…'))
        conns = bo_session.get_bw_connections()
        if not self._destroyed:
            self.after(0, lambda c=conns: self._on_loaded(c))

    def _on_loaded(self, conns):
        self._conns = conns or []
        self._test_results = {c['id']: None for c in self._conns}
        self._filter()
        self._update_cards()

    def _filter(self):
        q = self._q_var.get().lower()
        shown = [c for c in self._conns
                 if not q
                 or q in c.get('name', '').lower()
                 or q in c.get('kind', '').lower()
                 or q in c.get('desc', '').lower()]

        for row in self._tv.get_children():
            self._tv.delete(row)

        for conn in shown:
            cid      = str(conn['id'])
            tested   = self._test_results.get(conn['id'])
            dot      = '●'
            tag      = 'unknown'
            if tested is True:  tag = 'ok'
            elif tested is False: tag = 'failed'

            ts = conn.get('updated', '')
            self._tv.insert('', 'end', iid=cid, tags=(tag,),
                            values=(dot,
                                    conn.get('name', ''),
                                    conn.get('kind', ''),
                                    conn.get('owner', ''),
                                    conn.get('desc', '')[:80],
                                    ts))

        self._status_lbl.configure(
            text=f'{len(self._conns)} connections  |  showing {len(shown)}')

    def _update_cards(self):
        total    = len(self._conns)
        ok       = sum(1 for v in self._test_results.values() if v is True)
        failed   = sum(1 for v in self._test_results.values() if v is False)
        untested = sum(1 for v in self._test_results.values() if v is None)
        self._card_lbls['total'].configure(text=str(total))
        self._card_lbls['ok'].configure(text=str(ok))
        self._card_lbls['failed'].configure(text=str(failed))
        self._card_lbls['untested'].configure(text=str(untested))

    # ── Actions ───────────────────────────────────────────────────────────────

    def _selected_conn(self):
        sel = self._tv.selection()
        if not sel:
            messagebox.showinfo('Select', 'Select a connection first.', parent=self)
            return None
        cid = sel[0]
        return next((c for c in self._conns if str(c['id']) == cid), None)

    def _test_selected(self):
        conn = self._selected_conn()
        if not conn:
            return
        self._status_lbl.configure(text=f'⏳ Testing: {conn["name"]}…')
        cid = conn['id']

        def _do():
            ok, msg = bo_session.test_bw_connection(cid)
            self._test_results[cid] = ok
            self.after(0, lambda: self._on_test_done(cid, ok, msg, conn['name']))

        threading.Thread(target=_do, daemon=True).start()

    def _on_test_done(self, cid, ok, msg, name):
        self._filter()
        self._update_cards()
        icon  = '✅' if ok else '❌'
        color = C['success'] if ok else C['danger']
        self._status_lbl.configure(text=f'{icon} {name}: {msg}')
        messagebox.showinfo('Test Result',
                            f'{icon}  {name}\n\n{msg}', parent=self)

    def _test_all(self):
        if not self._conns:
            messagebox.showinfo('No Connections', 'No connections loaded.', parent=self)
            return
        self._status_lbl.configure(text='⏳ Testing all connections…')

        def _do():
            for conn in self._conns:
                ok, _ = bo_session.test_bw_connection(conn['id'])
                self._test_results[conn['id']] = ok
            self.after(0, lambda: (self._filter(), self._update_cards(),
                                   self._status_lbl.configure(
                                       text=f'Test complete — '
                                            f'{sum(1 for v in self._test_results.values() if v)} OK  |  '
                                            f'{sum(1 for v in self._test_results.values() if v is False)} failed')))

        threading.Thread(target=_do, daemon=True).start()

    def _browse_selected(self):
        conn = self._selected_conn()
        if not conn:
            return
        _BExBrowserWindow(self, conn['name'], conn['id'])

    def _create_conn(self):
        dlg = _BWConnDialog(self)
        self.wait_window(dlg)
        if not dlg.result:
            return
        data = dlg.result
        self._status_lbl.configure(text='⏳ Creating connection…')

        def _do():
            ok, msg = bo_session.create_bw_connection(data)
            self.after(0, lambda: self._on_create_done(ok, msg, data['name']))

        threading.Thread(target=_do, daemon=True).start()

    def _on_create_done(self, ok, msg, name):
        if ok:
            self._status_lbl.configure(text=f'✅ Created: {name}')
            messagebox.showinfo('Created', f'✅ Connection created:\n{name}\n\n{msg}',
                                parent=self)
            threading.Thread(target=self._load, daemon=True).start()
        else:
            self._status_lbl.configure(text=f'❌ Create failed')
            messagebox.showerror('Error', f'❌ Could not create connection:\n{msg}',
                                 parent=self)

    def _edit_selected(self):
        conn = self._selected_conn()
        if not conn:
            return
        dlg = _BWConnDialog(self, conn_data=conn)
        self.wait_window(dlg)
        if not dlg.result:
            return
        data = dlg.result
        self._status_lbl.configure(text='⏳ Saving…')

        def _do():
            ok, msg = bo_session.update_bw_connection(conn['id'], data)
            self.after(0, lambda: self._on_edit_done(ok, msg, data['name']))

        threading.Thread(target=_do, daemon=True).start()

    def _on_edit_done(self, ok, msg, name):
        if ok:
            self._status_lbl.configure(text=f'✅ Saved: {name}')
            messagebox.showinfo('Saved', f'✅ Connection updated:\n{name}', parent=self)
            threading.Thread(target=self._load, daemon=True).start()
        else:
            self._status_lbl.configure(text='❌ Save failed')
            messagebox.showerror('Error', f'❌ Could not update:\n{msg}', parent=self)

    def _delete_selected(self):
        conn = self._selected_conn()
        if not conn:
            return
        name = conn['name']
        if not messagebox.askyesno(
                'Confirm Delete',
                f'Delete BW connection:\n  {name}\n\n'
                f'⚠  Reports using this connection will break.',
                parent=self):
            return
        self._status_lbl.configure(text=f'⏳ Deleting {name}…')

        def _do():
            ok, msg = bo_session.delete_bw_connection(conn['id'])
            self.after(0, lambda: self._on_delete_done(ok, msg, name))

        threading.Thread(target=_do, daemon=True).start()

    def _on_delete_done(self, ok, msg, name):
        if ok:
            self._status_lbl.configure(text=f'✅ Deleted: {name}')
            messagebox.showinfo('Deleted', f'✅ Deleted:\n{name}', parent=self)
            threading.Thread(target=self._load, daemon=True).start()
        else:
            self._status_lbl.configure(text='❌ Delete failed')
            messagebox.showerror('Error', f'❌ Could not delete:\n{msg}', parent=self)
