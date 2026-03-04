"""
gui/pages/report_viewer.py  —  BO Report Viewer
──────────────────────────────────────────────────────────────────────────────
Unified viewer for ALL SAP BO report types:

  1. Web Intelligence (WebI)  — full control via Raylight REST
       • View in embedded browser panel (HTML / Launchpad)
       • Refresh with prompt input
       • Export: PDF / Excel / CSV / HTML
       • Schedule, view instances

  2. Crystal Reports           — via Launchpad URL + REST scheduling
       • Open in browser redirect
       • Export PDF / Excel
       • Schedule

  3. Analysis for Office (AO) — Excel workbooks stored in repository
       • Download
       • Schedule
       • Open in Launchpad if available

Capability reference:
  Feature          | WebI  | Crystal    | AO
  List             |  ✅   |   ✅       |  ✅
  View inline      |  ✅   |  ⚠ URL    |  ❌
  Refresh          |  ✅   |  ⚠ sched  |  ❌
  Export           |  ✅   |   ✅       |  ⚠
  AI Integration   | ⭐⭐⭐⭐|   ⭐⭐      |  ⭐
──────────────────────────────────────────────────────────────────────────────
"""

import threading
import os
import webbrowser
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk
from datetime import datetime
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS

# ── optional: embedded browser ────────────────────────────────────────────────
try:
    import tkinterweb
    HAS_BROWSER = True
except ImportError:
    HAS_BROWSER = False

# ── report type metadata ──────────────────────────────────────────────────────
REPORT_TYPES = {
    'Webi': {
        'label':    'Web Intelligence',
        'short':    'WebI',
        'icon':     '📊',
        'color':    '#3B82F6',
        'can_view': True,
        'can_refresh': True,
        'can_export': True,
        'export_fmts': ['PDF', 'Excel', 'CSV', 'HTML'],
        'api_path': 'v1/documents',
        'badge':    'Full REST control',
        'badge_ok': True,
    },
    'CrystalReport': {
        'label':    'Crystal Reports',
        'short':    'Crystal',
        'icon':     '💎',
        'color':    '#8B5CF6',
        'can_view': False,     # open in browser/launchpad
        'can_refresh': False,  # schedule only
        'can_export': True,
        'export_fmts': ['PDF', 'Excel'],
        'api_path': 'v1/documents',
        'badge':    'Via Launchpad / Export',
        'badge_ok': None,
    },
    'Excel': {
        'label':    'Analysis for Office (AO)',
        'short':    'AO / Excel',
        'icon':     '📗',
        'color':    '#10B981',
        'can_view': False,
        'can_refresh': False,
        'can_export': True,
        'export_fmts': ['Excel (XLSX)', 'Download'],
        'api_path': 'infostore',
        'badge':    'Download / Schedule',
        'badge_ok': False,
    },
    'Pdf': {
        'label':    'PDF Document',
        'short':    'PDF',
        'icon':     '📄',
        'color':    '#EF4444',
        'can_view': False,
        'can_refresh': False,
        'can_export': True,
        'export_fmts': ['PDF'],
        'api_path': 'infostore',
        'badge':    'Download only',
        'badge_ok': False,
    },
}

def _type_meta(kind):
    return REPORT_TYPES.get(kind, {
        'label': kind, 'short': kind, 'icon': '📋',
        'color': '#64748B', 'can_view': False,
        'can_refresh': False, 'can_export': True,
        'export_fmts': ['PDF', 'Excel'],
        'api_path': 'infostore',
        'badge': 'Export / Schedule', 'badge_ok': None,
    })

# ── background helper ─────────────────────────────────────────────────────────
_ROOT = [None]

def _bg(fn, cb):
    root = _ROOT[0]
    def _w():
        try:    r = fn()
        except Exception as e: r = None
        if root:
            try: root.after(0, lambda res=r: cb(res))
            except Exception: pass
    threading.Thread(target=_w, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
#  Prompt / Parameter dialog
# ─────────────────────────────────────────────────────────────────────────────

class _PromptDialog(ctk.CTkToplevel):
    """Collects prompt values before running/exporting a WebI report."""

    def __init__(self, parent, report_name, prompts):
        super().__init__(parent)
        self.title(f'📝  Prompts — {report_name[:50]}')
        self.geometry('480x460')
        self.configure(fg_color=C['bg_primary'])
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        self._vars  = {}
        self._build(prompts)

    def _build(self, prompts):
        ctk.CTkLabel(self, text='📝  Enter Report Prompts',
                     font=('Segoe UI', 15, 'bold'),
                     text_color=C['text_primary']).pack(anchor='w', padx=20, pady=(16, 4))
        ctk.CTkLabel(self,
                     text='Fill in required values before running the report.',
                     font=('Segoe UI', 10),
                     text_color=C['text_secondary']).pack(anchor='w', padx=20, pady=(0, 10))

        form = ctk.CTkScrollableFrame(self, fg_color='transparent')
        form.pack(fill='both', expand=True, padx=20, pady=(0, 4))

        if not prompts:
            ctk.CTkLabel(form, text='No prompts required for this report.',
                         font=('Segoe UI', 11), text_color=C['success']).pack(pady=20)
        else:
            for p in prompts:
                name      = p.get('name', p.get('id', str(p)))
                mandatory = p.get('mandatory', True)
                ptype     = p.get('type', 'text')
                lbl_txt   = f'{name}{"  *" if mandatory else ""}'
                ctk.CTkLabel(form, text=lbl_txt, font=('Segoe UI', 10),
                             text_color=C['text_secondary']).pack(anchor='w', pady=(8, 1))
                var = ctk.StringVar()
                self._vars[name] = var
                ctk.CTkEntry(form, textvariable=var, height=30,
                             placeholder_text=f'Enter {name}…',
                             fg_color=C['bg_secondary'],
                             border_color=C['primary'] if mandatory else C['bg_tertiary'],
                             text_color=C['text_primary'],
                             font=('Segoe UI', 11)).pack(fill='x')

        btns = ctk.CTkFrame(self, fg_color='transparent', height=48)
        btns.pack(fill='x', padx=20, pady=(4, 12))
        btns.pack_propagate(False)
        ctk.CTkButton(btns, text='Cancel', width=90, height=34,
                      fg_color=C['bg_tertiary'], text_color=C['text_primary'],
                      command=self.destroy).pack(side='right')
        ctk.CTkButton(btns, text='▶  Run Report', width=130, height=34,
                      fg_color=C['primary'], hover_color=C['accent'],
                      command=self._submit).pack(side='right', padx=(0, 6))

    def _submit(self):
        self.result = {k: v.get().strip() for k, v in self._vars.items()}
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
#  Schedule dialog
# ─────────────────────────────────────────────────────────────────────────────

class _ScheduleDialog(ctk.CTkToplevel):

    FREQ_OPTIONS = ['Once (immediate)', 'Hourly', 'Daily', 'Weekly', 'Monthly']
    FMT_OPTIONS  = ['PDF', 'Excel', 'CSV', 'HTML', 'Original']

    def __init__(self, parent, report_name):
        super().__init__(parent)
        self.title(f'📅  Schedule — {report_name[:50]}')
        self.geometry('420x380')
        self.configure(fg_color=C['bg_primary'])
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text='📅  Schedule Report',
                     font=('Segoe UI', 15, 'bold'),
                     text_color=C['text_primary']).pack(anchor='w', padx=20, pady=(16, 12))

        form = ctk.CTkFrame(self, fg_color='transparent')
        form.pack(fill='x', padx=20)

        for label, attr, options, default in [
            ('Frequency',     '_freq',   self.FREQ_OPTIONS,  'Once (immediate)'),
            ('Output Format', '_fmt',    self.FMT_OPTIONS,   'PDF'),
        ]:
            ctk.CTkLabel(form, text=label, font=('Segoe UI', 10),
                         text_color=C['text_secondary']).pack(anchor='w', pady=(8, 2))
            var = ctk.StringVar(value=default)
            setattr(self, attr, var)
            ctk.CTkOptionMenu(form, values=options, variable=var,
                              fg_color=C['bg_secondary'],
                              button_color=C['primary'],
                              text_color=C['text_primary'],
                              height=30).pack(fill='x')

        ctk.CTkLabel(form, text='Destination (email / folder, optional)',
                     font=('Segoe UI', 10),
                     text_color=C['text_secondary']).pack(anchor='w', pady=(8, 2))
        self._dest = ctk.StringVar()
        ctk.CTkEntry(form, textvariable=self._dest, height=30,
                     placeholder_text='e.g. user@company.com or leave blank',
                     fg_color=C['bg_secondary'],
                     border_color=C['bg_tertiary'],
                     text_color=C['text_primary'],
                     font=('Segoe UI', 11)).pack(fill='x')

        btns = ctk.CTkFrame(self, fg_color='transparent', height=50)
        btns.pack(fill='x', padx=20, pady=(16, 0))
        btns.pack_propagate(False)
        ctk.CTkButton(btns, text='Cancel', width=90, height=34,
                      fg_color=C['bg_tertiary'], text_color=C['text_primary'],
                      command=self.destroy).pack(side='right')
        ctk.CTkButton(btns, text='📅  Schedule', width=110, height=34,
                      fg_color=C['primary'], hover_color=C['accent'],
                      command=self._submit).pack(side='right', padx=(0, 6))

    def _submit(self):
        self.result = {
            'frequency':   self._freq.get(),
            'format':      self._fmt.get(),
            'destination': self._dest.get().strip(),
        }
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
#  Detail / Preview panel (right side)
# ─────────────────────────────────────────────────────────────────────────────

class _DetailPanel(ctk.CTkFrame):
    """Right-side panel showing report metadata + actions for selected report."""

    def __init__(self, parent, on_status, **kw):
        super().__init__(parent, fg_color=C['bg_secondary'],
                         corner_radius=10, **kw)
        self._on_status  = on_status
        self._report     = None
        self._prompts    = []
        self._build_empty()

    def _build_empty(self):
        for w in self.winfo_children():
            w.destroy()
        ctk.CTkLabel(self,
                     text='👈  Select a report\nto see details & actions',
                     font=('Segoe UI', 13),
                     text_color=C['text_secondary'],
                     justify='center').pack(expand=True)

    def load(self, report):
        self._report  = report
        self._prompts = []
        for w in self.winfo_children():
            w.destroy()
        self._build_detail(report)
        # Load prompts for WebI in background
        if report.get('kind') == 'Webi':
            _bg(lambda: bo_session.get_report_prompts(report['id']),
                self._on_prompts)

    def _on_prompts(self, prompts):
        self._prompts = prompts or []
        if self._prompt_lbl and self._prompt_lbl.winfo_exists():
            n = len(self._prompts)
            self._prompt_lbl.configure(
                text=f'{n} prompt{"s" if n != 1 else ""}',
                text_color='#F59E0B' if n > 0 else C['success'])

    def _build_detail(self, r):
        meta = _type_meta(r.get('kind', ''))

        # ── Title strip ───────────────────────────────────────────────────────
        title_bar = ctk.CTkFrame(self, fg_color=meta['color'],
                                 corner_radius=10, height=54)
        title_bar.pack(fill='x', padx=2, pady=(2, 0))
        title_bar.pack_propagate(False)

        ctk.CTkLabel(title_bar,
                     text=f'{meta["icon"]}  {meta["short"]}',
                     font=('Segoe UI', 13, 'bold'),
                     text_color='white').pack(side='left', padx=12)

        badge_color = '#10B981' if meta['badge_ok'] is True \
            else '#EF4444' if meta['badge_ok'] is False else '#F59E0B'
        ctk.CTkLabel(title_bar, text=meta['badge'],
                     font=('Segoe UI', 9, 'bold'),
                     fg_color=badge_color,
                     corner_radius=4,
                     text_color='white').pack(side='right', padx=10)

        # ── Metadata ──────────────────────────────────────────────────────────
        info_frame = ctk.CTkFrame(self, fg_color='transparent')
        info_frame.pack(fill='x', padx=12, pady=8)

        fields = [
            ('Report Name', r.get('name', '—')),
            ('Type',        meta['label']),
            ('Owner',       r.get('owner', '—')),
            ('Created',     r.get('created', '—')),
            ('Last Run',    r.get('last_run', '—')),
            ('ID',          str(r.get('id', '—'))),
        ]
        for label, value in fields:
            row = ctk.CTkFrame(info_frame, fg_color='transparent', height=22)
            row.pack(fill='x', pady=1)
            row.pack_propagate(False)
            ctk.CTkLabel(row, text=f'{label}:',
                         width=90, anchor='w',
                         font=('Segoe UI', 10),
                         text_color=C['text_secondary']).pack(side='left')
            ctk.CTkLabel(row, text=str(value)[:55], anchor='w',
                         font=('Segoe UI', 10),
                         text_color=C['text_primary']).pack(side='left')

        # Prompt count (WebI only)
        self._prompt_lbl = None
        if r.get('kind') == 'Webi':
            prow = ctk.CTkFrame(info_frame, fg_color='transparent', height=22)
            prow.pack(fill='x', pady=1)
            prow.pack_propagate(False)
            ctk.CTkLabel(prow, text='Prompts:',
                         width=90, anchor='w',
                         font=('Segoe UI', 10),
                         text_color=C['text_secondary']).pack(side='left')
            self._prompt_lbl = ctk.CTkLabel(prow, text='checking…',
                                            anchor='w',
                                            font=('Segoe UI', 10),
                                            text_color=C['text_secondary'])
            self._prompt_lbl.pack(side='left')

        # Separator
        ctk.CTkFrame(self, fg_color=C['bg_tertiary'], height=1).pack(
            fill='x', padx=12, pady=(0, 6))

        # ── Action buttons ────────────────────────────────────────────────────
        acts = ctk.CTkScrollableFrame(self, fg_color='transparent', corner_radius=0)
        acts.pack(fill='both', expand=True, padx=10, pady=(0, 8))

        kind = r.get('kind', '')

        if kind == 'Webi':
            self._add_action(acts, '▶  Run / Refresh',  '#3B82F6', self._run_webi)
            self._add_action(acts, '🌐  Open in Browser', '#0EA5E9', self._open_browser)
            self._add_section(acts, 'Export')
            for fmt in ['PDF', 'Excel', 'CSV']:
                self._add_action(acts, f'⬇  Export {fmt}', '#6366F1',
                                 lambda f=fmt: self._export(f))
            self._add_section(acts, 'Manage')
            self._add_action(acts, '📅  Schedule',       '#10B981', self._schedule)
            self._add_action(acts, '📋  View Instances', '#F59E0B', self._view_instances)

        elif kind == 'CrystalReport':
            self._add_action(acts, '🌐  Open in Launchpad', '#8B5CF6', self._open_browser)
            self._add_section(acts, 'Export')
            for fmt in ['PDF', 'Excel']:
                self._add_action(acts, f'⬇  Export {fmt}', '#6366F1',
                                 lambda f=fmt: self._export(f))
            self._add_section(acts, 'Manage')
            self._add_action(acts, '📅  Schedule',       '#10B981', self._schedule)
            self._add_action(acts, '📋  View Instances', '#F59E0B', self._view_instances)
            self._add_info(acts,
                '⚠  Crystal Reports cannot be rendered inline. '
                'Use "Open in Launchpad" to view in browser.')

        elif kind in ('Excel', 'Pdf'):
            self._add_action(acts, '⬇  Download File',  '#10B981', self._download)
            self._add_action(acts, '🌐  Open in Launchpad', '#0EA5E9', self._open_browser)
            self._add_section(acts, 'Manage')
            self._add_action(acts, '📅  Schedule',       '#8B5CF6', self._schedule)
            self._add_info(acts,
                '📗  Analysis for Office workbooks must be opened '
                'in Excel with the SAP AO add-in installed.')

        else:
            self._add_action(acts, '🌐  Open in Browser', '#3B82F6', self._open_browser)
            self._add_action(acts, '⬇  Export PDF',   '#6366F1',
                             lambda: self._export('PDF'))

    def _add_section(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=('Segoe UI', 10, 'bold'),
                     text_color=C['text_secondary'],
                     anchor='w').pack(fill='x', padx=4, pady=(10, 2))

    def _add_action(self, parent, label, color, cmd):
        ctk.CTkButton(parent, text=label, height=32, anchor='w',
                      fg_color=color, hover_color=color,
                      font=('Segoe UI', 11),
                      command=cmd).pack(fill='x', padx=4, pady=2)

    def _add_info(self, parent, text):
        ctk.CTkLabel(parent, text=text,
                     font=('Segoe UI', 9),
                     text_color=C['text_secondary'],
                     wraplength=240, justify='left').pack(
            anchor='w', padx=6, pady=(8, 0))

    # ── Actions ───────────────────────────────────────────────────────────────

    def _run_webi(self):
        if not self._report: return
        prompts = self._prompts or []
        if prompts:
            dlg = _PromptDialog(self.winfo_toplevel(),
                                self._report['name'], prompts)
            self.winfo_toplevel().wait_window(dlg)
            if dlg.result is None: return
            prompt_vals = dlg.result
        else:
            prompt_vals = {}

        self._on_status('⏳ Running report…')
        _bg(lambda: bo_session.run_report_with_prompts(
                self._report['id'], prompt_vals),
            self._on_run_done)

    def _on_run_done(self, result):
        if result and result[0]:
            self._on_status('✅ Report run submitted successfully')
            messagebox.showinfo('Success',
                                '✅ Report run submitted!\n\n'
                                'Check Instances to see the output.',
                                parent=self.winfo_toplevel())
        else:
            msg = result[1] if result else 'Unknown error'
            self._on_status(f'❌ Run failed: {msg}')
            messagebox.showerror('Failed',
                                 f'❌ Could not run report:\n{msg}',
                                 parent=self.winfo_toplevel())

    def _open_browser(self):
        if not self._report: return
        url = bo_session.get_report_launchpad_url(self._report['id'],
                                                   self._report.get('kind', ''))
        if url:
            webbrowser.open(url)
            self._on_status(f'🌐 Opened in browser: {self._report["name"]}')
        else:
            messagebox.showwarning('No URL',
                                   'Could not build a Launchpad URL.\n'
                                   'Check BO server host configuration in Settings.',
                                   parent=self.winfo_toplevel())

    def _export(self, fmt):
        if not self._report: return
        ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
        ext  = {'PDF': '.pdf', 'Excel': '.xlsx', 'CSV': '.csv',
                'HTML': '.html'}.get(fmt, '.bin')
        name = self._report['name'].replace(' ', '_').replace('/', '_')[:40]
        path = filedialog.asksaveasfilename(
            title=f'Export {fmt}',
            defaultextension=ext,
            filetypes=[(f'{fmt} File', f'*{ext}')],
            initialfile=f'{name}_{ts}{ext}',
            parent=self.winfo_toplevel()
        )
        if not path: return
        self._on_status(f'⏳ Exporting {fmt}…')
        _bg(lambda: bo_session.export_report(
                self._report['id'], fmt, self._report.get('kind', 'Webi')),
            lambda r: self._on_export_done(r, path, fmt))

    def _on_export_done(self, data, path, fmt):
        if data:
            try:
                mode = 'wb' if isinstance(data, bytes) else 'w'
                with open(path, mode) as f:
                    f.write(data)
                size_kb = os.path.getsize(path) // 1024
                self._on_status(f'✅ Exported {fmt}: {os.path.basename(path)} ({size_kb} KB)')
                messagebox.showinfo('Exported',
                                    f'✅ {fmt} exported successfully!\n\n'
                                    f'File: {path}\nSize: {size_kb} KB',
                                    parent=self.winfo_toplevel())
            except Exception as e:
                self._on_status(f'❌ Save failed: {e}')
        else:
            self._on_status(f'❌ Export {fmt} failed — no data returned')
            messagebox.showerror('Export Failed',
                                 f'❌ Could not export as {fmt}.\n'
                                 f'The BO server may not support this format for this report type.',
                                 parent=self.winfo_toplevel())

    def _download(self):
        """Download raw file (AO/Excel/PDF)."""
        self._export('Excel' if self._report.get('kind') == 'Excel' else 'PDF')

    def _schedule(self):
        if not self._report: return
        dlg = _ScheduleDialog(self.winfo_toplevel(), self._report['name'])
        self.winfo_toplevel().wait_window(dlg)
        if not dlg.result: return
        self._on_status('⏳ Scheduling…')
        sched = dlg.result
        _bg(lambda: bo_session.schedule_report(
                self._report['id'], sched['frequency'],
                sched['format'], sched['destination']),
            lambda r: self._on_schedule_done(r))

    def _on_schedule_done(self, result):
        ok  = result[0] if isinstance(result, tuple) else bool(result)
        msg = result[1] if isinstance(result, tuple) and len(result) > 1 else ''
        if ok:
            self._on_status('✅ Scheduled successfully')
            messagebox.showinfo('Scheduled', '✅ Report scheduled!', parent=self.winfo_toplevel())
        else:
            self._on_status(f'❌ Schedule failed: {msg}')
            messagebox.showerror('Failed', f'❌ Could not schedule:\n{msg}',
                                 parent=self.winfo_toplevel())

    def _view_instances(self):
        if not self._report: return
        _InstancesWindow(self.winfo_toplevel(), self._report)


# ─────────────────────────────────────────────────────────────────────────────
#  Instances window
# ─────────────────────────────────────────────────────────────────────────────

class _InstancesWindow(ctk.CTkToplevel):
    """Shows run instances for a specific report."""

    _COLS = [
        ('status',   'Status',   80,  False),
        ('started',  'Started',  155, False),
        ('ended',    'Ended',    155, False),
        ('owner',    'Owner',    110, False),
        ('fmt',      'Format',    80, False),
    ]

    def __init__(self, parent, report):
        super().__init__(parent)
        self._report = report
        self.title(f'📋  Instances — {report["name"][:50]}')
        self.geometry('760x440')
        self.configure(fg_color=C['bg_primary'])
        self._build_ui()
        threading.Thread(target=self._load, daemon=True).start()

    def _build_ui(self):
        hdr = ctk.CTkFrame(self, fg_color=C['bg_secondary'],
                           corner_radius=0, height=46)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=f'📋  {self._report["name"]}  — Run Instances',
                     font=('Segoe UI', 12, 'bold'),
                     text_color=C['text_primary']).pack(side='left', padx=14)
        self._status_lbl = ctk.CTkLabel(hdr, text='⏳ Loading…',
                                        font=('Segoe UI', 10),
                                        text_color=C['text_secondary'])
        self._status_lbl.pack(side='right', padx=14)

        tv_frame = ctk.CTkFrame(self, fg_color=C['bg_secondary'], corner_radius=8)
        tv_frame.pack(fill='both', expand=True, padx=10, pady=10)

        sn = f'INS{id(self)}'
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
        self._tv.tag_configure('success', foreground='#10B981')
        self._tv.tag_configure('failed',  foreground='#EF4444')
        self._tv.tag_configure('running', foreground='#F59E0B')

        vsb = ctk.CTkScrollbar(tv_frame, orientation='vertical', command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        self._tv.pack(fill='both', expand=True, padx=6, pady=6)

    def _load(self):
        instances = bo_session.get_report_instances(self._report['id'])
        if hasattr(self, '_tv'):
            self.after(0, lambda i=instances: self._render(i))

    def _render(self, instances):
        for row in self._tv.get_children():
            self._tv.delete(row)
        for inst in (instances or []):
            st  = inst.get('status', 'unknown').lower()
            tag = ('success' if 'success' in st
                   else 'failed' if 'fail' in st
                   else 'running' if 'run' in st
                   else '')
            status_icon = {'success': '✅', 'fail': '❌', 'run': '⏳'}.get(
                next((k for k in ('success','fail','run') if k in st), ''), '⬜')
            self._tv.insert('', 'end', tags=(tag,),
                            values=(f'{status_icon} {inst.get("status","?")}',
                                    inst.get('start_time', ''),
                                    inst.get('end_time', ''),
                                    inst.get('owner', ''),
                                    inst.get('format', '')))
        n = len(instances or [])
        self._status_lbl.configure(text=f'{n} instance{"s" if n != 1 else ""}')


# ─────────────────────────────────────────────────────────────────────────────
#  Main Report Viewer Page
# ─────────────────────────────────────────────────────────────────────────────

class ReportViewerPage(ctk.CTkFrame):

    _COLS = [
        ('type_dot', '●',           28,  False),
        ('icon',     '',            28,  False),
        ('name',     'Report Name', 260, True),
        ('kind',     'Type',        110, False),
        ('owner',    'Owner',       100, False),
        ('folder',   'Folder',      130, False),
        ('last_run', 'Last Run',    135, False),
    ]

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0, **kw)
        _ROOT[0] = self.winfo_toplevel()
        self._all_reports = []
        self._destroyed   = False
        self._active_type = 'All'
        self._build_ui()
        threading.Thread(target=self._load, daemon=True).start()

    def destroy(self):
        self._destroyed = True
        super().destroy()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color='transparent', height=56)
        hdr.pack(fill='x', padx=16, pady=(14, 0))
        hdr.pack_propagate(False)

        ctk.CTkLabel(hdr, text='📊  Report Viewer',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')

        ctk.CTkButton(hdr, text='🔄 Refresh', width=88, height=34,
                      fg_color=C['bg_tertiary'], text_color=C['text_primary'],
                      command=lambda: threading.Thread(
                          target=self._load, daemon=True).start()
                      ).pack(side='right')

        # ── Capability legend ─────────────────────────────────────────────────
        legend = ctk.CTkFrame(self, fg_color=C['bg_secondary'],
                              corner_radius=8, height=42)
        legend.pack(fill='x', padx=16, pady=(6, 4))
        legend.pack_propagate(False)

        for icon, label, color in [
            ('📊', 'WebI — Full REST: Run · Export · Schedule',         '#3B82F6'),
            ('💎', 'Crystal — Open in Launchpad · Export · Schedule',    '#8B5CF6'),
            ('📗', 'AO/Excel — Download · Schedule',                     '#10B981'),
        ]:
            ctk.CTkLabel(legend, text=f'{icon} {label}',
                         font=('Segoe UI', 9),
                         text_color=color).pack(side='left', padx=14)

        # ── Type filter tabs ──────────────────────────────────────────────────
        tabs = ctk.CTkFrame(self, fg_color='transparent', height=38)
        tabs.pack(fill='x', padx=16, pady=(0, 4))
        tabs.pack_propagate(False)

        self._tab_btns = {}
        tab_defs = [
            ('All',           '📋', '#3B82F6'),
            ('Webi',          '📊', '#3B82F6'),
            ('CrystalReport', '💎', '#8B5CF6'),
            ('Excel',         '📗', '#10B981'),
            ('Pdf',           '📄', '#EF4444'),
        ]
        for tid, icon, color in tab_defs:
            label = 'All' if tid == 'All' else _type_meta(tid)['short']
            btn = ctk.CTkButton(tabs, text=f'{icon} {label}',
                                height=28, width=110, corner_radius=6,
                                fg_color=color if tid == 'All' else C['bg_tertiary'],
                                hover_color=color,
                                text_color='white',
                                font=('Segoe UI', 10),
                                command=lambda t=tid, c=color: self._set_type(t, c))
            btn.pack(side='left', padx=3)
            self._tab_btns[tid] = (btn, color)

        # ── Summary cards ─────────────────────────────────────────────────────
        cards = ctk.CTkFrame(self, fg_color='transparent', height=72)
        cards.pack(fill='x', padx=16, pady=(0, 6))
        cards.pack_propagate(False)
        self._card_lbls = {}
        for key, label, color in [
            ('total',   'Total Reports', '#3B82F6'),
            ('webi',    'WebI',          '#3B82F6'),
            ('crystal', 'Crystal',       '#8B5CF6'),
            ('ao',      'AO / Excel',    '#10B981'),
            ('other',   'Other',         '#64748B'),
        ]:
            card = ctk.CTkFrame(cards, fg_color=C['bg_secondary'], corner_radius=8)
            card.pack(side='left', padx=(0, 6), fill='both', expand=True)
            ctk.CTkLabel(card, text=label, font=('Segoe UI', 9),
                         text_color=C['text_secondary']).pack(pady=(6, 0))
            lbl = ctk.CTkLabel(card, text='—',
                               font=('Segoe UI', 18, 'bold'),
                               text_color=color)
            lbl.pack(pady=(0, 6))
            self._card_lbls[key] = lbl

        # ── Search bar ────────────────────────────────────────────────────────
        sbar = ctk.CTkFrame(self, fg_color='transparent', height=34)
        sbar.pack(fill='x', padx=16, pady=(0, 4))
        sbar.pack_propagate(False)

        self._q_var = ctk.StringVar()
        self._q_var.trace_add('write', lambda *_: self._render())
        ctk.CTkEntry(sbar, textvariable=self._q_var,
                     placeholder_text='🔎  Search by name, owner…',
                     width=300, height=30,
                     fg_color=C['bg_secondary'],
                     border_color=C['bg_tertiary'],
                     text_color=C['text_primary'],
                     font=('Segoe UI', 11)).pack(side='left')

        self._status_lbl = ctk.CTkLabel(sbar, text='',
                                        font=('Segoe UI', 10),
                                        text_color=C['text_secondary'])
        self._status_lbl.pack(side='right')

        # ── Main split: list (left) + detail (right) ──────────────────────────
        body = ctk.CTkFrame(self, fg_color='transparent')
        body.pack(fill='both', expand=True, padx=16, pady=(0, 14))

        # Left: treeview
        left = ctk.CTkFrame(body, fg_color='transparent')
        left.pack(side='left', fill='both', expand=True)

        tv_outer = ctk.CTkFrame(left, fg_color=C['bg_secondary'], corner_radius=8)
        tv_outer.pack(fill='both', expand=True)

        sn = f'RV{id(self)}.TV'
        s = ttk.Style()
        s.configure(sn, background=C['bg_secondary'], foreground=C['text_primary'],
                    fieldbackground=C['bg_secondary'], rowheight=32,
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
            self._tv.column(cid, width=w, minwidth=20, stretch=st)

        self._tv.tag_configure('webi',    foreground='#60A5FA')
        self._tv.tag_configure('crystal', foreground='#A78BFA')
        self._tv.tag_configure('ao',      foreground='#34D399')
        self._tv.tag_configure('other',   foreground='#9AA0B4')

        vsb = ctk.CTkScrollbar(tv_outer, orientation='vertical', command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y', padx=(0, 4), pady=8)
        self._tv.pack(fill='both', expand=True, padx=8, pady=8)
        self._tv.bind('<<TreeviewSelect>>', self._on_select)
        self._tv.bind('<Double-1>', self._on_double_click)

        # Right: detail panel
        self._detail = _DetailPanel(body,
                                    on_status=lambda m: self._status_lbl.configure(text=m),
                                    width=280)
        self._detail.pack(side='right', fill='y', padx=(8, 0))

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load(self):
        self.after(0, lambda: self._status_lbl.configure(
            text='⏳ Loading reports…'))
        reports = bo_session.get_all_reports_typed()
        if not self._destroyed:
            self.after(0, lambda r=reports: self._on_loaded(r))

    def _on_loaded(self, reports):
        self._all_reports = reports or []
        self._render()
        self._update_cards()

    def _set_type(self, type_id, color):
        self._active_type = type_id
        for tid, (btn, col) in self._tab_btns.items():
            btn.configure(fg_color=col if tid == type_id else C['bg_tertiary'])
        self._render()

    def _render(self):
        q     = self._q_var.get().lower()
        ftype = self._active_type

        shown = []
        for r in self._all_reports:
            kind = r.get('kind', '')
            if ftype != 'All' and kind != ftype:
                continue
            if q and q not in r.get('name', '').lower() \
                  and q not in r.get('owner', '').lower():
                continue
            shown.append(r)

        for row in self._tv.get_children():
            self._tv.delete(row)

        for r in shown:
            kind = r.get('kind', '')
            meta = _type_meta(kind)
            tag  = ('webi' if kind == 'Webi'
                    else 'crystal' if kind == 'CrystalReport'
                    else 'ao' if kind == 'Excel'
                    else 'other')
            self._tv.insert('', 'end', iid=str(r['id']), tags=(tag,),
                            values=('●', meta['icon'],
                                    r.get('name', ''),
                                    meta['short'],
                                    r.get('owner', ''),
                                    r.get('folder', ''),
                                    r.get('last_run', '')))

        self._status_lbl.configure(
            text=f'{len(self._all_reports)} reports  |  showing {len(shown)}')

    def _update_cards(self):
        kinds = [r.get('kind', '') for r in self._all_reports]
        self._card_lbls['total'].configure(text=str(len(self._all_reports)))
        self._card_lbls['webi'].configure(text=str(kinds.count('Webi')))
        self._card_lbls['crystal'].configure(text=str(kinds.count('CrystalReport')))
        self._card_lbls['ao'].configure(text=str(kinds.count('Excel')))
        other = sum(1 for k in kinds if k not in ('Webi', 'CrystalReport', 'Excel'))
        self._card_lbls['other'].configure(text=str(other))

    # ── Selection ─────────────────────────────────────────────────────────────

    def _on_select(self, event=None):
        sel = self._tv.selection()
        if not sel: return
        rid  = sel[0]
        report = next((r for r in self._all_reports if str(r['id']) == rid), None)
        if report:
            self._detail.load(report)

    def _on_double_click(self, event=None):
        sel = self._tv.selection()
        if not sel: return
        rid    = sel[0]
        report = next((r for r in self._all_reports if str(r['id']) == rid), None)
        if not report: return
        kind = report.get('kind', '')
        if kind == 'Webi':
            self._detail._run_webi()
        else:
            self._detail._open_browser()
