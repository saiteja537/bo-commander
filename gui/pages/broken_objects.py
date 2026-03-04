"""broken_objects.py — Broken Objects Detector"""
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


class BrokenObjectsPage(ctk.CTkFrame):
    _COLS = [
        ('name','Object Name',260,True),
        ('kind','Type',110,False),
        ('owner','Owner',100,False),
        ('cause','Cause',200,False),
        ('fix','Suggested Fix',200,True),
        ('updated','Updated',140,False),
    ]
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0, **kw)
        _PAGE_REF[0] = self.winfo_toplevel()
        self._items = []
        self._destroyed = False
        self._build_ui()

    def destroy(self):
        self._destroyed = True
        super().destroy()

    def _build_ui(self):
        hdr = ctk.CTkFrame(self, fg_color='transparent', height=48)
        hdr.pack(fill='x', pady=(0,6))
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text='🔨  Broken Objects',
                     font=F['sub_header'], text_color=C['text_primary']).pack(side='left')
        ctk.CTkButton(hdr, text='🔍  Scan', width=90, height=30,
                      fg_color=C['primary'], hover_color=C['primary_hover'],
                      font=F['small'], command=self._scan).pack(side='right', pady=8)
        ctk.CTkButton(hdr, text='🗑  Delete Selected', width=120, height=30,
                      fg_color=C['danger'], hover_color='#DC2626',
                      font=F['small'], command=self._delete_selected
                      ).pack(side='right', padx=6, pady=8)

        fbar = ctk.CTkFrame(self, fg_color=C['bg_secondary'], corner_radius=8, height=40)
        fbar.pack(fill='x', pady=(0,6))
        fbar.pack_propagate(False)
        self._q_var = ctk.StringVar()
        self._q_var.trace_add('write', lambda *_: self._filter())
        ctk.CTkEntry(fbar, textvariable=self._q_var,
                     placeholder_text='Filter results…', width=300, height=26,
                     fg_color=C['bg_tertiary'], border_color=C['bg_tertiary'],
                     text_color=C['text_primary'], font=F['small']
                     ).pack(side='left', padx=12, pady=6)
        self._status_var = ctk.StringVar(value='Click Scan to detect broken objects')
        ctk.CTkLabel(fbar, textvariable=self._status_var,
                     font=F['small'], text_color=C['text_secondary']
                     ).pack(side='right', padx=12)

        tv_frame = ctk.CTkFrame(self, fg_color=C['bg_secondary'], corner_radius=8)
        tv_frame.pack(fill='both', expand=True)
        sn = f'BO{id(tv_frame)}.TV'
        s = ttk.Style()
        s.configure(sn, background=C['bg_secondary'], foreground=C['text_primary'],
                    fieldbackground=C['bg_secondary'], rowheight=30,
                    font=('Segoe UI',10), borderwidth=0)
        s.configure(f'{sn}.Heading', background=C['bg_tertiary'],
                    foreground=C['text_secondary'], font=('Segoe UI',9,'bold'), relief='flat')
        s.map(sn, background=[('selected',C['primary'])], foreground=[('selected','white')])
        s.layout(sn, [('Treeview.treearea', {'sticky': 'nswe'})])
        self._tv = ttk.Treeview(tv_frame, style=sn, show='headings',
                                selectmode='extended',
                                columns=[c[0] for c in self._COLS])
        for cid, hd, w, st in self._COLS:
            self._tv.heading(cid, text=hd)
            self._tv.column(cid, width=w, minwidth=40, stretch=st)
        self._tv.tag_configure('broken', foreground='#EF4444')
        vsb = ctk.CTkScrollbar(tv_frame, orientation='vertical', command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        self._tv.pack(side='left', fill='both', expand=True)

    def _scan(self):
        self._status_var.set('⏳ Scanning…')
        _run_bg(bo_session.get_broken_objects, self._on_scanned)

    def _on_scanned(self, items):
        if self._destroyed: return
        self._items = items or []
        self._filter()

    def _filter(self):
        q = self._q_var.get().lower()
        shown = [i for i in self._items if not q or q in i.get('name','').lower()]
        for row in self._tv.get_children(): self._tv.delete(row)
        for it in shown:
            self._tv.insert('', 'end', iid=str(it['id']),
                            values=(it.get('name',''), it.get('kind',''),
                                    it.get('owner',''), it.get('cause',''),
                                    it.get('fix',''), it.get('updated','')),
                            tags=('broken',))
        self._status_var.set(f'{len(self._items)} broken objects found  |  showing {len(shown)}')

    def _delete_selected(self):
        sel = self._tv.selection()
        if not sel:
            messagebox.showinfo('Select', 'Select objects to delete.', parent=self)
            return
        if not messagebox.askyesno('Confirm', f'Delete {len(sel)} object(s)?', parent=self):
            return
        def _do():
            ok = sum(1 for iid in sel if bo_session.delete_object(iid)[0])
            return ok
        _run_bg(_do, lambda ok: (
            messagebox.showinfo('Done', f'{ok} object(s) deleted.', parent=self),
            self._scan()
        ))
