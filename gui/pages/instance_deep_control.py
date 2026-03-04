"""instance_deep_control.py — Instance Deep Control"""
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


class InstanceDeepControlPage(ctk.CTkFrame):
    _COLS = [
        ('name','Instance Name',250,True),
        ('kind','Type',90,False),
        ('owner','Owner',100,False),
        ('status','Status',80,False),
        ('start','Started',140,False),
        ('end','Ended',140,False),
        ('dur','Duration(s)',80,False),
    ]
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0, **kw)
        _PAGE_REF[0] = self.winfo_toplevel()
        self._instances = []
        self._destroyed = False
        self._build_ui()

    def destroy(self):
        self._destroyed = True
        super().destroy()

    def _build_ui(self):
        hdr = ctk.CTkFrame(self, fg_color='transparent', height=48)
        hdr.pack(fill='x', pady=(0,6))
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text='🎛️  Instance Deep Control',
                     font=F['sub_header'], text_color=C['text_primary']).pack(side='left')
        _b = dict(height=30, corner_radius=6, font=F['small'])
        ctk.CTkButton(hdr, text='🔍  Load', width=80,
                      fg_color=C['primary'], hover_color=C['primary_hover'],
                      command=self._load, **_b).pack(side='right', pady=8)
        ctk.CTkButton(hdr, text='🗑  Delete', width=80,
                      fg_color=C['danger'], hover_color='#DC2626',
                      command=self._delete_sel, **_b).pack(side='right', padx=4, pady=8)
        ctk.CTkButton(hdr, text='↺  Retry', width=80,
                      fg_color=C['warning'], hover_color='#D97706',
                      command=self._retry_sel, **_b).pack(side='right', padx=0, pady=8)

        # Filters
        fbar = ctk.CTkFrame(self, fg_color=C['bg_secondary'], corner_radius=8, height=44)
        fbar.pack(fill='x', pady=(0,6))
        fbar.pack_propagate(False)

        ctk.CTkLabel(fbar, text='Status:', font=F['small'],
                     text_color=C['text_secondary']).pack(side='left', padx=(12,4))
        self._status_filter = ctk.StringVar(value='All')
        ctk.CTkOptionMenu(fbar, variable=self._status_filter,
                          values=['All','failed','success','running','pending'],
                          width=100, height=28,
                          fg_color=C['bg_tertiary'], button_color=C['primary'],
                          dropdown_fg_color=C['bg_secondary'],
                          text_color=C['text_primary'], font=F['small']
                          ).pack(side='left', padx=4)

        ctk.CTkLabel(fbar, text='Days back:', font=F['small'],
                     text_color=C['text_secondary']).pack(side='left', padx=(12,4))
        self._days_var = ctk.StringVar(value='7')
        ctk.CTkEntry(fbar, textvariable=self._days_var, width=50, height=28,
                     fg_color=C['bg_tertiary'], border_color=C['bg_tertiary'],
                     text_color=C['text_primary'], font=F['small']
                     ).pack(side='left', padx=4)

        ctk.CTkLabel(fbar, text='Owner:', font=F['small'],
                     text_color=C['text_secondary']).pack(side='left', padx=(12,4))
        self._owner_var = ctk.StringVar()
        ctk.CTkEntry(fbar, textvariable=self._owner_var, width=120, height=28,
                     placeholder_text='all',
                     fg_color=C['bg_tertiary'], border_color=C['bg_tertiary'],
                     text_color=C['text_primary'], font=F['small']
                     ).pack(side='left', padx=4)

        self._sv = ctk.StringVar(value='Configure filters and click Load')
        ctk.CTkLabel(fbar, textvariable=self._sv,
                     font=F['small'], text_color=C['text_secondary']
                     ).pack(side='right', padx=12)

        tv_frame = ctk.CTkFrame(self, fg_color=C['bg_secondary'], corner_radius=8)
        tv_frame.pack(fill='both', expand=True)
        sn = f'IDC{id(tv_frame)}.TV'
        s = ttk.Style()
        s.configure(sn, background=C['bg_secondary'], foreground=C['text_primary'],
                    fieldbackground=C['bg_secondary'], rowheight=28,
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
            self._tv.column(cid, width=w, minwidth=30, stretch=st)
        self._tv.tag_configure('Failed',  foreground='#EF4444')
        self._tv.tag_configure('Running', foreground='#22C55E')
        self._tv.tag_configure('Pending', foreground='#F59E0B')
        vsb = ctk.CTkScrollbar(tv_frame, orientation='vertical', command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        self._tv.pack(side='left', fill='both', expand=True)

    def _load(self):
        sf = self._status_filter.get()
        status = None if sf == 'All' else sf
        try: days = int(self._days_var.get() or 7)
        except ValueError: days = 7
        owner = self._owner_var.get().strip() or None
        self._sv.set('⏳ Loading…')
        _run_bg(
            lambda: bo_session.get_instances_deep(status=status, days_back=days, owner=owner),
            self._on_loaded
        )

    def _on_loaded(self, instances):
        if self._destroyed: return
        self._instances = instances or []
        for row in self._tv.get_children(): self._tv.delete(row)
        counts = {}
        for inst in self._instances:
            st = inst.get('status','')
            counts[st] = counts.get(st, 0) + 1
            self._tv.insert('', 'end', iid=str(inst['id']),
                            values=(inst.get('name',''), inst.get('kind',''),
                                    inst.get('owner',''), st,
                                    inst.get('start',''), inst.get('end',''),
                                    inst.get('duration',0)),
                            tags=(st,))
        summary = '  '.join(f'{k}: {v}' for k,v in counts.items())
        self._sv.set(f'{len(self._instances)} instances  |  {summary}')

    def _delete_sel(self):
        sel = self._tv.selection()
        if not sel:
            messagebox.showinfo('Select', 'Select instances to delete.', parent=self)
            return
        if not messagebox.askyesno('Confirm', f'Delete {len(sel)} instance(s)?', parent=self):
            return
        _run_bg(
            lambda: bo_session.bulk_delete_instances(list(sel)),
            lambda r: (
                messagebox.showinfo('Done', f'Deleted: {r[0]}  Errors: {r[1]}', parent=self),
                self._load()
            )
        )

    def _retry_sel(self):
        sel = self._tv.selection()
        if not sel:
            messagebox.showinfo('Select', 'Select failed instances to retry.', parent=self)
            return
        _run_bg(
            lambda: bo_session.bulk_retry_instances(list(sel)),
            lambda r: (
                messagebox.showinfo('Done', f'Retried: {r[0]}  Errors: {r[1]}', parent=self),
                self._load()
            )
        )
