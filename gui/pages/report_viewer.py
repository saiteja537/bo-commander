"""
gui/pages/report_viewer.py  —  BO Commander Report Viewer  v2.0
────────────────────────────────────────────────────────────────
Supports: WebI · Crystal Reports · Analysis for Office · PDF
Features:
  • Status-filtered instance view (All/Success/Failed/Running/Pending/Scheduled)
  • OpenDocument URL — correct BI 4.3 format (port 8080)
  • Export: PDF / Excel / CSV / HTML (WebI via Raylight REST)
  • AI error detection + fix suggestions on failed instances
  • Analytics dashboard — bar chart, status breakdown, health score
  • Prompt dialog for parameterised WebI reports
  • Schedule dialog
  • Embedded browser preview (if tkinterweb installed)
"""

import os
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

import customtkinter as ctk

from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS

# ── optional embedded browser ─────────────────────────────────────────────────
try:
    import tkinterweb
    HAS_BROWSER = True
except ImportError:
    HAS_BROWSER = False

# ── optional AI ───────────────────────────────────────────────────────────────
try:
    from ai.gemini_client import GeminiClient
    _ai = GeminiClient()
    HAS_AI = True
except Exception:
    HAS_AI = False

# ── Design tokens (dark cyber palette) ───────────────────────────────────────
T = {
    "bg0":     "#060d15",
    "bg1":     "#0b1622",
    "bg2":     "#0f1e2e",
    "bg3":     "#162638",
    "bg4":     "#1c3048",
    "border":  "#1e3a52",
    "cyan":    "#22d3ee",
    "blue":    "#3b82f6",
    "violet":  "#8b5cf6",
    "green":   "#22c55e",
    "amber":   "#f59e0b",
    "red":     "#ef4444",
    "rose":    "#f43f5e",
    "text":    "#e2eaf4",
    "text2":   "#8fafc8",
    "text3":   "#4a6d8c",
    "H1":      ("Segoe UI", 20, "bold"),
    "H2":      ("Segoe UI", 14, "bold"),
    "H3":      ("Segoe UI", 12, "bold"),
    "body":    ("Segoe UI", 12),
    "small":   ("Segoe UI", 10),
    "mono":    ("Courier New", 11),
}

STATUS_META = {
    "Success":   {"icon": "✅", "color": "#22c55e", "tag": "ok"},
    "Failed":    {"icon": "❌", "color": "#ef4444", "tag": "fail"},
    "Running":   {"icon": "⏳", "color": "#f59e0b", "tag": "run"},
    "Pending":   {"icon": "⏸", "color": "#8fafc8", "tag": "pend"},
    "Scheduled": {"icon": "📅", "color": "#3b82f6", "tag": "sched"},
    "Paused":    {"icon": "⏸", "color": "#8b5cf6", "tag": "pause"},
}

REPORT_META = {
    "Webi":          {"icon": "📊", "label": "Web Intelligence", "short": "WebI",    "color": "#3b82f6"},
    "CrystalReport": {"icon": "💎", "label": "Crystal Reports",  "short": "Crystal", "color": "#8b5cf6"},
    "Excel":         {"icon": "📗", "label": "Analysis for Office","short": "AO",    "color": "#22c55e"},
    "Pdf":           {"icon": "📄", "label": "PDF Document",      "short": "PDF",    "color": "#ef4444"},
}

def _rmeta(kind):
    return REPORT_META.get(kind, {"icon": "📋", "label": kind, "short": kind, "color": "#64748b"})

_ROOT_REF = [None]

def _bg(fn, cb):
    root = _ROOT_REF[0]
    def _run():
        try:    res = fn()
        except Exception as e: res = ("ERROR", str(e))
        if root:
            try: root.after(0, lambda r=res: cb(r))
            except Exception: pass
    threading.Thread(target=_run, daemon=True).start()


# ── OpenDocument URL builder (BI 4.3 correct format) ─────────────────────────
def _build_open_doc_url(report_id, kind="Webi"):
    """
    BI 4.3 OpenDocument URL — opens in default browser, works for ALL types.
    Falls back to BI Launchpad if token not available.
    """
    try:
        base = bo_session.base_url  # http://HOST:6405/biprws
        host = base.replace("/biprws", "").replace("https://", "").replace("http://", "")
        # Strip port from host if present, use 8080 for Launchpad
        host_only = host.split(":")[0]
        token = bo_session.logon_token or ""

        # Primary: OpenDocument (works for WebI, Crystal, AO, PDF)
        url = (
            f"http://{host_only}:8080/BOE/OpenDocument/opendoc/openDocument.jsp"
            f"?iDocID={report_id}&sIDType=InfoObjectID"
        )
        if token:
            url += f"&token={token}"
        return url
    except Exception:
        return None


def _build_launchpad_url(report_id):
    """BI Launchpad URL — alternative viewer."""
    try:
        base = bo_session.base_url
        host_only = base.replace("/biprws", "").replace("https://", "").replace("http://", "").split(":")[0]
        return f"http://{host_only}:8080/BOE/BI?startDocument={report_id}"
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  Prompt dialog
# ─────────────────────────────────────────────────────────────────────────────
class _PromptDialog(ctk.CTkToplevel):
    def __init__(self, parent, report_name, prompts):
        super().__init__(parent)
        self.title(f"Prompts — {report_name[:50]}")
        self.geometry("500x480")
        self.configure(fg_color=T["bg1"])
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        self._vars = {}
        self._build(prompts)

    def _build(self, prompts):
        ctk.CTkLabel(self, text="📝  Report Prompts", font=T["H2"],
                     text_color=T["cyan"]).pack(anchor="w", padx=20, pady=(18, 2))
        ctk.CTkLabel(self, text="Fill in values before running the report.",
                     font=T["small"], text_color=T["text2"]).pack(anchor="w", padx=20, pady=(0, 10))

        form = ctk.CTkScrollableFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=20, pady=(0, 4))

        if not prompts:
            ctk.CTkLabel(form, text="✅  No prompts required.",
                         font=T["body"], text_color=T["green"]).pack(pady=20)
        else:
            for p in prompts:
                name = p.get("name", p.get("id", str(p)))
                mandatory = p.get("mandatory", True)
                ctk.CTkLabel(form, text=f"{name}{'  *' if mandatory else ''}",
                             font=T["small"], text_color=T["text2"]).pack(anchor="w", pady=(8, 1))
                var = ctk.StringVar()
                self._vars[name] = var
                ctk.CTkEntry(form, textvariable=var, height=32,
                             placeholder_text=f"Enter {name}…",
                             fg_color=T["bg3"], border_color=T["cyan"] if mandatory else T["border"],
                             text_color=T["text"], font=T["body"]).pack(fill="x")

        bar = ctk.CTkFrame(self, fg_color="transparent", height=52)
        bar.pack(fill="x", padx=20, pady=(4, 14))
        bar.pack_propagate(False)
        ctk.CTkButton(bar, text="Cancel", width=90, height=36,
                      fg_color=T["bg3"], text_color=T["text2"],
                      command=self.destroy).pack(side="right")
        ctk.CTkButton(bar, text="▶  Run Report", width=140, height=36,
                      fg_color=T["cyan"], text_color=T["bg0"],
                      hover_color="#06b6d4",
                      font=("Segoe UI", 12, "bold"),
                      command=self._submit).pack(side="right", padx=(0, 8))

    def _submit(self):
        self.result = {k: v.get().strip() for k, v in self._vars.items()}
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
#  Schedule dialog
# ─────────────────────────────────────────────────────────────────────────────
class _ScheduleDialog(ctk.CTkToplevel):
    def __init__(self, parent, report_name):
        super().__init__(parent)
        self.title(f"Schedule — {report_name[:50]}")
        self.geometry("440x400")
        self.configure(fg_color=T["bg1"])
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="📅  Schedule Report", font=T["H2"],
                     text_color=T["cyan"]).pack(anchor="w", padx=20, pady=(18, 12))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=20)

        self._freq = ctk.StringVar(value="Once (immediate)")
        self._fmt  = ctk.StringVar(value="PDF")
        self._dest = ctk.StringVar()

        for label, var, opts in [
            ("Frequency",     self._freq, ["Once (immediate)", "Hourly", "Daily", "Weekly", "Monthly"]),
            ("Output Format", self._fmt,  ["PDF", "Excel", "CSV", "HTML"]),
        ]:
            ctk.CTkLabel(form, text=label, font=T["small"],
                         text_color=T["text2"]).pack(anchor="w", pady=(10, 2))
            ctk.CTkOptionMenu(form, values=opts, variable=var,
                              fg_color=T["bg3"], button_color=T["blue"],
                              text_color=T["text"], height=32,
                              font=T["body"]).pack(fill="x")

        ctk.CTkLabel(form, text="Destination (email or folder, optional)",
                     font=T["small"], text_color=T["text2"]).pack(anchor="w", pady=(10, 2))
        ctk.CTkEntry(form, textvariable=self._dest, height=32,
                     placeholder_text="user@company.com or leave blank",
                     fg_color=T["bg3"], border_color=T["border"],
                     text_color=T["text"], font=T["body"]).pack(fill="x")

        bar = ctk.CTkFrame(self, fg_color="transparent", height=52)
        bar.pack(fill="x", padx=20, pady=(16, 0))
        bar.pack_propagate(False)
        ctk.CTkButton(bar, text="Cancel", width=90, height=36,
                      fg_color=T["bg3"], text_color=T["text2"],
                      command=self.destroy).pack(side="right")
        ctk.CTkButton(bar, text="📅  Schedule", width=120, height=36,
                      fg_color=T["blue"], hover_color="#2563eb",
                      font=("Segoe UI", 12, "bold"),
                      command=self._submit).pack(side="right", padx=(0, 8))

    def _submit(self):
        self.result = {
            "frequency":   self._freq.get(),
            "format":      self._fmt.get(),
            "destination": self._dest.get().strip(),
        }
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
#  AI Error Analysis window
# ─────────────────────────────────────────────────────────────────────────────
class _AIAnalysisWindow(ctk.CTkToplevel):
    def __init__(self, parent, report, instances):
        super().__init__(parent)
        self.title(f"🤖 AI Analysis — {report['name'][:50]}")
        self.geometry("680x560")
        self.configure(fg_color=T["bg1"])
        self._report    = report
        self._instances = instances
        self._build()
        threading.Thread(target=self._analyze, daemon=True).start()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=T["bg3"], corner_radius=0, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="🤖  AI Error Detection & Fix Assistant",
                     font=T["H2"], text_color=T["cyan"]).pack(side="left", padx=16)
        ctk.CTkLabel(hdr, text="Powered by Gemini AI  •  Always verify before applying",
                     font=T["small"], text_color=T["amber"]).pack(side="right", padx=16)

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=12)

        # Report summary
        s_frame = ctk.CTkFrame(body, fg_color=T["bg3"], corner_radius=8)
        s_frame.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(s_frame, text=f"Report:  {self._report['name']}",
                     font=T["H3"], text_color=T["text"]).pack(anchor="w", padx=14, pady=(10, 2))

        failed  = [i for i in self._instances if "fail" in i.get("status","").lower()]
        running = [i for i in self._instances if "run"  in i.get("status","").lower()]
        ctk.CTkLabel(s_frame,
                     text=f"Total instances: {len(self._instances)}   |   "
                          f"Failed: {len(failed)}   |   Running: {len(running)}",
                     font=T["body"], text_color=T["text2"]).pack(anchor="w", padx=14, pady=(0, 10))

        # AI response area
        self._result_box = ctk.CTkTextbox(body, font=T["body"],
                                           fg_color=T["bg2"],
                                           text_color=T["text"],
                                           border_color=T["border"],
                                           border_width=1,
                                           wrap="word", height=340)
        self._result_box.pack(fill="x")
        self._result_box.insert("end", "⏳  Analyzing with Gemini AI…\n")
        self._result_box.configure(state="disabled")

        bar = ctk.CTkFrame(self, fg_color="transparent", height=50)
        bar.pack(fill="x", padx=16, pady=(4, 12))
        bar.pack_propagate(False)
        ctk.CTkButton(bar, text="Close", width=90, height=36,
                      fg_color=T["bg3"], text_color=T["text2"],
                      command=self.destroy).pack(side="right")

    def _analyze(self):
        if not HAS_AI:
            self._set_text("⚠  AI engine not available. Check Gemini API key in settings.")
            return

        failed = [i for i in self._instances if "fail" in i.get("status","").lower()]
        if not failed:
            self._set_text("✅  No failed instances detected for this report.\n\nAll recent runs completed successfully.")
            return

        context = f"""
You are an SAP BusinessObjects expert analyzing failed report instances.

Report: {self._report['name']}
Type: {self._report.get('kind', 'Unknown')}
Owner: {self._report.get('owner', 'Unknown')}
Total instances analyzed: {len(self._instances)}
Failed instances: {len(failed)}

Failed instance details:
{chr(10).join(
    f"- Start: {i.get('start_time','')}  End: {i.get('end_time','')}  Owner: {i.get('owner','')}"
    for i in failed[:10]
)}

Provide:
1. LIKELY CAUSES — list the most common reasons this report type fails in SAP BO BI 4.3
2. DIAGNOSTIC STEPS — what to check in CMC, server logs, and BO administration
3. RECOMMENDED FIXES — actionable steps in order of likelihood
4. PREVENTION — how to avoid recurrence

Be specific to SAP BO BI 4.3. Use plain text, no markdown formatting.
"""
        try:
            response = _ai.ask(context)
            self._set_text(response)
        except Exception as e:
            self._set_text(f"❌  AI analysis failed: {e}\n\nManual check: Review CMC → Instances and server logs.")

    def _set_text(self, text):
        try:
            if self.winfo_exists():
                self.after(0, lambda: self._update_box(text))
        except Exception:
            pass

    def _update_box(self, text):
        self._result_box.configure(state="normal")
        self._result_box.delete("1.0", "end")
        self._result_box.insert("end", text)
        self._result_box.configure(state="disabled")


# ─────────────────────────────────────────────────────────────────────────────
#  Instances window with status filters
# ─────────────────────────────────────────────────────────────────────────────
class _InstancesWindow(ctk.CTkToplevel):
    def __init__(self, parent, report):
        super().__init__(parent)
        self._report    = report
        self._instances = []
        self._filter    = "All"
        self.title(f"📋  Instances — {report['name'][:50]}")
        self.geometry("900x560")
        self.configure(fg_color=T["bg1"])
        self._build()
        threading.Thread(target=self._load, daemon=True).start()

    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=T["bg3"], corner_radius=0, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=f"📋  {self._report['name']}  — Run Instances",
                     font=T["H3"], text_color=T["text"]).pack(side="left", padx=16)
        self._status_lbl = ctk.CTkLabel(hdr, text="Loading…",
                                         font=T["small"], text_color=T["text2"])
        self._status_lbl.pack(side="right", padx=16)

        # Status filter tabs
        tabs = ctk.CTkFrame(self, fg_color=T["bg2"], height=40)
        tabs.pack(fill="x", padx=12, pady=(8, 0))
        tabs.pack_propagate(False)
        self._tab_btns = {}
        for label, color in [
            ("All",       T["cyan"]),
            ("Success",   T["green"]),
            ("Failed",    T["red"]),
            ("Running",   T["amber"]),
            ("Pending",   T["text2"]),
            ("Scheduled", T["blue"]),
        ]:
            btn = ctk.CTkButton(tabs, text=label, width=100, height=28,
                                corner_radius=6, font=T["small"],
                                fg_color=T["cyan"] if label == "All" else T["bg3"],
                                hover_color=color, text_color=T["text"],
                                command=lambda l=label, c=color: self._set_filter(l, c))
            btn.pack(side="left", padx=3)
            self._tab_btns[label] = (btn, color)

        # Action bar
        act = ctk.CTkFrame(self, fg_color="transparent", height=40)
        act.pack(fill="x", padx=12, pady=(6, 0))
        act.pack_propagate(False)
        ctk.CTkButton(act, text="🤖 AI Analyse", width=120, height=30,
                      fg_color=T["violet"], hover_color="#7c3aed",
                      font=T["small"],
                      command=self._ai_analyse).pack(side="left", padx=(0, 8))
        ctk.CTkButton(act, text="🔄 Retry Failed", width=120, height=30,
                      fg_color=T["amber"], text_color=T["bg0"],
                      hover_color="#d97706", font=T["small"],
                      command=self._retry_failed).pack(side="left", padx=(0, 8))
        ctk.CTkButton(act, text="🗑 Delete Selected", width=130, height=30,
                      fg_color=T["red"], hover_color="#dc2626",
                      font=T["small"],
                      command=self._delete_selected).pack(side="left")

        # Tree
        tv_frame = ctk.CTkFrame(self, fg_color=T["bg2"], corner_radius=8)
        tv_frame.pack(fill="both", expand=True, padx=12, pady=8)

        sn = f"INS{id(self)}"
        s = ttk.Style()
        s.configure(sn, background=T["bg2"], foreground=T["text"],
                    fieldbackground=T["bg2"], rowheight=30, font=("Segoe UI", 11), borderwidth=0)
        s.configure(f"{sn}.Heading", background=T["bg3"], foreground=T["text2"],
                    font=("Segoe UI", 10, "bold"), relief="flat")
        s.map(sn, background=[("selected", T["blue"])], foreground=[("selected", "white")])
        s.layout(sn, [("Treeview.treearea", {"sticky": "nswe"})])

        cols = [("status","Status",100), ("name","Name",240), ("start","Started",155),
                ("end","Ended",155), ("owner","Owner",110), ("fmt","Format",80)]
        self._tv = ttk.Treeview(tv_frame, style=sn, show="headings",
                                columns=[c[0] for c in cols], selectmode="extended")
        for cid, hd, w in cols:
            self._tv.heading(cid, text=hd)
            self._tv.column(cid, width=w, minwidth=40)

        for st, meta in STATUS_META.items():
            self._tv.tag_configure(meta["tag"], foreground=meta["color"])

        vsb = ctk.CTkScrollbar(tv_frame, orientation="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y", pady=6)
        self._tv.pack(fill="both", expand=True, padx=6, pady=6)

    def _load(self):
        insts = bo_session.get_report_instances(self._report["id"], limit=200)
        self._instances = insts or []
        self.after(0, self._render)

    def _set_filter(self, label, color):
        self._filter = label
        for l, (btn, col) in self._tab_btns.items():
            btn.configure(fg_color=col if l == label else T["bg3"])
        self._render()

    def _render(self):
        for row in self._tv.get_children():
            self._tv.delete(row)

        filtered = self._instances if self._filter == "All" else [
            i for i in self._instances
            if self._filter.lower() in i.get("status", "").lower()
        ]

        for inst in filtered:
            st   = inst.get("status", "Unknown")
            meta = STATUS_META.get(st, {"icon": "⬜", "color": T["text2"], "tag": ""})
            self._tv.insert("", "end", iid=str(inst.get("id", id(inst))),
                            tags=(meta["tag"],),
                            values=(
                                f"{meta['icon']} {st}",
                                inst.get("name", self._report["name"])[:50],
                                str(inst.get("start_time", ""))[:19],
                                str(inst.get("end_time", ""))[:19],
                                inst.get("owner", ""),
                                inst.get("format", ""),
                            ))

        n = len(filtered)
        self._status_lbl.configure(
            text=f"{n} instance{'s' if n != 1 else ''}  |  total: {len(self._instances)}")

    def _ai_analyse(self):
        _AIAnalysisWindow(self, self._report, self._instances)

    def _retry_failed(self):
        failed_ids = [
            inst["id"] for inst in self._instances
            if "fail" in inst.get("status", "").lower() and inst.get("id")
        ]
        if not failed_ids:
            messagebox.showinfo("No Failed Instances",
                                "No failed instances to retry.", parent=self)
            return
        ok, err = bo_session.bulk_retry_instances(failed_ids)
        messagebox.showinfo("Retry Result",
                            f"✅ Retried: {ok}  |  ❌ Errors: {err}", parent=self)

    def _delete_selected(self):
        sel = self._tv.selection()
        if not sel:
            messagebox.showinfo("Nothing selected",
                                "Select instances first.", parent=self)
            return
        if not messagebox.askyesno("Confirm Delete",
                                   f"Delete {len(sel)} instance(s)?", parent=self):
            return
        ok = err = 0
        for iid in sel:
            success, _ = bo_session.delete_instance(iid)
            if success:
                ok += 1
                self._tv.delete(iid)
            else:
                err += 1
        self._status_lbl.configure(text=f"Deleted {ok}  |  Errors: {err}")


# ─────────────────────────────────────────────────────────────────────────────
#  Analytics panel  (mini bar chart + health score using CTk canvas)
# ─────────────────────────────────────────────────────────────────────────────
class _AnalyticsPanel(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=T["bg2"], corner_radius=10, **kw)
        self._data = {}
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="📈  Analytics", font=T["H3"],
                     text_color=T["cyan"]).pack(anchor="w", padx=12, pady=(10, 6))
        ctk.CTkFrame(self, height=1, fg_color=T["border"]).pack(fill="x", padx=12)

        self._canvas = tk.Canvas(self, bg=T["bg2"], highlightthickness=0, height=160)
        self._canvas.pack(fill="x", padx=12, pady=8)

        self._score_lbl = ctk.CTkLabel(self, text="Health Score  —",
                                        font=("Segoe UI", 11, "bold"),
                                        text_color=T["text2"])
        self._score_lbl.pack(anchor="w", padx=12, pady=(0, 6))

        ctk.CTkFrame(self, height=1, fg_color=T["border"]).pack(fill="x", padx=12)
        self._detail = ctk.CTkLabel(self, text="Select reports to see analytics",
                                     font=T["small"], text_color=T["text2"],
                                     justify="left", wraplength=220)
        self._detail.pack(anchor="w", padx=12, pady=8)

    def update(self, reports):
        self._data = {
            "Webi":    sum(1 for r in reports if r.get("kind") == "Webi"),
            "Crystal": sum(1 for r in reports if r.get("kind") == "CrystalReport"),
            "AO":      sum(1 for r in reports if r.get("kind") == "Excel"),
            "PDF":     sum(1 for r in reports if r.get("kind") == "Pdf"),
            "Other":   sum(1 for r in reports if r.get("kind") not in ("Webi","CrystalReport","Excel","Pdf")),
        }
        total = max(sum(self._data.values()), 1)
        score = min(100, int(100 * (self._data.get("Webi", 0) + self._data.get("Crystal", 0)) / total + 60))

        # Draw bar chart
        self._canvas.delete("all")
        bars = [
            ("WebI",    self._data["Webi"],    T["blue"]),
            ("Crystal", self._data["Crystal"], T["violet"]),
            ("AO",      self._data["AO"],      T["green"]),
            ("PDF",     self._data["PDF"],      T["red"]),
            ("Other",   self._data["Other"],    T["text2"]),
        ]
        max_val = max(v for _, v, _ in bars) or 1
        bar_w = 32; gap = 10; x = 16; h = 140
        for label, val, color in bars:
            bar_h = int(val / max_val * 100)
            y_top = h - bar_h
            self._canvas.create_rectangle(x, y_top, x + bar_w, h,
                                          fill=color, outline="", width=0)
            self._canvas.create_text(x + bar_w // 2, h + 12,
                                     text=label, fill=T["text2"],
                                     font=("Segoe UI", 8))
            if val > 0:
                self._canvas.create_text(x + bar_w // 2, y_top - 8,
                                         text=str(val), fill=color,
                                         font=("Segoe UI", 9, "bold"))
            x += bar_w + gap

        score_color = T["green"] if score >= 80 else T["amber"] if score >= 50 else T["red"]
        self._score_lbl.configure(
            text=f"Health Score  {score}/100",
            text_color=score_color)

        self._detail.configure(
            text=f"Total: {total} reports\n"
                 f"WebI: {self._data['Webi']}  Crystal: {self._data['Crystal']}\n"
                 f"AO: {self._data['AO']}  PDF: {self._data['PDF']}")


# ─────────────────────────────────────────────────────────────────────────────
#  Detail / Action panel
# ─────────────────────────────────────────────────────────────────────────────
class _DetailPanel(ctk.CTkFrame):
    def __init__(self, parent, on_status, **kw):
        super().__init__(parent, fg_color=T["bg2"], corner_radius=10, **kw)
        self._on_status = on_status
        self._report    = None
        self._prompts   = []
        self._prompt_lbl = None
        self._build_empty()

    def _build_empty(self):
        for w in self.winfo_children():
            w.destroy()
        ctk.CTkLabel(self,
                     text="👈  Select a report\nto see details & actions",
                     font=T["body"], text_color=T["text2"],
                     justify="center").pack(expand=True)

    def load(self, report):
        self._report  = report
        self._prompts = []
        for w in self.winfo_children():
            w.destroy()
        self._build_detail(report)
        if report.get("kind") == "Webi":
            _bg(lambda: bo_session.get_report_prompts(report["id"]), self._on_prompts)

    def _on_prompts(self, res):
        self._prompts = res if isinstance(res, list) else []
        if self._prompt_lbl and self._prompt_lbl.winfo_exists():
            n = len(self._prompts)
            self._prompt_lbl.configure(
                text=f"{n} prompt{'s' if n != 1 else ''}",
                text_color=T["amber"] if n > 0 else T["green"])

    def _build_detail(self, r):
        meta = _rmeta(r.get("kind", ""))

        # Type banner
        banner = ctk.CTkFrame(self, fg_color=meta["color"], corner_radius=8, height=50)
        banner.pack(fill="x", padx=8, pady=(8, 0))
        banner.pack_propagate(False)
        ctk.CTkLabel(banner, text=f"{meta['icon']}  {meta['label']}",
                     font=T["H3"], text_color="white").pack(side="left", padx=12)
        ctk.CTkLabel(banner, text=meta["short"], font=("Segoe UI", 9, "bold"),
                     fg_color="#ffffff22", corner_radius=4,
                     text_color="white").pack(side="right", padx=10)

        # Metadata
        info = ctk.CTkFrame(self, fg_color="transparent")
        info.pack(fill="x", padx=10, pady=6)
        fields = [
            ("Name",     r.get("name", "—")[:45]),
            ("Owner",    r.get("owner", "—")),
            ("Created",  str(r.get("created", "—"))[:19]),
            ("Last Run", str(r.get("last_run", "—"))[:19]),
            ("Folder",   str(r.get("folder", "—"))[:30]),
            ("ID",       str(r.get("id", "—"))),
        ]
        for lbl, val in fields:
            row = ctk.CTkFrame(info, fg_color="transparent", height=22)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)
            ctk.CTkLabel(row, text=f"{lbl}:", width=70, anchor="w",
                         font=T["small"], text_color=T["text2"]).pack(side="left")
            ctk.CTkLabel(row, text=val, anchor="w",
                         font=T["small"], text_color=T["text"]).pack(side="left")

        if r.get("kind") == "Webi":
            prow = ctk.CTkFrame(info, fg_color="transparent", height=22)
            prow.pack(fill="x", pady=1)
            prow.pack_propagate(False)
            ctk.CTkLabel(prow, text="Prompts:", width=70, anchor="w",
                         font=T["small"], text_color=T["text2"]).pack(side="left")
            self._prompt_lbl = ctk.CTkLabel(prow, text="checking…",
                                             font=T["small"], text_color=T["text2"])
            self._prompt_lbl.pack(side="left")

        ctk.CTkFrame(self, height=1, fg_color=T["border"]).pack(fill="x", padx=10, pady=4)

        # Action buttons
        acts = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        acts.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        kind = r.get("kind", "")

        def _sec(t): ctk.CTkLabel(acts, text=t, font=("Segoe UI", 9, "bold"),
                                   text_color=T["text3"], anchor="w").pack(fill="x", padx=4, pady=(10, 2))
        def _btn(t, col, cmd, hover=None):
            ctk.CTkButton(acts, text=t, height=34, anchor="w",
                          fg_color=col, hover_color=hover or col,
                          font=T["body"], text_color="white",
                          command=cmd).pack(fill="x", padx=4, pady=2)

        if kind == "Webi":
            _sec("Run")
            _btn("▶  Run / Refresh",     T["blue"],   self._run_webi,    "#2563eb")
            _btn("🌐  Open in Browser",   "#0ea5e9",   self._open_browser,"#0284c7")
            _btn("🖥  View in Launchpad", "#6366f1",   self._open_launchpad,"#4f46e5")
            _sec("Export")
            for fmt, col in [("PDF","#dc2626"),("Excel","#16a34a"),("CSV","#0891b2"),("HTML","#7c3aed")]:
                _btn(f"⬇  Export {fmt}", col, lambda f=fmt: self._export(f))
            _sec("Manage")
            _btn("📅  Schedule",         T["green"],  self._schedule,    "#16a34a")
            _btn("📋  View Instances",   T["amber"],  self._view_instances,"#d97706")
            _btn("🤖  AI Error Analysis",T["violet"],self._ai_quick,    "#7c3aed")

        elif kind == "CrystalReport":
            _sec("View")
            _btn("🌐  Open in Browser",   T["violet"], self._open_browser, "#7c3aed")
            _btn("🖥  Open in Launchpad", "#6366f1",   self._open_launchpad,"#4f46e5")
            _sec("Export")
            for fmt, col in [("PDF","#dc2626"),("Excel","#16a34a")]:
                _btn(f"⬇  Export {fmt}", col, lambda f=fmt: self._export(f))
            _sec("Manage")
            _btn("📅  Schedule",         T["green"],  self._schedule,    "#16a34a")
            _btn("📋  View Instances",   T["amber"],  self._view_instances,"#d97706")
            ctk.CTkLabel(acts,
                         text="⚠  Crystal Reports cannot be rendered inline.\n"
                              "Use Open in Browser to view.",
                         font=T["small"], text_color=T["text2"],
                         wraplength=220, justify="left").pack(anchor="w", padx=6, pady=6)

        elif kind in ("Excel", "Pdf"):
            _sec("Download")
            _btn("⬇  Download File",     T["green"],  self._download,    "#16a34a")
            _btn("🌐  Open in Launchpad", "#0ea5e9",   self._open_launchpad,"#0284c7")
            _sec("Manage")
            _btn("📅  Schedule",         T["blue"],   self._schedule,    "#2563eb")
            _btn("📋  View Instances",   T["amber"],  self._view_instances,"#d97706")
            ctk.CTkLabel(acts,
                         text="📗  AO workbooks require Excel\nwith SAP AO add-in installed.",
                         font=T["small"], text_color=T["text2"],
                         wraplength=220, justify="left").pack(anchor="w", padx=6, pady=6)

        else:
            _btn("🌐  Open in Browser",  T["blue"],  self._open_browser,  "#2563eb")
            _btn("⬇  Export PDF",        T["red"],   lambda: self._export("PDF"), "#dc2626")

    # ── Actions ───────────────────────────────────────────────────────────────
    def _run_webi(self):
        if not self._report: return
        if self._prompts:
            dlg = _PromptDialog(self.winfo_toplevel(), self._report["name"], self._prompts)
            self.winfo_toplevel().wait_window(dlg)
            if dlg.result is None: return
            vals = dlg.result
        else:
            vals = {}
        self._on_status("⏳ Running report…")
        _bg(lambda: bo_session.run_report_with_prompts(self._report["id"], vals),
            self._on_run_done)

    def _on_run_done(self, res):
        ok  = res[0] if isinstance(res, tuple) else bool(res)
        msg = res[1] if isinstance(res, tuple) and len(res) > 1 else ""
        if ok:
            self._on_status("✅ Report submitted")
            messagebox.showinfo("Success", "✅ Report run submitted!\nCheck Instances for output.",
                                parent=self.winfo_toplevel())
        else:
            self._on_status(f"❌ Run failed: {msg}")
            messagebox.showerror("Failed", f"❌ Could not run report:\n{msg}",
                                 parent=self.winfo_toplevel())

    def _open_browser(self):
        if not self._report: return
        url = _build_open_doc_url(self._report["id"], self._report.get("kind",""))
        if url:
            webbrowser.open(url)
            self._on_status(f"🌐 Opened: {self._report['name']}")
        else:
            messagebox.showwarning("No URL", "Could not build OpenDocument URL.\nCheck BO server host in Settings.",
                                   parent=self.winfo_toplevel())

    def _open_launchpad(self):
        if not self._report: return
        url = _build_launchpad_url(self._report["id"])
        if url:
            webbrowser.open(url)
            self._on_status(f"🌐 Opened in Launchpad: {self._report['name']}")
        else:
            messagebox.showwarning("No URL", "Could not build Launchpad URL.",
                                   parent=self.winfo_toplevel())

    def _export(self, fmt):
        if not self._report: return
        ext  = {"PDF": ".pdf","Excel": ".xlsx","CSV": ".csv","HTML": ".html"}.get(fmt, ".bin")
        name = self._report["name"].replace(" ","_").replace("/","_")[:40]
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            title=f"Export {fmt}",
            defaultextension=ext,
            filetypes=[(f"{fmt} File", f"*{ext}")],
            initialfile=f"{name}_{ts}{ext}",
            parent=self.winfo_toplevel())
        if not path: return
        self._on_status(f"⏳ Exporting {fmt}…")
        _bg(lambda: bo_session.export_report(self._report["id"], fmt, self._report.get("kind","Webi")),
            lambda r: self._on_export_done(r, path, fmt))

    def _on_export_done(self, data, path, fmt):
        if data:
            try:
                with open(path, "wb" if isinstance(data, bytes) else "w") as f:
                    f.write(data)
                kb = os.path.getsize(path) // 1024
                self._on_status(f"✅ {fmt} saved: {os.path.basename(path)} ({kb} KB)")
                messagebox.showinfo("Exported",
                                    f"✅ {fmt} exported!\n\nFile: {path}\nSize: {kb} KB",
                                    parent=self.winfo_toplevel())
            except Exception as e:
                self._on_status(f"❌ Save failed: {e}")
        else:
            self._on_status(f"❌ Export {fmt} failed")
            messagebox.showerror("Export Failed",
                                 f"❌ Could not export as {fmt}.\n"
                                 f"This format may not be supported for {self._report.get('kind','this')} reports.",
                                 parent=self.winfo_toplevel())

    def _download(self):
        kind = self._report.get("kind","")
        self._export("Excel" if kind == "Excel" else "PDF")

    def _schedule(self):
        if not self._report: return
        dlg = _ScheduleDialog(self.winfo_toplevel(), self._report["name"])
        self.winfo_toplevel().wait_window(dlg)
        if not dlg.result: return
        self._on_status("⏳ Scheduling…")
        sched = dlg.result
        _bg(lambda: bo_session.schedule_report(
                self._report["id"],
                schedule_type=sched["frequency"],
                params={"outputFormat": sched["format"], "destination": sched["destination"]}),
            lambda r: self._on_schedule_done(r))

    def _on_schedule_done(self, res):
        ok  = res[0] if isinstance(res, tuple) else bool(res)
        msg = res[1] if isinstance(res, tuple) and len(res) > 1 else ""
        if ok:
            self._on_status("✅ Scheduled")
            messagebox.showinfo("Scheduled", "✅ Report scheduled!", parent=self.winfo_toplevel())
        else:
            self._on_status(f"❌ Schedule failed: {msg}")
            messagebox.showerror("Failed", f"❌ Could not schedule:\n{msg}",
                                 parent=self.winfo_toplevel())

    def _view_instances(self):
        if self._report:
            _InstancesWindow(self.winfo_toplevel(), self._report)

    def _ai_quick(self):
        if not self._report: return
        def _fetch():
            insts = bo_session.get_report_instances(self._report["id"], limit=50)
            return insts or []
        _bg(_fetch, lambda insts: _AIAnalysisWindow(
            self.winfo_toplevel(), self._report, insts))


# ─────────────────────────────────────────────────────────────────────────────
#  Main Report Viewer Page
# ─────────────────────────────────────────────────────────────────────────────
class ReportViewerPage(ctk.CTkFrame):

    _COLS = [
        ("dot",      "●",           26, False),
        ("icon",     "",            26, False),
        ("name",     "Report Name", 260, True),
        ("kind",     "Type",        100, False),
        ("owner",    "Owner",       100, False),
        ("folder",   "Folder",      120, False),
        ("last_run", "Last Run",    130, False),
    ]

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=T["bg0"], corner_radius=0, **kw)
        _ROOT_REF[0] = self.winfo_toplevel()
        self._all_reports = []
        self._destroyed   = False
        self._active_type = "All"
        self._build_ui()
        threading.Thread(target=self._load, daemon=True).start()

    def destroy(self):
        self._destroyed = True
        super().destroy()

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=T["bg1"], corner_radius=0, height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(hdr, text="📊  Report Viewer",
                     font=T["H1"], text_color=T["cyan"]).pack(side="left", padx=18)

        self._status_lbl = ctk.CTkLabel(hdr, text="", font=T["small"],
                                         text_color=T["text2"])
        self._status_lbl.pack(side="right", padx=18)

        ctk.CTkButton(hdr, text="⟳  Refresh", width=100, height=34,
                      font=T["body"], fg_color=T["bg3"],
                      border_color=T["border"], border_width=1,
                      hover_color=T["bg4"],
                      command=lambda: threading.Thread(target=self._load, daemon=True).start()
                      ).pack(side="right", padx=(0, 8))

        # ── Legend strip ──────────────────────────────────────────────────────
        leg = ctk.CTkFrame(self, fg_color=T["bg2"], corner_radius=0, height=34)
        leg.pack(fill="x")
        leg.pack_propagate(False)
        for icon, lbl, col in [
            ("📊", "WebI — Run · Export PDF/Excel/CSV · Schedule · Prompts", T["blue"]),
            ("💎", "Crystal — Open in Browser · Export · Schedule",          T["violet"]),
            ("📗", "AO — Download · Schedule",                               T["green"]),
            ("📄", "PDF — Download",                                         T["red"]),
        ]:
            ctk.CTkLabel(leg, text=f"{icon} {lbl}", font=("Segoe UI", 9),
                         text_color=col).pack(side="left", padx=12)

        # ── Type filter tabs ──────────────────────────────────────────────────
        tabs = ctk.CTkFrame(self, fg_color=T["bg1"], height=44)
        tabs.pack(fill="x", padx=14, pady=(8, 0))
        tabs.pack_propagate(False)
        self._tab_btns = {}
        for tid, icon, col in [
            ("All","📋",T["cyan"]), ("Webi","📊",T["blue"]),
            ("CrystalReport","💎",T["violet"]), ("Excel","📗",T["green"]),
            ("Pdf","📄",T["red"]),
        ]:
            lbl = "All" if tid == "All" else _rmeta(tid)["short"]
            btn = ctk.CTkButton(tabs, text=f"{icon} {lbl}", height=32, width=110,
                                corner_radius=6, font=T["body"],
                                fg_color=col if tid == "All" else T["bg3"],
                                hover_color=col, text_color="white",
                                command=lambda t=tid, c=col: self._set_type(t, c))
            btn.pack(side="left", padx=3)
            self._tab_btns[tid] = (btn, col)

        # ── Summary cards ─────────────────────────────────────────────────────
        cards = ctk.CTkFrame(self, fg_color="transparent", height=76)
        cards.pack(fill="x", padx=14, pady=(8, 0))
        cards.pack_propagate(False)
        self._card_lbls = {}
        for key, lbl, col in [
            ("total",   "Total",    T["cyan"]),
            ("webi",    "WebI",     T["blue"]),
            ("crystal", "Crystal",  T["violet"]),
            ("ao",      "AO/Excel", T["green"]),
            ("other",   "Other",    T["text2"]),
        ]:
            card = ctk.CTkFrame(cards, fg_color=T["bg2"], corner_radius=8,
                                border_color=T["border"], border_width=1)
            card.pack(side="left", padx=(0, 8), fill="both", expand=True)
            ctk.CTkLabel(card, text=lbl, font=("Segoe UI", 9),
                         text_color=T["text2"]).pack(pady=(8, 0))
            v = ctk.CTkLabel(card, text="—", font=("Segoe UI", 22, "bold"),
                             text_color=col)
            v.pack(pady=(0, 8))
            self._card_lbls[key] = v

        # ── Search + sort bar ─────────────────────────────────────────────────
        sbar = ctk.CTkFrame(self, fg_color="transparent", height=36)
        sbar.pack(fill="x", padx=14, pady=(8, 4))
        sbar.pack_propagate(False)

        self._q_var = ctk.StringVar()
        self._q_var.trace_add("write", lambda *_: self._render())
        ctk.CTkEntry(sbar, textvariable=self._q_var,
                     placeholder_text="🔎  Search by name, owner, folder…",
                     width=320, height=32,
                     fg_color=T["bg2"], border_color=T["border"],
                     text_color=T["text"], font=T["body"]).pack(side="left")

        ctk.CTkButton(sbar, text="🤖 AI Scan All", width=120, height=32,
                      fg_color=T["violet"], hover_color="#7c3aed",
                      font=T["body"],
                      command=self._ai_scan_all).pack(side="right")

        # ── Body: list + right panels ─────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        # Left: treeview
        left = ctk.CTkFrame(body, fg_color=T["bg1"], corner_radius=8)
        left.pack(side="left", fill="both", expand=True)

        sn = f"RV{id(self)}"
        s  = ttk.Style()
        s.configure(sn, background=T["bg1"], foreground=T["text"],
                    fieldbackground=T["bg1"], rowheight=34,
                    font=("Segoe UI", 11), borderwidth=0)
        s.configure(f"{sn}.Heading", background=T["bg3"],
                    foreground=T["text2"], font=("Segoe UI", 10, "bold"), relief="flat")
        s.map(sn, background=[("selected", T["blue"])],
              foreground=[("selected", "white")])
        s.layout(sn, [("Treeview.treearea", {"sticky": "nswe"})])

        self._tv = ttk.Treeview(left, style=sn, show="headings",
                                selectmode="browse",
                                columns=[c[0] for c in self._COLS])
        for cid, hd, w, st in self._COLS:
            self._tv.heading(cid, text=hd)
            self._tv.column(cid, width=w, minwidth=20, stretch=st)

        self._tv.tag_configure("webi",    foreground="#60a5fa")
        self._tv.tag_configure("crystal", foreground="#a78bfa")
        self._tv.tag_configure("ao",      foreground="#34d399")
        self._tv.tag_configure("pdf",     foreground="#f87171")
        self._tv.tag_configure("other",   foreground="#94a3b8")

        vsb = ctk.CTkScrollbar(left, orientation="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y", padx=(0, 4), pady=8)
        self._tv.pack(fill="both", expand=True, padx=8, pady=8)
        self._tv.bind("<<TreeviewSelect>>", self._on_select)
        self._tv.bind("<Double-1>",          self._on_double)

        # Right: detail + analytics stacked
        right = ctk.CTkFrame(body, fg_color="transparent", width=270)
        right.pack(side="right", fill="y", padx=(10, 0))
        right.pack_propagate(False)

        self._detail = _DetailPanel(right,
                                    on_status=lambda m: self._status_lbl.configure(text=m))
        self._detail.pack(fill="both", expand=True)

        self._analytics = _AnalyticsPanel(right)
        self._analytics.pack(fill="x", pady=(8, 0))

    # ── Data ──────────────────────────────────────────────────────────────────
    def _load(self):
        self.after(0, lambda: self._status_lbl.configure(text="⏳ Loading…"))
        reports = bo_session.get_all_reports_typed()
        if not self._destroyed:
            self.after(0, lambda r=reports: self._on_loaded(r))

    def _on_loaded(self, reports):
        self._all_reports = reports or []
        self._render()
        self._update_cards()
        self._analytics.update(self._all_reports)

    def _set_type(self, tid, color):
        self._active_type = tid
        for t, (btn, col) in self._tab_btns.items():
            btn.configure(fg_color=col if t == tid else T["bg3"])
        self._render()

    def _render(self):
        q     = self._q_var.get().lower()
        ftype = self._active_type
        shown = [
            r for r in self._all_reports
            if (ftype == "All" or r.get("kind") == ftype)
            and (not q or q in r.get("name","").lower()
                       or q in r.get("owner","").lower()
                       or q in r.get("folder","").lower())
        ]
        for row in self._tv.get_children():
            self._tv.delete(row)
        for r in shown:
            kind = r.get("kind", "")
            meta = _rmeta(kind)
            tag  = {"Webi":"webi","CrystalReport":"crystal",
                    "Excel":"ao","Pdf":"pdf"}.get(kind,"other")
            self._tv.insert("", "end", iid=str(r["id"]), tags=(tag,),
                            values=("●", meta["icon"],
                                    r.get("name",""), meta["short"],
                                    r.get("owner",""), r.get("folder",""),
                                    str(r.get("last_run",""))[:19]))
        self._status_lbl.configure(
            text=f"{len(self._all_reports)} reports  |  showing {len(shown)}")

    def _update_cards(self):
        kinds = [r.get("kind","") for r in self._all_reports]
        self._card_lbls["total"].configure(text=str(len(self._all_reports)))
        self._card_lbls["webi"].configure(text=str(kinds.count("Webi")))
        self._card_lbls["crystal"].configure(text=str(kinds.count("CrystalReport")))
        self._card_lbls["ao"].configure(text=str(kinds.count("Excel")))
        other = sum(1 for k in kinds if k not in ("Webi","CrystalReport","Excel","Pdf"))
        self._card_lbls["other"].configure(text=str(other))

    def _on_select(self, event=None):
        sel = self._tv.selection()
        if not sel: return
        report = next((r for r in self._all_reports if str(r["id"]) == sel[0]), None)
        if report:
            self._detail.load(report)

    def _on_double(self, event=None):
        sel = self._tv.selection()
        if not sel: return
        report = next((r for r in self._all_reports if str(r["id"]) == sel[0]), None)
        if not report: return
        if report.get("kind") == "Webi":
            self._detail._run_webi()
        else:
            self._detail._open_browser()

    def _ai_scan_all(self):
        if not self._all_reports:
            messagebox.showinfo("No Reports", "Load reports first.", parent=self)
            return
        # Find reports with recent failures
        self._status_lbl.configure(text="⏳ AI scanning all reports…")
        def _scan():
            summary = []
            for r in self._all_reports[:20]:  # check top 20
                insts = bo_session.get_report_instances(r["id"], limit=10)
                failed = [i for i in (insts or []) if "fail" in i.get("status","").lower()]
                if failed:
                    summary.append({"report": r, "failed": len(failed), "instances": insts})
            return summary
        _bg(_scan, self._on_ai_scan_done)

    def _on_ai_scan_done(self, summary):
        if not summary:
            self._status_lbl.configure(text="✅ AI scan: no failures detected")
            messagebox.showinfo("AI Scan Complete",
                                "✅ No failed instances detected in recent reports.",
                                parent=self)
            return
        self._status_lbl.configure(
            text=f"⚠ AI scan: {len(summary)} report(s) with failures")
        # Open AI analysis for worst offender
        worst = max(summary, key=lambda x: x["failed"])
        _AIAnalysisWindow(self, worst["report"], worst["instances"])
