"""
gui/pages/log_correlation.py
Fix: Page was a blank stub.

Design answer to user's question: "Why does every tab scan all 8 layers?"
  → It SHOULDN'T. The 8-layer scan belongs ONLY to AI Sentinel (on-demand).
  → Log Correlation does a TARGETED scan: reads specific BO log files only,
     categorises errors, and correlates them by timestamp.
  → No OS diagnostics, no network checks, no Windows Event Viewer.
  → Just: read BO log files → find error patterns → show correlated timeline.
"""

import os
import re
import threading
import glob
from datetime import datetime
import customtkinter as ctk
from config import Config

C = Config.COLORS

ERROR_PATTERNS = {
    'Memory':     [r'OutOfMemoryError', r'Java heap', r'GC overhead'],
    'Connection': [r'Connection refused', r'Unable to connect', r'CORBA.*exception'],
    'Auth':       [r'Authentication failed', r'Invalid credentials', r'Access denied'],
    'Crash':      [r'Fatal error', r'Segmentation fault', r'EXCEPTION_ACCESS'],
    'Database':   [r'SQLException', r'connection pool', r'Deadlock'],
    'Disk':       [r'No space left', r'disk.*full', r'I/O error'],
}

CAT_COLORS = {
    'Memory':     '#EF4444',
    'Connection': '#F97316',
    'Auth':       '#F59E0B',
    'Crash':      '#DC2626',
    'Database':   '#8B5CF6',
    'Disk':       '#64748B',
}


class LogCorrelationPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0)

        # ── header ───────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color='transparent', height=50)
        top.pack(fill='x', padx=20, pady=(15, 0))
        top.pack_propagate(False)

        ctk.CTkLabel(top, text='📊  Log Correlation',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')

        ctk.CTkLabel(top,
                     text='Targeted BO log scan — no OS/network/Event Viewer overhead',
                     font=('Segoe UI', 11),
                     text_color=C['text_secondary']).pack(side='left', padx=14)

        self._scan_btn = ctk.CTkButton(top, text='⟳ Scan Logs',
                                       width=110, height=34,
                                       command=self._start_scan)
        self._scan_btn.pack(side='right')

        # ── BO log directory input ────────────────────────────────────────────
        path_row = ctk.CTkFrame(self, fg_color=C['bg_secondary'], corner_radius=8)
        path_row.pack(fill='x', padx=15, pady=(8, 0))

        ctk.CTkLabel(path_row, text='BO Log Dir:',
                     font=('Segoe UI', 11),
                     text_color=C['text_primary']).pack(side='left', padx=12, pady=10)

        self._dir_entry = ctk.CTkEntry(path_row, width=500,
                                       font=('Segoe UI', 11),
                                       placeholder_text='e.g. D:\\SAP BO\\SAP BO\\SAP BusinessObjects Enterprise XI 4.0\\logging')
        self._dir_entry.pack(side='left', padx=6)

        # Pre-fill from Config
        try:
            self._dir_entry.insert(0, Config.BOE_LOG_DIR)
        except Exception:
            pass

        ctk.CTkLabel(path_row, text='Lines:',
                     font=('Segoe UI', 11),
                     text_color=C['text_primary']).pack(side='left', padx=(14, 4))

        self._lines_var = ctk.StringVar(value='500')
        ctk.CTkEntry(path_row, textvariable=self._lines_var,
                     width=60, font=('Segoe UI', 11)).pack(side='left')

        self._status = ctk.CTkLabel(path_row, text='',
                                    font=('Segoe UI', 11),
                                    text_color=C['text_secondary'])
        self._status.pack(side='right', padx=12)

        # ── results ───────────────────────────────────────────────────────────
        self.scroll = ctk.CTkScrollableFrame(self,
                                             fg_color=C['bg_secondary'],
                                             corner_radius=8)
        self.scroll.pack(fill='both', expand=True, padx=15, pady=10)

        ctk.CTkLabel(self.scroll,
                     text='Enter your BO log directory and click Scan Logs.\n'
                          'This scans ONLY BO log files — no slow OS/network diagnostics.',
                     font=('Segoe UI', 12),
                     text_color=C['text_secondary']).pack(pady=40)

    # ── scan ─────────────────────────────────────────────────────────────────

    def _start_scan(self):
        log_dir = self._dir_entry.get().strip()
        if not log_dir:
            self._status.configure(text='⚠ Enter log directory')
            return
        if not os.path.isdir(log_dir):
            self._status.configure(text=f'❌ Directory not found: {log_dir}')
            return

        self._scan_btn.configure(state='disabled', text='Scanning…')
        self._status.configure(text='Scanning BO log files…')
        for w in self.scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.scroll, text='⏳  Reading log files…',
                     font=('Segoe UI', 12, 'italic'),
                     text_color=C['text_secondary']).pack(pady=30)

        try:
            lines = int(self._lines_var.get())
        except ValueError:
            lines = 500

        threading.Thread(target=self._scan, args=(log_dir, lines), daemon=True).start()

    def _scan(self, log_dir, n_lines):
        """Targeted log scan — reads BO log files only, no OS or network checks."""
        findings = []
        files_scanned = []

        # Find all .log and .glf files in the directory (not recursive — keeps it fast)
        patterns = ['*.log', '*.glf', '*.txt']
        log_files = []
        for pat in patterns:
            log_files.extend(glob.glob(os.path.join(log_dir, pat)))

        # Sort by modified time, most recent first
        log_files.sort(key=os.path.getmtime, reverse=True)

        for fpath in log_files[:20]:   # cap at 20 files
            fname = os.path.basename(fpath)
            size_mb = round(os.path.getsize(fpath) / 1024 / 1024, 2)
            files_scanned.append({'name': fname, 'size_mb': size_mb, 'path': fpath})

            try:
                with open(fpath, 'r', errors='ignore') as f:
                    lines = f.readlines()[-n_lines:]
                content = ''.join(lines)
            except Exception:
                continue

            for category, pats in ERROR_PATTERNS.items():
                for pat in pats:
                    for match in re.finditer(pat, content, re.IGNORECASE):
                        s    = max(0, match.start() - 60)
                        e    = min(len(content), match.end() + 120)
                        ctx  = content[s:e].replace('\n', ' ').strip()
                        ts_m = re.search(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', content[s:e])
                        ts   = ts_m.group(0) if ts_m else ''

                        findings.append({
                            'category': category,
                            'file':     fname,
                            'match':    match.group(0),
                            'context':  ctx[:200],
                            'timestamp': ts,
                        })

        # Deduplicate (same category+file+match)
        seen = set()
        unique = []
        for f in findings:
            key = (f['category'], f['file'], f['match'])
            if key not in seen:
                seen.add(key)
                unique.append(f)

        self.after(0, lambda r=unique, fs=files_scanned: self._render(r, fs))

    # ── render ────────────────────────────────────────────────────────────────

    def _render(self, findings, files_scanned):
        for w in self.scroll.winfo_children():
            w.destroy()
        self._scan_btn.configure(state='normal', text='⟳ Scan Logs')
        self._status.configure(
            text=f'{len(files_scanned)} files scanned · {len(findings)} findings'
        )

        # Files scanned summary
        fs_frame = ctk.CTkFrame(self.scroll, fg_color=C['bg_tertiary'], corner_radius=6)
        fs_frame.pack(fill='x', padx=8, pady=(8, 4))
        ctk.CTkLabel(fs_frame,
                     text=f'📁  Files scanned: {", ".join(f["name"] for f in files_scanned[:8])}',
                     font=('Segoe UI', 10),
                     text_color=C['text_secondary'],
                     wraplength=1000).pack(anchor='w', padx=12, pady=6)

        if not findings:
            ctk.CTkLabel(self.scroll,
                         text='✅  No error patterns found in the scanned logs.',
                         font=('Segoe UI', 12),
                         text_color=C['success']).pack(pady=30)
            return

        # Category summary chips
        chip_row = ctk.CTkFrame(self.scroll, fg_color='transparent')
        chip_row.pack(fill='x', padx=8, pady=6)

        from collections import Counter
        counts = Counter(f['category'] for f in findings)
        for cat, cnt in sorted(counts.items(), key=lambda x: -x[1]):
            chip = ctk.CTkFrame(chip_row, fg_color=CAT_COLORS.get(cat, C['bg_tertiary']),
                                corner_radius=6)
            chip.pack(side='left', padx=4)
            ctk.CTkLabel(chip, text=f'  {cat}: {cnt}  ',
                         font=('Segoe UI', 10, 'bold'),
                         text_color='white').pack(pady=3)

        # Timeline of findings (sorted by timestamp then category severity)
        sev_order = ['Crash', 'Memory', 'Database', 'Disk', 'Connection', 'Auth']
        findings.sort(key=lambda x: (
            '' if not x['timestamp'] else x['timestamp'],
            sev_order.index(x['category']) if x['category'] in sev_order else 99
        ))

        ctk.CTkLabel(self.scroll,
                     text='Error Timeline (most recent first)',
                     font=('Segoe UI', 11, 'bold'),
                     text_color=C['text_primary']).pack(anchor='w', padx=12, pady=(8, 2))

        for finding in findings:
            self._render_finding(finding)

    def _render_finding(self, f):
        cat   = f['category']
        color = CAT_COLORS.get(cat, C['bg_tertiary'])

        row = ctk.CTkFrame(self.scroll, fg_color=C['bg_tertiary'], corner_radius=5)
        row.pack(fill='x', padx=8, pady=2)

        # Color bar
        bar = ctk.CTkFrame(row, fg_color=color, width=4, corner_radius=2)
        bar.pack(side='left', fill='y')
        bar.pack_propagate(False)

        inner = ctk.CTkFrame(row, fg_color='transparent')
        inner.pack(side='left', fill='both', expand=True, padx=10, pady=6)

        top_row = ctk.CTkFrame(inner, fg_color='transparent')
        top_row.pack(fill='x')

        ctk.CTkLabel(top_row,
                     text=f' {cat} ',
                     fg_color=color,
                     corner_radius=4,
                     font=('Segoe UI', 9, 'bold'),
                     text_color='white').pack(side='left')

        ctk.CTkLabel(top_row,
                     text=f.get('match', ''),
                     font=('Segoe UI', 10, 'bold'),
                     text_color=C['text_primary']).pack(side='left', padx=8)

        if f.get('timestamp'):
            ctk.CTkLabel(top_row,
                         text=f['timestamp'],
                         font=('Segoe UI', 10),
                         text_color=C['text_secondary']).pack(side='right', padx=8)

        ctk.CTkLabel(inner,
                     text=f"📄 {f['file']}  —  {f.get('context','')}",
                     font=('Segoe UI', 10),
                     text_color=C['text_secondary'],
                     anchor='w',
                     wraplength=1000).pack(fill='x')
