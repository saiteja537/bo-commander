"""
gui/tabs/tab_logs.py  —  Logs & Diagnostics  (Fixed)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FIXES:
  FIX-1  "No log files found" — auto-scans ALL candidate BO log directories,
          no longer depends on one hardcoded path being correct.
  FIX-2  📁 Browse Path button — pick any dir or .log file; saves to .env
          immediately so it persists across restarts.
  FIX-3  Shows WHICH dirs were scanned in the status bar so user knows what
          is happening.
  FIX-4  Groups files by folder in the sidebar.
  FIX-5  Error/Warn/Info lines colour-coded in the viewer.
  FIX-6  Live search with highlight + jump-to-next.
  FIX-7  AI analysis persisted to KnowledgeBase if available.

Drop-in replacement for:  gui/tabs/tab_logs.py
No other files need to change.
"""

import os
import re
import glob
import platform
import threading
import tkinter.filedialog as _fd
from datetime import datetime
from pathlib import Path

from gui.tabs._base import *

_IS_WIN = platform.system() == "Windows"


# ─────────────────────────────────────────────────────────────────────────────
# Path detection helpers
# ─────────────────────────────────────────────────────────────────────────────

def _candidate_dirs() -> list:
    """
    Build a list of every possible BO log directory that could exist on this
    machine.  Returns only directories that actually exist right now.
    """
    from config import Config

    candidates = []

    # ── 1. Config-derived paths (highest priority) ────────────────────────────
    for attr in ("BOE_LOG_DIR", "BOE_TOMCAT_DIR", "BOE_WDEPLOY_LOGS",
                 "BOE_INSTALL_LOGS", "BO_LOG_DIR"):
        v = getattr(Config, attr, None) or os.environ.get(attr, "")
        if v:
            p = Path(v)
            candidates.append(str(p if p.is_dir() else p.parent))

    # EXTRA_LOG_DIRS from .env: semicolon-separated list
    for extra in getattr(Config, "EXTRA_LOG_DIRS", []):
        if extra:
            candidates.append(extra)

    # ── 2. Windows standard install root + common sub-paths ──────────────────
    if _IS_WIN:
        install_root = getattr(Config, "BOE_INSTALL_DIR",
                                r"D:\SAP BO\SAP BO")
        win_roots = [
            install_root,
            r"C:\Program Files (x86)\SAP BusinessObjects",
            r"C:\Program Files\SAP BusinessObjects",
            r"D:\SAP BusinessObjects",
            r"C:\SAP",
        ]
        sub_paths = [
            r"SAP BusinessObjects Enterprise XI 4.0\logging",
            r"SAP BusinessObjects\logging",
            r"logging",
            r"tomcat\logs",
            r"SAP BusinessObjects\Tomcat\logs",
            r"SAP BusinessObjects Enterprise XI 4.0\wdeploy",
            r"InstallData\logs",
        ]
        for root in win_roots:
            for sub in sub_paths:
                candidates.append(os.path.join(root, sub))
            candidates.append(root)

        # ProgramData
        app_data = os.environ.get("ALLUSERSPROFILE", r"C:\ProgramData")
        candidates.append(
            os.path.join(app_data, "SAP", "SAP BusinessObjects", "Logging"))
        candidates.append(
            os.path.join(app_data, "Business Objects",
                         "BusinessObjects 12.0", "Logging"))
    else:
        # Linux
        candidates.extend([
            "/opt/sap/BO/sap_bobj/logging",
            "/opt/sap/BusinessObjects/logging",
            "/opt/BOE/sap_bobj/logging",
            "/var/log/sap",
        ])

    # Deduplicate and keep only real dirs
    seen, result = set(), []
    for p in candidates:
        p = str(p).strip()
        if p and p not in seen and os.path.isdir(p):
            seen.add(p)
            result.append(p)
    return result


def _scan_dirs(directories: list) -> list:
    """
    Walk each directory for BO log files.
    Returns sorted list of dicts: {name, path, size_kb, modified, dir}.
    Error/warn-named files sorted to top.
    """
    exts = {".log", ".txt", ".out", ".trace", ".trc", ".err", ".log1", ".log2"}
    found = {}
    for d in directories:
        try:
            for root, dirs, files in os.walk(d):
                dirs[:] = [x for x in dirs if not x.startswith(".")]
                for f in files:
                    if Path(f).suffix.lower() in exts:
                        full = os.path.join(root, f)
                        if full not in found:
                            try:
                                st = os.stat(full)
                                found[full] = {
                                    "name":     f,
                                    "path":     full,
                                    "size_kb":  round(st.st_size / 1024, 1),
                                    "modified": datetime.fromtimestamp(
                                        st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                                    "dir":      root,
                                }
                            except OSError:
                                pass
        except PermissionError:
            pass

    def _sort_key(x):
        nm = x["name"].lower()
        is_err = ("error" in nm or "err." in nm or nm.endswith(".err"))
        return (0 if is_err else 1, x["modified"])

    return sorted(found.values(), key=_sort_key)


def _tail(path: str, lines: int) -> str:
    """Efficiently read last N lines from potentially large log file."""
    try:
        size = os.path.getsize(path)
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            if size < 8 * 1024 * 1024:          # < 8 MB → read all
                all_lines = fh.readlines()
            else:                                 # large file → seek near end
                fh.seek(max(0, size - lines * 250))
                fh.readline()                     # skip partial first line
                all_lines = fh.readlines()
        return "".join(all_lines[-lines:])
    except Exception as e:
        return f"[Error reading file: {e}]"


# ─────────────────────────────────────────────────────────────────────────────
# Tab
# ─────────────────────────────────────────────────────────────────────────────

class LogsTab(BaseTab):
    """
    Logs & Diagnostics tab.

    Auto-scans every candidate BO log directory on startup.
    If nothing is found, the user can click 📁 Browse Path to point at any dir
    or file — the choice is saved to .env immediately.
    """

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._log_dirs:       list = []
        self._log_files:      list = []
        self._selected:       dict | None = None
        self._current_content = ""
        self._lines_var       = ctk.StringVar(value="300")
        self._search_var      = ctk.StringVar()
        self._search_var.trace_add("write", self._on_search_change)
        self._build()
        self._initial_scan()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        # Header
        rf = self._page_header("Logs & Diagnostics", "📋",
                                "Browse BO log files, search errors, AI analysis")

        # Header action buttons (right → left)
        ctk.CTkButton(rf, text="🤖 AI Analyse", width=110, height=30,
                      fg_color=VIOLET, text_color="white", font=F_SM,
                      command=self._ai_analyse).pack(side="right", padx=3)

        ctk.CTkButton(rf, text="📁 Browse Path", width=115, height=30,
                      fg_color=AMBER, text_color=BG0, font=F_SM,
                      command=self._browse_path).pack(side="right", padx=3)

        ctk.CTkButton(rf, text="⟳ Refresh", width=90, height=30,
                      fg_color=BG2, text_color=TEXT, font=F_SM,
                      command=self._initial_scan).pack(side="right", padx=3)

        # Body split
        body = self._body
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # ── LEFT sidebar ──────────────────────────────────────────────────────
        sidebar = ctk.CTkFrame(body, fg_color=BG1, corner_radius=10, width=240)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(14, 4), pady=10)
        sidebar.grid_propagate(False)

        sidebar_top = ctk.CTkFrame(sidebar, fg_color="transparent")
        sidebar_top.pack(fill="x", padx=10, pady=(10, 4))
        ctk.CTkLabel(sidebar_top, text="📁  Log Files",
                     font=F_H3, text_color=CYAN).pack(side="left")

        # Scanned dirs label
        self._dirs_lbl = ctk.CTkLabel(sidebar, text="Scanning…",
                                       font=("Segoe UI", 8), text_color=TEXT2,
                                       wraplength=215, justify="left")
        self._dirs_lbl.pack(anchor="w", padx=12, pady=(0, 4))

        ctk.CTkFrame(sidebar, fg_color=BG2, height=1).pack(fill="x", padx=6)

        self._file_list = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
        self._file_list.pack(fill="both", expand=True, padx=2, pady=2)

        # ── RIGHT viewer ──────────────────────────────────────────────────────
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 14), pady=10)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        # Search / lines bar
        sbar = ctk.CTkFrame(right, fg_color=BG1, corner_radius=8, height=42)
        sbar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        sbar.pack_propagate(False)
        sbar.grid_columnconfigure(0, weight=1)

        ctk.CTkEntry(sbar, textvariable=self._search_var,
                     placeholder_text="🔎  Search in log (live highlight)…",
                     fg_color=BG2, border_color=BG2, text_color=TEXT,
                     font=F_SM, height=30
                     ).pack(side="left", fill="x", expand=True, padx=8, pady=6)

        ctk.CTkButton(sbar, text="Find ↓", width=70, height=28,
                      fg_color=BLUE, text_color="white", font=F_SM,
                      command=self._jump_next).pack(side="right", padx=4, pady=6)

        ctk.CTkOptionMenu(sbar, variable=self._lines_var,
                           values=["100", "200", "300", "500", "1000", "2000"],
                           width=80, height=28,
                           fg_color=BG2, button_color=BG2,
                           dropdown_fg_color=BG1, text_color=TEXT, font=F_SM,
                           command=lambda _: self._reload()
                           ).pack(side="right", padx=4, pady=6)
        ctk.CTkLabel(sbar, text="Lines:", font=F_XS, text_color=TEXT2
                     ).pack(side="right")

        # Log viewer
        self._log_viewer = ctk.CTkTextbox(right, fg_color=BG0,
                                           text_color=TEXT, font=F_MONO,
                                           wrap="none", corner_radius=8)
        self._log_viewer.grid(row=1, column=0, sticky="nsew")
        self._log_viewer.configure(state="disabled")

        # AI output strip (hidden until AI runs)
        self._ai_frame = ctk.CTkFrame(right, fg_color=BG1, corner_radius=8)
        self._ai_frame.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self._ai_frame.grid_remove()   # hidden by default
        self._ai_lbl = ctk.CTkLabel(self._ai_frame, text="",
                                     font=F_SM, text_color=VIOLET,
                                     wraplength=860, justify="left", anchor="w")
        self._ai_lbl.pack(padx=12, pady=8, fill="x")

    # ── Scan ─────────────────────────────────────────────────────────────────

    def _initial_scan(self):
        self.set_status("⏳ Scanning for BO log files…", AMBER)
        self._dirs_lbl.configure(text="Scanning…")
        for w in self._file_list.winfo_children():
            w.destroy()

        def _run():
            dirs  = _candidate_dirs()
            files = _scan_dirs(dirs)
            return dirs, files

        def _done(result):
            dirs, files = result
            self._log_dirs  = dirs
            self._log_files = files
            self._populate_sidebar()
            n = len(files)
            if n:
                # Show abbreviated dir list
                short = [os.path.basename(d) or d for d in dirs[:3]]
                extra = f" +{len(dirs)-3} more" if len(dirs) > 3 else ""
                self._dirs_lbl.configure(
                    text="Scanned: " + ", ".join(short) + extra)
                self.set_status(
                    f"✅ {n} log file(s) in {len(dirs)} director(ies)"
                    f"  —  select a file to view", GREEN)
            else:
                self._dirs_lbl.configure(
                    text="No BO log dirs found.\nClick '📁 Browse Path' ↑")
                self.set_status(
                    "⚠  No log files found — click '📁 Browse Path' to "
                    "select your SAP BO log directory", AMBER)
                self._show_no_files_hint()

        bg(_run, _done, self)

    def _show_no_files_hint(self):
        for w in self._file_list.winfo_children():
            w.destroy()
        hint = (
            "No log files found.\n\n"
            "Click  📁 Browse Path  ↑\n"
            "to select your BO log folder.\n\n"
            "Typical paths:\n"
            "D:\\SAP BO\\SAP BO\\\n"
            "  SAP BusinessObjects Enterprise\n"
            "  XI 4.0\\logging\\\n\n"
            "or\n\n"
            "D:\\SAP BO\\SAP BO\\\n"
            "  tomcat\\logs\\"
        )
        ctk.CTkLabel(self._file_list, text=hint,
                     font=("Segoe UI", 9), text_color=TEXT2,
                     justify="left").pack(anchor="w", padx=10, pady=8)

    def _populate_sidebar(self):
        for w in self._file_list.winfo_children():
            w.destroy()

        if not self._log_files:
            self._show_no_files_hint()
            return

        # Group by directory
        groups: dict = {}
        for f in self._log_files:
            groups.setdefault(f["dir"], []).append(f)

        for dir_path, files in groups.items():
            dir_name = os.path.basename(dir_path) or dir_path
            ctk.CTkLabel(self._file_list,
                         text=f"📂 {dir_name}",
                         font=("Segoe UI", 8, "bold"),
                         text_color=TEAL, anchor="w"
                         ).pack(fill="x", padx=6, pady=(8, 2))

            for fi in files:
                nm     = fi["name"]
                is_err = ("error" in nm.lower() or "err." in nm.lower()
                          or nm.lower().endswith(".err"))
                col    = RED if is_err else TEXT2

                btn = ctk.CTkButton(
                    self._file_list,
                    text=f"  {nm}\n  {fi['size_kb']} KB",
                    height=42, anchor="w",
                    font=("Segoe UI", 8),
                    fg_color="transparent", hover_color=BG2,
                    text_color=col, corner_radius=4,
                    command=lambda fi=fi: self._load_file(fi))
                btn.pack(fill="x", padx=2, pady=1)

        # Auto-open first file
        if self._log_files:
            self._load_file(self._log_files[0])

    # ── Browse ───────────────────────────────────────────────────────────────

    def _browse_path(self):
        """Let user pick a directory or a single file, then rescan."""
        # Ask: directory or file?
        choice_win = ctk.CTkToplevel(self)
        choice_win.title("Select Log Source")
        choice_win.geometry("340x160")
        choice_win.configure(fg_color=BG0)
        choice_win.grab_set()

        ctk.CTkLabel(choice_win, text="What do you want to open?",
                     font=F_H3, text_color=TEXT).pack(pady=(20, 10))

        btn_row = ctk.CTkFrame(choice_win, fg_color="transparent")
        btn_row.pack()

        def _pick_dir():
            choice_win.destroy()
            path = _fd.askdirectory(title="Select BO Log Directory",
                                     parent=self)
            if path and os.path.isdir(path):
                self._add_custom_dir(path)

        def _pick_file():
            choice_win.destroy()
            path = _fd.askopenfilename(
                title="Select Log File",
                parent=self,
                filetypes=[("Log files", "*.log *.txt *.out *.trc *.err"),
                            ("All files", "*.*")])
            if path and os.path.isfile(path):
                self._add_custom_file(path)

        ctk.CTkButton(btn_row, text="📂 Browse Folder", width=140, height=34,
                      fg_color=BLUE, command=_pick_dir).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="📄 Browse File", width=130, height=34,
                      fg_color=BG2, text_color=TEXT,
                      command=_pick_file).pack(side="left", padx=6)

    def _add_custom_dir(self, path: str):
        """Add a manually selected directory, save to .env, rescan."""
        self.set_status(f"⏳ Scanning {path}…", AMBER)
        # Insert at front (highest priority)
        self._log_dirs = [path] + [d for d in self._log_dirs if d != path]

        def _run():
            return _scan_dirs(self._log_dirs)

        def _done(files):
            self._log_files = files
            self._populate_sidebar()
            self._dirs_lbl.configure(text=f"Custom: {os.path.basename(path)}")
            self.set_status(
                f"✅ {len(files)} file(s) found  —  "
                f"path saved to .env", GREEN)

        bg(_run, _done, self)
        self._save_log_dir_to_env(path)

    def _add_custom_file(self, path: str):
        """Load a single manually selected log file directly."""
        fi = {
            "name":     os.path.basename(path),
            "path":     path,
            "size_kb":  round(os.path.getsize(path) / 1024, 1),
            "modified": datetime.fromtimestamp(
                os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M"),
            "dir":      os.path.dirname(path),
        }
        # Prepend to list
        self._log_files = [fi] + [f for f in self._log_files
                                   if f["path"] != path]
        self._populate_sidebar()
        self._load_file(fi)

    def _save_log_dir_to_env(self, path: str):
        """Persist the chosen path to .env so it survives restarts."""
        try:
            env_path = Path(".env")
            txt = env_path.read_text("utf-8") if env_path.exists() else ""

            # Update BOE_INSTALL_DIR if path looks like a BO install root
            if "SAP BO" in path or "BusinessObjects" in path:
                # Save as EXTRA_LOG_DIRS to not break existing BOE_INSTALL_DIR
                if "EXTRA_LOG_DIRS=" in txt:
                    txt = re.sub(r"EXTRA_LOG_DIRS=.*",
                                 f"EXTRA_LOG_DIRS={path}", txt)
                else:
                    txt += f"\nEXTRA_LOG_DIRS={path}\n"
            else:
                if "EXTRA_LOG_DIRS=" in txt:
                    txt = re.sub(r"EXTRA_LOG_DIRS=.*",
                                 f"EXTRA_LOG_DIRS={path}", txt)
                else:
                    txt += f"\nEXTRA_LOG_DIRS={path}\n"

            env_path.write_text(txt, "utf-8")

            # Also update in-memory config
            from config import Config
            Config.EXTRA_LOG_DIRS = [path] + list(
                getattr(Config, "EXTRA_LOG_DIRS", []))

        except Exception:
            pass    # non-fatal — user just has to pick again next time

    # ── File loading ─────────────────────────────────────────────────────────

    def _load_file(self, fi: dict):
        self._selected = fi
        n = int(self._lines_var.get())
        self.set_status(f"⏳ Loading {fi['name']}…", AMBER)
        self._ai_frame.grid_remove()

        def _run():
            return _tail(fi["path"], n)

        def _done(content):
            self._current_content = content
            self._show_content(content, fi["name"])

        bg(_run, _done, self)

    def _reload(self):
        if self._selected:
            self._load_file(self._selected)

    def _show_content(self, content: str, name: str):
        self._log_viewer.configure(state="normal")
        self._log_viewer.delete("1.0", "end")

        for line in content.splitlines(keepends=True):
            up = line.upper()
            if any(k in up for k in ("ERROR", "EXCEPTION", "FATAL", "CRITICAL")):
                tag = "err"
            elif any(k in up for k in ("WARN", "WARNING")):
                tag = "wrn"
            elif "INFO" in up:
                tag = "inf"
            else:
                tag = "def"
            self._log_viewer.insert("end", line, tag)

        self._log_viewer.tag_config("err", foreground="#ff6b6b")
        self._log_viewer.tag_config("wrn", foreground=AMBER)
        self._log_viewer.tag_config("inf", foreground=TEXT2)
        self._log_viewer.tag_config("def", foreground="#a8b4c8")

        self._log_viewer.configure(state="disabled")
        self._log_viewer.see("end")

        n_err  = content.upper().count("ERROR")
        n_warn = content.upper().count("WARN")
        col    = RED if n_err > 0 else (AMBER if n_warn > 0 else GREEN)
        self.set_status(
            f"📄 {name}  —  {n_err} error(s)  {n_warn} warning(s)  "
            f"| {int(self._lines_var.get())} lines shown", col)

        # Re-apply any active search
        q = self._search_var.get().strip()
        if q:
            self._highlight(q)

    # ── Search ───────────────────────────────────────────────────────────────

    def _on_search_change(self, *_):
        q = self._search_var.get().strip()
        self._highlight(q)

    def _highlight(self, query: str):
        self._log_viewer.configure(state="normal")
        self._log_viewer.tag_remove("hi", "1.0", "end")
        if query:
            start = "1.0"
            while True:
                pos = self._log_viewer.search(
                    query, start, nocase=True, stopindex="end")
                if not pos:
                    break
                end = f"{pos}+{len(query)}c"
                self._log_viewer.tag_add("hi", pos, end)
                start = end
            self._log_viewer.tag_config(
                "hi", background="#854d0e", foreground="white")
        self._log_viewer.configure(state="disabled")

    def _jump_next(self):
        q = self._search_var.get().strip()
        if not q:
            return
        try:
            cur = self._log_viewer.index("insert")
            pos = self._log_viewer.search(
                q, f"{cur}+1c", nocase=True, stopindex="end")
            if not pos:                        # wrap around
                pos = self._log_viewer.search(
                    q, "1.0", nocase=True, stopindex="end")
            if pos:
                self._log_viewer.see(pos)
                self._log_viewer.mark_set("insert", pos)
        except Exception:
            pass

    # ── AI analysis ──────────────────────────────────────────────────────────

    def _ai_analyse(self):
        if not self._current_content:
            show_info("No Log Loaded",
                      "Select a log file from the sidebar first.", parent=self)
            return

        snippet = self._current_content[-5000:]
        self._ai_frame.grid()
        self._ai_lbl.configure(text="🤖  Analysing with AI…", text_color=AMBER)
        self.set_status("⏳ AI analysing log…", AMBER)

        def _run():
            try:
                from ai.gemini_client import GeminiClient
                client = GeminiClient()
                fname  = self._selected["name"] if self._selected else "log"
                prompt = (
                    "You are an SAP BusinessObjects expert.\n"
                    f"Log file: {fname}\n\n"
                    "Analyse this BO log snippet and provide:\n"
                    "1. SUMMARY: What this log is and overall health status\n"
                    "2. ERRORS: List specific errors with line context (max 5)\n"
                    "3. ROOT CAUSE: Most likely cause for any errors found\n"
                    "4. FIX: Step-by-step remediation actions\n"
                    "5. SEVERITY: Critical / Warning / Healthy\n\n"
                    "Be concise and actionable. No markdown.\n\n"
                    f"LOG CONTENT:\n{snippet}"
                )
                for method in ("get_response", "ask", "generate",
                               "chat", "query"):
                    m = getattr(client, method, None)
                    if callable(m):
                        try:
                            r = m(prompt)
                            txt = r.text if hasattr(r, "text") else str(r)
                            break
                        except Exception:
                            pass
                else:
                    txt = ("AI analysis unavailable. "
                           "Check Gemini API key in Settings.")

                # Persist to KB if available
                try:
                    from memory.knowledge_base import kb
                    kb.log_incident(
                        kind="log_analysis",
                        obj=fname,
                        detail=txt[:400],
                        severity="INFO",
                        source="logs_tab")
                except Exception:
                    pass

                return txt
            except Exception as exc:
                return f"AI error: {exc}"

        def _done(txt):
            self._ai_lbl.configure(
                text=f"🤖  AI Analysis:\n\n{txt}", text_color=VIOLET)
            self.set_status("✅ AI analysis complete", GREEN)

        bg(_run, _done, self)
