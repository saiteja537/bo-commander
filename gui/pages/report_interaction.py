"""
report_interaction.py — Interactive Report Runner
Run BO reports with prompt/parameter input directly from the GUI.
"""
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
            try: root.after(0, lambda res=r: _safe(cb, res))
            except Exception: pass
    threading.Thread(target=_w, daemon=True).start()

def _safe(cb, res):
    try: cb(res)
    except Exception: pass


class ReportInteractionPage(ctk.CTkFrame):

    _COLS = [
        ('name',     'Report Name',   280, True),
        ('kind',     'Type',           90, False),
        ('owner',    'Owner',         110, False),
        ('last_run', 'Last Run',      140, False),
    ]

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0, **kw)
        _PAGE_REF[0] = self.winfo_toplevel()
        self._reports   = []
        self._sel_id    = None
        self._destroyed = False
        self._build_ui()
        self._load()

    def destroy(self):
        self._destroyed = True
        super().destroy()

    def _build_ui(self):
        hdr = ctk.CTkFrame(self, fg_color='transparent', height=48)
        hdr.pack(fill='x', pady=(0, 6))
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text='▶  Interactive Report Runner',
                     font=F['sub_header'], text_color=C['text_primary']).pack(side='left')
        ctk.CTkButton(hdr, text='⟳  Refresh', width=90, height=30,
                      fg_color=C['bg_tertiary'], hover_color=C['primary'],
                      font=F['small'], command=self._load).pack(side='right', pady=8)

        # Filter
        fbar = ctk.CTkFrame(self, fg_color=C['bg_secondary'], corner_radius=8, height=40)
        fbar.pack(fill='x', pady=(0, 6))
        fbar.pack_propagate(False)
        self._q_var = ctk.StringVar()
        self._q_var.trace_add('write', lambda *_: self._filter())
        ctk.CTkEntry(fbar, textvariable=self._q_var,
                     placeholder_text='🔍 Search reports…',
                     width=300, height=26,
                     fg_color=C['bg_tertiary'], border_color=C['bg_tertiary'],
                     text_color=C['text_primary'], font=F['small']
                     ).pack(side='left', padx=12, pady=6)
        self._status_var = ctk.StringVar(value='Loading…')
        ctk.CTkLabel(fbar, textvariable=self._status_var,
                     font=F['small'], text_color=C['text_secondary']
                     ).pack(side='right', padx=12)

        # Body — left: report list, right: run panel
        body = ctk.CTkFrame(self, fg_color='transparent')
        body.pack(fill='both', expand=True)

        # Report list
        left = ctk.CTkFrame(body, fg_color=C['bg_secondary'], corner_radius=8, width=420)
        left.pack(side='left', fill='y', padx=(0, 8))
        left.pack_propagate(False)

        sn = f'RI{id(left)}.TV'
        s = ttk.Style()
        s.configure(sn, background=C['bg_secondary'], foreground=C['text_primary'],
                    fieldbackground=C['bg_secondary'], rowheight=30,
                    font=('Segoe UI', 10), borderwidth=0)
        s.configure(f'{sn}.Heading', background=C['bg_tertiary'],
                    foreground=C['text_secondary'],
                    font=('Segoe UI', 9, 'bold'), relief='flat')
        s.map(sn, background=[('selected', C['primary'])], foreground=[('selected', 'white')])
        s.layout(sn, [('Treeview.treearea', {'sticky': 'nswe'})])

        self._tv = ttk.Treeview(left, style=sn, show='headings',
                                selectmode='browse',
                                columns=[c[0] for c in self._COLS])
        for cid, hd, w, st in self._COLS:
            self._tv.heading(cid, text=hd)
            self._tv.column(cid, width=w, minwidth=40, stretch=st)
        vsb = ctk.CTkScrollbar(left, orientation='vertical', command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        self._tv.pack(side='left', fill='both', expand=True)
        self._tv.bind('<<TreeviewSelect>>', self._on_report_select)

        # Run panel
        self._run_panel = ctk.CTkScrollableFrame(body, fg_color=C['bg_secondary'], corner_radius=8)
        self._run_panel.pack(side='left', fill='both', expand=True)
        ctk.CTkLabel(self._run_panel,
                     text='Select a report to view its parameters and run options.',
                     font=F['small'], text_color=C['text_secondary']).pack(pady=30)

    def _load(self):
        self._status_var.set('⏳ Loading reports…')
        _run_bg(bo_session.get_all_reports, self._on_loaded)

    def _on_loaded(self, reports):
        if self._destroyed:
            return
        self._reports = reports or []
        self._filter()

    def _filter(self):
        q = self._q_var.get().lower()
        shown = [r for r in self._reports
                 if not q or q in r.get('name','').lower()]
        for row in self._tv.get_children():
            self._tv.delete(row)
        for r in shown:
            self._tv.insert('', 'end', iid=str(r['id']),
                            values=(r.get('name',''), r.get('kind',''),
                                    r.get('owner',''), r.get('last_run','')))
        self._status_var.set(f'{len(self._reports)} reports  |  showing {len(shown)}')

    def _on_report_select(self, event):
        sel = self._tv.selection()
        if not sel:
            return
        self._sel_id = sel[0]
        self._status_var.set('⏳ Loading parameters…')
        _run_bg(lambda: bo_session.get_report_prompts(self._sel_id),
                self._render_run_panel)

    def _render_run_panel(self, prompts):
        if self._destroyed:
            return
        for w in self._run_panel.winfo_children():
            w.destroy()

        # Report name
        name = next((r['name'] for r in self._reports if str(r['id']) == self._sel_id), 'Report')
        ctk.CTkLabel(self._run_panel, text=f'▶  {name}',
                     font=('Segoe UI', 13, 'bold'),
                     text_color=C['text_primary']).pack(anchor='w', padx=16, pady=(12, 4))

        self._prompt_vars = {}
        if prompts:
            ctk.CTkLabel(self._run_panel, text='Parameters:',
                         font=('Segoe UI', 10, 'bold'),
                         text_color=C['text_secondary']).pack(anchor='w', padx=16, pady=(8, 4))
            for p in prompts:
                pname = p.get('name', str(p))
                row = ctk.CTkFrame(self._run_panel, fg_color='transparent')
                row.pack(fill='x', padx=16, pady=3)
                ctk.CTkLabel(row, text=pname, width=180, anchor='w',
                             font=F['small'],
                             text_color=C['text_secondary']).pack(side='left')
                var = ctk.StringVar()
                self._prompt_vars[pname] = var
                ctk.CTkEntry(row, textvariable=var, width=240, height=26,
                             fg_color=C['bg_tertiary'], border_color=C['bg_tertiary'],
                             text_color=C['text_primary'], font=F['small']
                             ).pack(side='left', padx=8)
        else:
            ctk.CTkLabel(self._run_panel,
                         text='ℹ  No parameters required — report runs immediately.',
                         font=F['small'], text_color=C['text_secondary']
                         ).pack(anchor='w', padx=16, pady=8)

        # Format selector
        frow = ctk.CTkFrame(self._run_panel, fg_color='transparent')
        frow.pack(fill='x', padx=16, pady=(12, 4))
        ctk.CTkLabel(frow, text='Output Format:', width=140, anchor='w',
                     font=F['small'], text_color=C['text_secondary']).pack(side='left')
        self._fmt_var = ctk.StringVar(value='PDF')
        ctk.CTkOptionMenu(frow, variable=self._fmt_var,
                          values=['PDF', 'Excel', 'CSV', 'HTML'],
                          width=120, height=26,
                          fg_color=C['bg_tertiary'], button_color=C['primary'],
                          dropdown_fg_color=C['bg_secondary'],
                          text_color=C['text_primary'], font=F['small']
                          ).pack(side='left', padx=8)

        ctk.CTkButton(self._run_panel, text='▶  Run Report', width=140, height=36,
                      fg_color=C['success'], hover_color=C['accent'],
                      font=('Segoe UI', 12, 'bold'),
                      command=self._run_report).pack(anchor='w', padx=16, pady=16)

        self._status_var.set(f'{len(prompts or [])} parameters — ready to run')

    def _run_report(self):
        if not self._sel_id:
            return
        params = {k: v.get() for k, v in self._prompt_vars.items() if v.get()}
        self._status_var.set('⏳ Running report…')
        _run_bg(
            lambda: bo_session.run_report_with_prompts(self._sel_id, params),
            lambda r: (
                messagebox.showinfo('Result',
                                    '✅ Report scheduled successfully!' if r and r[0]
                                    else f'Failed: {r}',
                                    parent=self),
                self._status_var.set('Done')
            )
        )
