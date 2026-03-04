"""gui/pages/metadata_view.py — Deep metadata inspector for any BO object"""
import threading
import customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS


class MetadataViewPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0)

        top = ctk.CTkFrame(self, fg_color='transparent', height=50)
        top.pack(fill='x', padx=20, pady=(15, 0))
        top.pack_propagate(False)
        ctk.CTkLabel(top, text='🔍  Metadata View',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')

        ctk.CTkLabel(self, text='Inspect full metadata / properties of any BO object by ID or name search.',
                     font=('Segoe UI', 11), text_color=C['text_secondary']).pack(anchor='w', padx=22, pady=(2,8))

        # Search bar
        search_row = ctk.CTkFrame(self, fg_color=C['bg_secondary'], corner_radius=8)
        search_row.pack(fill='x', padx=15, pady=(0, 8))

        ctk.CTkLabel(search_row, text='Search:', font=('Segoe UI', 11),
                     text_color=C['text_primary']).pack(side='left', padx=12, pady=10)

        self._search_entry = ctk.CTkEntry(search_row, width=380, font=('Segoe UI', 11),
                                          placeholder_text='Object name or SI_ID…')
        self._search_entry.pack(side='left', padx=6)
        self._search_entry.bind('<Return>', self._search)

        ctk.CTkLabel(search_row, text='In:', font=('Segoe UI', 11),
                     text_color=C['text_primary']).pack(side='left', padx=(12,4))

        self._table_var = ctk.StringVar(value='CI_INFOOBJECTS')
        ctk.CTkComboBox(search_row,
                        values=['CI_INFOOBJECTS', 'CI_APPOBJECTS', 'CI_SYSTEMOBJECTS'],
                        variable=self._table_var, width=180,
                        font=('Segoe UI', 11)).pack(side='left', padx=6)

        ctk.CTkButton(search_row, text='Search', width=90, height=32,
                      command=self._search).pack(side='left', padx=10)

        self._status = ctk.CTkLabel(search_row, text='', font=('Segoe UI', 11),
                                    text_color=C['text_secondary'])
        self._status.pack(side='right', padx=12)

        # Split: left = results list, right = properties panel
        split = ctk.CTkFrame(self, fg_color='transparent')
        split.pack(fill='both', expand=True, padx=15, pady=(0, 15))
        split.grid_columnconfigure(0, weight=1)
        split.grid_columnconfigure(1, weight=2)
        split.grid_rowconfigure(0, weight=1)

        # Left: result list
        self.list_frame = ctk.CTkScrollableFrame(split, fg_color=C['bg_secondary'],
                                                 corner_radius=8, width=320)
        self.list_frame.grid(row=0, column=0, sticky='nsew', padx=(0,6))

        # Right: properties panel
        self.props_frame = ctk.CTkScrollableFrame(split, fg_color=C['bg_secondary'],
                                                  corner_radius=8)
        self.props_frame.grid(row=0, column=1, sticky='nsew')

        ctk.CTkLabel(self.props_frame, text='Select an object on the left to view its metadata.',
                     font=('Segoe UI', 12), text_color=C['text_secondary']).pack(pady=40)

    def _search(self, event=None):
        term = self._search_entry.get().strip()
        if not term:
            self._status.configure(text='⚠ Enter a name or ID')
            return
        if not bo_session.connected:
            self._status.configure(text='❌ Not connected'); return

        for w in self.list_frame.winfo_children():
            w.destroy()
        for w in self.props_frame.winfo_children():
            w.destroy()
        self._status.configure(text='Searching…')
        ctk.CTkLabel(self.list_frame, text='⏳ Searching…', font=('Segoe UI', 11, 'italic'),
                     text_color=C['text_secondary']).pack(pady=20)
        threading.Thread(target=self._do_search, args=(term,), daemon=True).start()

    def _do_search(self, term):
        results = []
        table = self._table_var.get()
        try:
            if term.isdigit():
                sql = (f"SELECT TOP 1 SI_ID, SI_NAME, SI_KIND, SI_OWNER "
                       f"FROM {table} WHERE SI_ID={term}")
            else:
                safe = term.replace("'","''")
                sql = (f"SELECT TOP 50 SI_ID, SI_NAME, SI_KIND, SI_OWNER "
                       f"FROM {table} WHERE SI_NAME LIKE '%{safe}%' "
                       f"ORDER BY SI_NAME ASC")
            d = bo_session.run_cms_query(sql)
            if d and d.get('entries'):
                results = d['entries']
        except Exception as ex:
            results = []
            self.after(0, lambda: self._status.configure(text=f'❌ {ex}'))
            return
        self.after(0, lambda r=results: self._render_list(r))

    def _render_list(self, results):
        for w in self.list_frame.winfo_children():
            w.destroy()
        self._status.configure(text=f'{len(results)} result(s)')
        if not results:
            ctk.CTkLabel(self.list_frame, text='No objects found.',
                         font=('Segoe UI', 11), text_color=C['text_secondary']).pack(pady=20)
            return
        for e in results:
            eid  = e.get('SI_ID', '')
            name = e.get('SI_NAME', '')
            kind = e.get('SI_KIND', '')
            btn = ctk.CTkButton(self.list_frame,
                                text=f"{name}\n{kind}  [ID:{eid}]",
                                font=('Segoe UI', 10),
                                fg_color=C['bg_tertiary'],
                                hover_color=C['primary'],
                                text_color=C['text_primary'],
                                anchor='w',
                                height=48,
                                command=lambda eid=eid: self._load_props(eid))
            btn.pack(fill='x', padx=4, pady=2)

    def _load_props(self, obj_id):
        for w in self.props_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.props_frame, text=f'⏳ Loading metadata for ID {obj_id}…',
                     font=('Segoe UI', 11, 'italic'), text_color=C['text_secondary']).pack(pady=20)
        threading.Thread(target=self._fetch_props, args=(obj_id,), daemon=True).start()

    def _fetch_props(self, obj_id):
        props = {}
        table = self._table_var.get()
        try:
            d = bo_session.run_cms_query(
                f"SELECT TOP 1 * FROM {table} WHERE SI_ID={obj_id}"
            )
            if d and d.get('entries'):
                props = d['entries'][0]
        except Exception as ex:
            props = {'Error': str(ex)}
        self.after(0, lambda p=props: self._render_props(p))

    def _render_props(self, props):
        for w in self.props_frame.winfo_children():
            w.destroy()
        if not props:
            ctk.CTkLabel(self.props_frame, text='No properties returned.',
                         font=('Segoe UI', 11), text_color=C['text_secondary']).pack(pady=20)
            return

        # Title
        name = props.get('SI_NAME', f"ID {props.get('SI_ID','')}")
        ctk.CTkLabel(self.props_frame, text=f'📄 {name}',
                     font=('Segoe UI', 13, 'bold'), text_color=C['text_primary'],
                     anchor='w').pack(fill='x', padx=15, pady=(12,6))

        # Key props first
        priority = ['SI_ID','SI_NAME','SI_KIND','SI_OWNER','SI_PARENTID',
                    'SI_CREATION_TIME','SI_UPDATE_TS','SI_DESCRIPTION']
        shown = set()
        for key in priority:
            if key in props:
                self._prop_row(key, props[key])
                shown.add(key)

        ctk.CTkFrame(self.props_frame, fg_color=C['bg_tertiary'],
                     height=1).pack(fill='x', padx=15, pady=6)

        # Remaining props
        for key, val in sorted(props.items()):
            if key not in shown:
                self._prop_row(key, val)

    def _prop_row(self, key, val):
        row = ctk.CTkFrame(self.props_frame, fg_color='transparent')
        row.pack(fill='x', padx=12, pady=1)
        ctk.CTkLabel(row, text=key, width=220, anchor='w',
                     font=('Segoe UI', 10, 'bold'),
                     text_color=C['text_secondary']).pack(side='left')
        val_str = str(val)[:200] if val is not None else 'null'
        ctk.CTkLabel(row, text=val_str, anchor='w',
                     font=('Consolas', 10),
                     text_color=C['text_primary'],
                     wraplength=500).pack(side='left', padx=8)
