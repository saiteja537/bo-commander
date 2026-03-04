"""deep_search.py — Deep Search across all BO objects"""
import threading
from tkinter import ttk, messagebox
import customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS
F = Config.FONTS
_PAGE_REF = [None]

def _run_bg(fn, cb):
    root = _PAGE_REF[0]
    def _w():
        try:    r = fn()
        except Exception: r = None
        if root:
            try: root.after(0, lambda res=r: (cb(res) if cb else None))
            except Exception: pass
    threading.Thread(target=_w, daemon=True).start()


class DeepSearchPage(ctk.CTkFrame):
    _COLS = [
        ('name','Name',280,True),
        ('kind','Type',110,False),
        ('owner','Owner',100,False),
        ('desc','Description',250,True),
        ('source','Table',120,False),
        ('updated','Updated',140,False),
    ]
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0, **kw)
        _PAGE_REF[0] = self.winfo_toplevel()
        self._results = []
        self._destroyed = False
        self._build_ui()

    def destroy(self):
        self._destroyed = True
        super().destroy()

    def _build_ui(self):
        hdr = ctk.CTkFrame(self, fg_color='transparent', height=48)
        hdr.pack(fill='x', pady=(0,6))
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text='🔍  Deep Search',
                     font=F['sub_header'], text_color=C['text_primary']).pack(side='left')

        sbar = ctk.CTkFrame(self, fg_color=C['bg_secondary'], corner_radius=8, height=48)
        sbar.pack(fill='x', pady=(0,6))
        sbar.pack_propagate(False)
        self._q_var = ctk.StringVar()
        qe = ctk.CTkEntry(sbar, textvariable=self._q_var,
                          placeholder_text='Search across all BO objects…',
                          height=30, fg_color=C['bg_tertiary'], border_color=C['bg_tertiary'],
                          text_color=C['text_primary'], font=('Segoe UI',12))
        qe.pack(side='left', fill='x', expand=True, padx=(12,6), pady=8)
        qe.bind('<Return>', lambda e: self._search())

        self._kind_var = ctk.StringVar(value='All')
        ctk.CTkOptionMenu(sbar, variable=self._kind_var,
                          values=['All','Webi','CrystalReport','Universe',
                                  'Folder','User','UserGroup','Connection'],
                          width=130, height=30,
                          fg_color=C['bg_tertiary'], button_color=C['primary'],
                          dropdown_fg_color=C['bg_secondary'],
                          text_color=C['text_primary'], font=F['small']
                          ).pack(side='left', padx=4)
        ctk.CTkButton(sbar, text='Search', width=90, height=30,
                      fg_color=C['primary'], hover_color=C['primary_hover'],
                      font=F['small'], command=self._search).pack(side='left', padx=4)

        self._status_var = ctk.StringVar(value='Enter a search term above')
        ctk.CTkLabel(sbar, textvariable=self._status_var,
                     font=F['small'], text_color=C['text_secondary']
                     ).pack(side='right', padx=12)

        tv_frame = ctk.CTkFrame(self, fg_color=C['bg_secondary'], corner_radius=8)
        tv_frame.pack(fill='both', expand=True)
        sn = f'DS{id(tv_frame)}.TV'
        s = ttk.Style()
        s.configure(sn, background=C['bg_secondary'], foreground=C['text_primary'],
                    fieldbackground=C['bg_secondary'], rowheight=30,
                    font=('Segoe UI',10), borderwidth=0)
        s.configure(f'{sn}.Heading', background=C['bg_tertiary'],
                    foreground=C['text_secondary'], font=('Segoe UI',9,'bold'), relief='flat')
        s.map(sn, background=[('selected',C['primary'])], foreground=[('selected','white')])
        s.layout(sn, [('Treeview.treearea', {'sticky': 'nswe'})])
        self._tv = ttk.Treeview(tv_frame, style=sn, show='headings',
                                selectmode='browse',
                                columns=[c[0] for c in self._COLS])
        for cid, hd, w, st in self._COLS:
            self._tv.heading(cid, text=hd)
            self._tv.column(cid, width=w, minwidth=40, stretch=st)
        vsb = ctk.CTkScrollbar(tv_frame, orientation='vertical', command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        self._tv.pack(side='left', fill='both', expand=True)

    def _search(self):
        q = self._q_var.get().strip()
        if not q:
            messagebox.showinfo('Search', 'Enter a search term.', parent=self)
            return
        kind = self._kind_var.get()
        kinds = None if kind == 'All' else [kind]
        self._status_var.set('⏳ Searching…')
        _run_bg(lambda: bo_session.deep_search(q, search_in=kinds), self._on_results)

    def _on_results(self, results):
        if self._destroyed: return
        self._results = results or []
        for row in self._tv.get_children(): self._tv.delete(row)
        for r in self._results:
            self._tv.insert('', 'end', iid=str(r['id']),
                            values=(r.get('name',''), r.get('kind',''),
                                    r.get('owner',''), r.get('desc',''),
                                    r.get('source',''), r.get('updated','')))
        self._status_var.set(f'{len(self._results)} results found')
