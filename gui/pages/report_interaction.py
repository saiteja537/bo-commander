"""
gui/pages/report_interaction.py  —  BO Commander Interactive Report Runner  v2.0
──────────────────────────────────────────────────────────────────────────────
Features:
  • Browse all report types (WebI, Crystal, AO, PDF)
  • Prompt/parameter input with type detection
  • Output format selector: PDF / Excel / CSV / HTML
  • Export & save to disk
  • Open in browser (OpenDocument URL — BI 4.3 port 8080)
  • Run history with status timeline visualisation
  • Per-run AI error analysis
  • Schedule dialog
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
F = Config.FONTS

# ── design tokens ─────────────────────────────────────────────────────────────
BG0    = C["bg_primary"]
BG1    = C["bg_secondary"]
BG2    = C["bg_tertiary"]
CYAN   = "#22d3ee"
BLUE   = C["primary"]
VIOLET = C["secondary"]
GREEN  = C["success"]
AMBER  = C["warning"]
RED    = C["danger"]
TEXT   = C["text_primary"]
TEXT2  = C["text_secondary"]

KIND_META = {
    "Webi":          ("📊", "WebI",    BLUE,   True),
    "CrystalReport": ("💎", "Crystal", VIOLET, False),
    "Excel":         ("📗", "AO",      GREEN,  False),
    "Pdf":           ("📄", "PDF",     RED,    False),
}

_PAGE_REF = [None]

def _bg(fn, cb):
    ref = _PAGE_REF[0]
    def _run():
        try:    res = fn()
        except Exception as e: res = None
        if ref:
            try: ref.after(0, lambda r=res: cb(r))
            except Exception: pass
    threading.Thread(target=_run, daemon=True).start()

def _open_doc_url(report_id):
    try:
        host  = bo_session.base_url.replace("/biprws","").split("://")[-1].split(":")[0]
        token = bo_session.logon_token or ""
        url = (f"http://{host}:8080/BOE/OpenDocument/opendoc/openDocument.jsp"
               f"?iDocID={report_id}&sIDType=InfoObjectID")
        if token:
            url += f"&token={token}"
        return url
    except Exception:
        return None


# ── AI helper ─────────────────────────────────────────────────────────────────
try:
    from ai.gemini_client import GeminiClient
    _ai = GeminiClient()
    HAS_AI = True
except Exception:
    HAS_AI = False


# ─────────────────────────────────────────────────────────────────────────────
#  Schedule dialog
# ─────────────────────────────────────────────────────────────────────────────
class _ScheduleDlg(ctk.CTkToplevel):
    def __init__(self, parent, name):
        super().__init__(parent)
        self.title(f"Schedule — {name[:45]}")
        self.geometry("420x380")
        self.configure(fg_color=BG0)
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="📅  Schedule Report",
                     font=("Segoe UI", 14, "bold"),
                     text_color=CYAN).pack(anchor="w", padx=20, pady=(18,12))
        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=20)

        self._freq = ctk.StringVar(value="Once (immediate)")
        self._fmt  = ctk.StringVar(value="PDF")
        self._dest = ctk.StringVar()

        for lbl, var, opts in [
            ("Frequency",     self._freq,
             ["Once (immediate)","Hourly","Daily","Weekly","Monthly"]),
            ("Output Format", self._fmt, ["PDF","Excel","CSV","HTML"]),
        ]:
            ctk.CTkLabel(form, text=lbl, font=F["small"], text_color=TEXT2
                         ).pack(anchor="w", pady=(10,2))
            ctk.CTkOptionMenu(form, values=opts, variable=var,
                              fg_color=BG2, button_color=BLUE,
                              text_color=TEXT, height=32,
                              font=F["body"]).pack(fill="x")

        ctk.CTkLabel(form, text="Destination (email/folder, optional)",
                     font=F["small"], text_color=TEXT2
                     ).pack(anchor="w", pady=(10,2))
        ctk.CTkEntry(form, textvariable=self._dest, height=32,
                     placeholder_text="user@company.com",
                     fg_color=BG2, border_color=BG2,
                     text_color=TEXT, font=F["body"]).pack(fill="x")

        bar = ctk.CTkFrame(self, fg_color="transparent", height=52)
        bar.pack(fill="x", padx=20, pady=(16,0))
        bar.pack_propagate(False)
        ctk.CTkButton(bar, text="Cancel", width=90, height=36,
                      fg_color=BG2, text_color=TEXT2,
                      command=self.destroy).pack(side="right")
        ctk.CTkButton(bar, text="📅  Schedule", width=120, height=36,
                      fg_color=BLUE, hover_color="#2563eb",
                      font=("Segoe UI", 12, "bold"),
                      command=self._submit).pack(side="right", padx=(0,8))

    def _submit(self):
        self.result = {"frequency": self._freq.get(),
                       "format":    self._fmt.get(),
                       "destination": self._dest.get().strip()}
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
#  Run history / timeline panel
# ─────────────────────────────────────────────────────────────────────────────
class _HistoryPanel(ctk.CTkFrame):
    """Mini instance timeline shown in the run panel."""
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=BG1, corner_radius=8, **kw)
        self._instances = []
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color="transparent", height=28)
        hdr.pack(fill="x", padx=10, pady=(8,2))
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="📈  Run History (last 20)",
                     font=("Segoe UI", 11, "bold"), text_color=TEXT2).pack(side="left")
        self._ai_btn = ctk.CTkButton(hdr, text="🤖 AI", width=60, height=22,
                                      fg_color=VIOLET+"55", text_color=VIOLET,
                                      hover_color=VIOLET, font=("Segoe UI", 9),
                                      command=self._ai_analyse)
        self._ai_btn.pack(side="right")
        self._ai_btn.pack_forget()  # hidden until data loaded

        # Canvas for timeline dots
        self._canvas = tk.Canvas(self, bg=BG1, height=36,
                                  highlightthickness=0)
        self._canvas.pack(fill="x", padx=10, pady=(0,4))

        # Treeview for detail
        outer = ctk.CTkFrame(self, fg_color=BG2, corner_radius=6)
        outer.pack(fill="both", expand=True, padx=8, pady=(0,8))

        sn = f"HP{id(self)}"
        s = ttk.Style()
        s.configure(sn, background=BG2, foreground=TEXT,
                    fieldbackground=BG2, rowheight=26,
                    font=("Segoe UI", 10), borderwidth=0)
        s.configure(f"{sn}.Heading", background=BG0, foreground=TEXT2,
                    font=("Segoe UI", 9, "bold"), relief="flat")
        s.map(sn, background=[("selected", BLUE)], foreground=[("selected","white")])
        s.layout(sn, [("Treeview.treearea", {"sticky":"nswe"})])

        self._tv = ttk.Treeview(outer, style=sn, show="headings",
                                columns=["status","start","end","owner","fmt"],
                                selectmode="browse", height=6)
        for cid, hd, w in [("status","Status",100),("start","Started",145),
                             ("end","Ended",145),("owner","Owner",100),("fmt","Format",70)]:
            self._tv.heading(cid, text=hd)
            self._tv.column(cid, width=w, minwidth=30)
        for st, col in [("ok",GREEN),("fail",RED),("run",AMBER),("pend",TEXT2)]:
            self._tv.tag_configure(st, foreground=col)
        vsb = ctk.CTkScrollbar(outer, orientation="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y", pady=4)
        self._tv.pack(fill="both", expand=True, padx=4, pady=4)

    def load(self, report_id, report_name):
        self._report_name = report_name
        self._canvas.delete("all")
        self._canvas.create_text(30, 18, text="⏳ Loading…",
                                  fill=TEXT2, font=("Segoe UI", 9), anchor="w")
        for row in self._tv.get_children():
            self._tv.delete(row)
        def _fetch():
            return bo_session.get_report_instances(report_id, limit=20)
        _bg(_fetch, self._render)

    def _render(self, insts):
        self._instances = insts or []
        self._canvas.delete("all")
        if not self._instances:
            self._canvas.create_text(10, 18, text="No instance history",
                                      fill=TEXT2, font=("Segoe UI", 9), anchor="w")
            return

        # Timeline dots
        n = len(self._instances)
        for idx, inst in enumerate(self._instances):
            st = inst.get("status","")
            col = (GREEN if "success" in st.lower() else
                   RED   if "fail"    in st.lower() else
                   AMBER if "run"     in st.lower() else TEXT2)
            x = 14 + idx * 22
            self._canvas.create_oval(x-7, 10, x+7, 24, fill=col, outline="")

        # Summary
        ok  = sum(1 for i in self._instances if "success" in i.get("status","").lower())
        fail= sum(1 for i in self._instances if "fail"    in i.get("status","").lower())
        self._canvas.create_text(n*22+20, 17,
                                  text=f"✅{ok}  ❌{fail}",
                                  fill=TEXT2, font=("Segoe UI", 9), anchor="w")

        # Populate treeview
        for row in self._tv.get_children():
            self._tv.delete(row)
        for inst in self._instances:
            st  = inst.get("status","")
            icon = ("✅" if "success" in st.lower() else
                    "❌" if "fail"    in st.lower() else
                    "⏳" if "run"     in st.lower() else "⬜")
            tag = ("ok"   if "success" in st.lower() else
                   "fail" if "fail"    in st.lower() else
                   "run"  if "run"     in st.lower() else "pend")
            self._tv.insert("", "end", tags=(tag,),
                            values=(f"{icon} {st}",
                                    str(inst.get("start_time",""))[:19],
                                    str(inst.get("end_time",""))[:19],
                                    inst.get("owner",""),
                                    inst.get("format","")))

        # Show AI button if failures exist
        if fail > 0:
            self._ai_btn.pack(side="right")
        else:
            self._ai_btn.pack_forget()

    def _ai_analyse(self):
        failed = [i for i in self._instances if "fail" in i.get("status","").lower()]
        if not failed:
            messagebox.showinfo("No failures","No failed instances.", parent=self)
            return
        if not HAS_AI:
            messagebox.showwarning("AI unavailable",
                                   "Gemini AI not configured. Check Settings.",
                                   parent=self)
            return
        win = ctk.CTkToplevel(self)
        win.title("🤖 AI Error Analysis")
        win.geometry("660x500")
        win.configure(fg_color=BG0)
        box = ctk.CTkTextbox(win, font=F["body"], fg_color=BG1,
                              text_color=TEXT, wrap="word")
        box.pack(fill="both", expand=True, padx=16, pady=14)
        box.insert("end", "⏳ Analyzing…")
        box.configure(state="disabled")
        def _run():
            ctx = (
                f"SAP BO BI 4.3 expert. Report: {getattr(self,'_report_name','?')}\n"
                f"Failed instances: {len(failed)}\n"
                f"Details:\n" +
                "\n".join(f"  Start: {i.get('start_time','')} End: {i.get('end_time','')}"
                          for i in failed[:8]) +
                "\n\nList: 1) Likely causes  2) Diagnostic steps  3) Fixes  4) Prevention\n"
                "Plain text, no markdown."
            )
            try:
                res = _ai.ask(ctx)
            except Exception as e:
                res = f"AI error: {e}"
            def _set():
                if win.winfo_exists():
                    box.configure(state="normal")
                    box.delete("1.0","end")
                    box.insert("end", res)
                    box.configure(state="disabled")
            win.after(0, _set)
        threading.Thread(target=_run, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
#  Run panel (right side)
# ─────────────────────────────────────────────────────────────────────────────
class _RunPanel(ctk.CTkScrollableFrame):
    def __init__(self, parent, on_status, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self._on_status  = on_status
        self._report     = None
        self._prompts    = []
        self._prompt_vars= {}
        self._fmt_var    = ctk.StringVar(value="PDF")
        self._show_empty()

    def _show_empty(self):
        for w in self.winfo_children(): w.destroy()
        ctk.CTkLabel(self,
                     text="👈  Select a report\nfrom the list",
                     font=F["body"], text_color=TEXT2,
                     justify="center").pack(expand=True, pady=40)

    def load(self, report):
        self._report = report
        self._prompts = []
        self._prompt_vars = {}
        for w in self.winfo_children(): w.destroy()
        self._build(report)
        if report.get("kind") == "Webi":
            _bg(lambda: bo_session.get_report_prompts(report["id"]),
                self._on_prompts)

    def _build(self, r):
        kind = r.get("kind","")
        icon, short, kcolor, can_run = KIND_META.get(kind, ("📋", kind, TEXT2, False))

        # Report header
        hdr = ctk.CTkFrame(self, fg_color=kcolor+"33", corner_radius=8)
        hdr.pack(fill="x", padx=4, pady=(4,8))
        ctk.CTkLabel(hdr, text=f"{icon}  {r.get('name','')[:50]}",
                     font=("Segoe UI", 13, "bold"), text_color=TEXT,
                     wraplength=280).pack(anchor="w", padx=12, pady=(10,2))
        ctk.CTkLabel(hdr,
                     text=f"{short}   Owner: {r.get('owner','—')}   ID: {r.get('id','—')}",
                     font=("Segoe UI", 9), text_color=TEXT2).pack(anchor="w", padx=12, pady=(0,8))

        def _sec(t):
            ctk.CTkLabel(self, text=t, font=("Segoe UI", 10, "bold"),
                         text_color=TEXT2).pack(anchor="w", padx=8, pady=(10,2))
        def _btn(t, col, cmd, hover=None):
            ctk.CTkButton(self, text=t, height=34, anchor="w",
                          fg_color=col, hover_color=hover or col,
                          text_color="white", font=F["body"],
                          command=cmd).pack(fill="x", padx=4, pady=2)

        # ── Prompts section (WebI only) ────────────────────────────────────
        if kind == "Webi":
            _sec("Parameters")
            self._prompt_frame = ctk.CTkFrame(self, fg_color=BG2, corner_radius=6)
            self._prompt_frame.pack(fill="x", padx=4, pady=(0,4))
            self._prompt_loading = ctk.CTkLabel(
                self._prompt_frame,
                text="⏳ Loading parameters…",
                font=F["small"], text_color=TEXT2)
            self._prompt_loading.pack(pady=10, padx=10, anchor="w")

        # ── Output format ──────────────────────────────────────────────────
        _sec("Output Format")
        fmts = (["PDF","Excel","CSV","HTML"] if kind == "Webi"
                else ["PDF","Excel"]          if kind == "CrystalReport"
                else ["Excel"])
        fmt_row = ctk.CTkFrame(self, fg_color="transparent")
        fmt_row.pack(fill="x", padx=4, pady=(0,6))
        ctk.CTkOptionMenu(fmt_row, values=fmts, variable=self._fmt_var,
                          fg_color=BG2, button_color=BLUE,
                          text_color=TEXT, height=32, width=150,
                          font=F["body"]).pack(side="left")

        # ── Primary actions ────────────────────────────────────────────────
        _sec("Actions")

        if kind == "Webi":
            _btn("▶  Run Report",        BLUE,   self._run, "#2563eb")
            _btn("🌐  Open in Browser",  "#0ea5e9", self._browser, "#0284c7")
            _btn("🖥  Open in Launchpad","#6366f1", self._launchpad,"#4f46e5")
        elif kind == "CrystalReport":
            _btn("🌐  Open in Browser",  VIOLET, self._browser,   "#7c3aed")
            _btn("🖥  Open in Launchpad","#6366f1",self._launchpad,"#4f46e5")
        elif kind in ("Excel","Pdf"):
            _btn("⬇  Download File",     GREEN,  self._download,  "#16a34a")
            _btn("🌐  Open in Launchpad","#0ea5e9",self._launchpad,"#0284c7")

        _sec("Export")
        for fmt, col in [("PDF","#dc2626"),("Excel","#16a34a"),("CSV","#0891b2"),("HTML","#7c3aed")]:
            if kind != "Webi" and fmt in ("CSV","HTML"):
                continue
            _btn(f"⬇  Export {fmt}", col, lambda f=fmt: self._export(f))

        _sec("Manage")
        _btn("📅  Schedule", GREEN,  self._schedule, "#16a34a")

        # ── Instance history ───────────────────────────────────────────────
        _sec("Run History")
        self._history = _HistoryPanel(self)
        self._history.pack(fill="x", padx=4, pady=(0,8))
        self._history.load(r["id"], r.get("name",""))

    def _on_prompts(self, prompts):
        self._prompts = prompts if isinstance(prompts, list) else []
        try:
            if not hasattr(self, "_prompt_frame") or not self._prompt_frame.winfo_exists():
                return
            self._prompt_loading.destroy()
            if not self._prompts:
                ctk.CTkLabel(self._prompt_frame,
                             text="✅  No parameters required",
                             font=F["small"], text_color=GREEN).pack(pady=8, padx=10)
                return
            for p in self._prompts:
                name = p.get("name", p.get("id", str(p)))
                mandatory = p.get("mandatory", True)
                row = ctk.CTkFrame(self._prompt_frame, fg_color="transparent")
                row.pack(fill="x", padx=10, pady=3)
                ctk.CTkLabel(row, text=f"{name}{'*' if mandatory else ''}",
                             width=160, anchor="w", font=F["small"],
                             text_color=TEXT2).pack(side="left")
                var = ctk.StringVar()
                self._prompt_vars[name] = var
                ctk.CTkEntry(row, textvariable=var, height=28,
                             placeholder_text="Enter value…",
                             fg_color=BG0,
                             border_color=BLUE if mandatory else BG2,
                             text_color=TEXT, font=F["small"]).pack(side="left", fill="x", expand=True)
            ctk.CTkFrame(self._prompt_frame, height=6, fg_color="transparent").pack()
        except Exception:
            pass

    # ── Actions ───────────────────────────────────────────────────────────────
    def _run(self):
        if not self._report: return
        vals = {k: v.get().strip() for k, v in self._prompt_vars.items() if v.get().strip()}
        self._on_status("⏳ Running…")
        _bg(lambda: bo_session.run_report_with_prompts(self._report["id"], vals),
            self._on_run_done)

    def _on_run_done(self, res):
        ok  = res[0] if isinstance(res, tuple) else bool(res)
        msg = res[1] if isinstance(res, tuple) and len(res) > 1 else ""
        if ok:
            self._on_status("✅ Run submitted")
            messagebox.showinfo("Success",
                                "✅ Report submitted!\nCheck Instances for output.",
                                parent=self.winfo_toplevel())
            # Reload history
            if self._report and hasattr(self,"_history"):
                self._history.load(self._report["id"], self._report.get("name",""))
        else:
            self._on_status(f"❌ Failed: {msg}")
            messagebox.showerror("Failed", f"❌ Could not run:\n{msg}",
                                 parent=self.winfo_toplevel())

    def _browser(self):
        if not self._report: return
        url = _open_doc_url(self._report["id"])
        if url:
            webbrowser.open(url)
            self._on_status(f"🌐 Opened: {self._report['name']}")
        else:
            messagebox.showwarning("No URL",
                                   "Could not build OpenDocument URL.\n"
                                   "Check server host in Settings.",
                                   parent=self.winfo_toplevel())

    def _launchpad(self):
        if not self._report: return
        try:
            host = bo_session.base_url.replace("/biprws","").split("://")[-1].split(":")[0]
            url = f"http://{host}:8080/BOE/BI?startDocument={self._report['id']}"
            webbrowser.open(url)
            self._on_status(f"🌐 Opened Launchpad: {self._report['name']}")
        except Exception as e:
            messagebox.showwarning("Error", str(e), parent=self.winfo_toplevel())

    def _export(self, fmt):
        if not self._report: return
        ext  = {"PDF":".pdf","Excel":".xlsx","CSV":".csv","HTML":".html"}.get(fmt,".bin")
        name = self._report.get("name","report").replace(" ","_")[:40]
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            title=f"Export {fmt}",
            defaultextension=ext,
            filetypes=[(f"{fmt} File",f"*{ext}")],
            initialfile=f"{name}_{ts}{ext}",
            parent=self.winfo_toplevel())
        if not path: return
        self._on_status(f"⏳ Exporting {fmt}…")
        _bg(lambda: bo_session.export_report(
                self._report["id"], fmt, self._report.get("kind","Webi")),
            lambda r: self._on_export_done(r, path, fmt))

    def _on_export_done(self, data, path, fmt):
        if data:
            try:
                with open(path, "wb" if isinstance(data, bytes) else "w") as f:
                    f.write(data)
                kb = os.path.getsize(path) // 1024
                self._on_status(f"✅ {fmt} saved ({kb} KB): {os.path.basename(path)}")
                messagebox.showinfo("Exported",
                                    f"✅ {fmt} exported!\nFile: {path}\nSize: {kb} KB",
                                    parent=self.winfo_toplevel())
            except Exception as e:
                self._on_status(f"❌ Save error: {e}")
        else:
            self._on_status(f"❌ Export {fmt} failed — server returned no data")
            messagebox.showerror("Export Failed",
                                 f"❌ Could not export as {fmt}.\n"
                                 f"This format may not be supported for this report type.",
                                 parent=self.winfo_toplevel())

    def _download(self):
        if not self._report: return
        kind = self._report.get("kind","")
        self._export("Excel" if kind == "Excel" else "PDF")

    def _schedule(self):
        if not self._report: return
        dlg = _ScheduleDlg(self.winfo_toplevel(), self._report.get("name",""))
        self.winfo_toplevel().wait_window(dlg)
        if not dlg.result: return
        self._on_status("⏳ Scheduling…")
        sc = dlg.result
        _bg(lambda: bo_session.schedule_report(
                self._report["id"],
                schedule_type=sc["frequency"],
                params={"outputFormat": sc["format"], "destination": sc["destination"]}),
            lambda r: (
                self._on_status("✅ Scheduled") if (r[0] if isinstance(r,tuple) else r)
                else self._on_status(f"❌ Schedule failed: {r[1] if isinstance(r,tuple) else r}")
            ))


# ─────────────────────────────────────────────────────────────────────────────
#  Main page
# ─────────────────────────────────────────────────────────────────────────────
class ReportInteractionPage(ctk.CTkFrame):

    _COLS = [
        ("dot",      "●",           22, False),
        ("icon",     "",            22, False),
        ("name",     "Report Name", 250, True),
        ("kind",     "Type",        90,  False),
        ("owner",    "Owner",       100, False),
        ("last_run", "Last Run",    130, False),
    ]

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=BG0, corner_radius=0, **kw)
        _PAGE_REF[0] = self.winfo_toplevel()
        self._reports   = []
        self._destroyed = False
        self._active_type = "All"
        self._build()
        self._load()

    def destroy(self):
        self._destroyed = True
        super().destroy()

    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="▶  Interactive Report Runner",
                     font=("Segoe UI", 18, "bold"),
                     text_color=CYAN).pack(side="left", padx=18)
        self._status_lbl = ctk.CTkLabel(hdr, text="", font=F["small"],
                                         text_color=TEXT2)
        self._status_lbl.pack(side="right", padx=18)
        ctk.CTkButton(hdr, text="⟳  Refresh", width=96, height=30,
                      font=F["small"], fg_color=BG2, hover_color=BG0,
                      command=self._load).pack(side="right", padx=(0,8))

        # Type filter tabs
        tabs = ctk.CTkFrame(self, fg_color=BG1, height=42)
        tabs.pack(fill="x", padx=14, pady=(6,0))
        tabs.pack_propagate(False)
        self._type_btns = {}
        for tid, icon, col in [("All","📋",CYAN),("Webi","📊",BLUE),
                                ("CrystalReport","💎",VIOLET),
                                ("Excel","📗",GREEN),("Pdf","📄",RED)]:
            lbl = "All" if tid=="All" else KIND_META.get(tid,("","??","",False))[1]
            b = ctk.CTkButton(tabs, text=f"{icon} {lbl}",
                              width=96, height=28, corner_radius=6,
                              font=F["small"],
                              fg_color=col if tid=="All" else BG2,
                              hover_color=col, text_color=TEXT,
                              command=lambda t=tid, c=col: self._set_type(t, c))
            b.pack(side="left", padx=3)
            self._type_btns[tid] = (b, col)

        # Search
        sbar = ctk.CTkFrame(self, fg_color="transparent", height=38)
        sbar.pack(fill="x", padx=14, pady=(6,4))
        sbar.pack_propagate(False)
        self._q = ctk.StringVar()
        self._q.trace_add("write", lambda *_: self._filter())
        ctk.CTkEntry(sbar, textvariable=self._q,
                     placeholder_text="🔎  Search by name, owner…",
                     width=300, height=30,
                     fg_color=BG2, border_color=BG2,
                     text_color=TEXT, font=F["body"]).pack(side="left")

        # Body: tree left + run panel right
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=(0,10))

        # Left: treeview
        left = ctk.CTkFrame(body, fg_color=BG1, corner_radius=8, width=480)
        left.pack(side="left", fill="both", expand=True)
        left.pack_propagate(False)

        sn = f"RI{id(self)}"
        s = ttk.Style()
        s.configure(sn, background=BG1, foreground=TEXT,
                    fieldbackground=BG1, rowheight=34,
                    font=("Segoe UI", 11), borderwidth=0)
        s.configure(f"{sn}.Heading", background=BG2, foreground=TEXT2,
                    font=("Segoe UI", 10, "bold"), relief="flat")
        s.map(sn, background=[("selected", BLUE)], foreground=[("selected","white")])
        s.layout(sn, [("Treeview.treearea", {"sticky":"nswe"})])

        self._tv = ttk.Treeview(left, style=sn, show="headings",
                                selectmode="browse",
                                columns=[c[0] for c in self._COLS])
        for cid, hd, w, st in self._COLS:
            self._tv.heading(cid, text=hd)
            self._tv.column(cid, width=w, minwidth=20, stretch=st)
        for tag, col in [("webi",BLUE),("crystal",VIOLET),("ao",GREEN),
                          ("pdf",RED),("other",TEXT2)]:
            self._tv.tag_configure(tag, foreground=col)

        vsb = ctk.CTkScrollbar(left, orientation="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y", padx=(0,4), pady=8)
        self._tv.pack(fill="both", expand=True, padx=8, pady=8)
        self._tv.bind("<<TreeviewSelect>>", self._on_select)
        self._tv.bind("<Double-1>", self._on_double)

        # Right: run panel
        right = ctk.CTkFrame(body, fg_color=BG1, corner_radius=8, width=340)
        right.pack(side="right", fill="y", padx=(10,0))
        right.pack_propagate(False)

        self._run_panel = _RunPanel(right,
                                    on_status=lambda m: self._status_lbl.configure(text=m))
        self._run_panel.pack(fill="both", expand=True, padx=4, pady=4)

    # ── Data ──────────────────────────────────────────────────────────────────
    def _load(self):
        self._status_lbl.configure(text="⏳ Loading…")
        _bg(bo_session.get_all_reports_typed, self._on_loaded)

    def _on_loaded(self, reports):
        if self._destroyed: return
        self._reports = reports or []
        self._filter()
        self._status_lbl.configure(text=f"{len(self._reports)} reports")

    def _set_type(self, tid, col):
        self._active_type = tid
        for t, (b, c) in self._type_btns.items():
            b.configure(fg_color=c if t==tid else BG2)
        self._filter()

    def _filter(self):
        if self._destroyed: return
        q = self._q.get().lower()
        shown = [
            r for r in self._reports
            if (self._active_type=="All" or r.get("kind")==self._active_type)
            and (not q or q in r.get("name","").lower()
                       or q in r.get("owner","").lower())
        ]
        for row in self._tv.get_children():
            self._tv.delete(row)
        for r in shown:
            kind = r.get("kind","")
            meta = KIND_META.get(kind, ("📋", kind, TEXT2, False))
            tag  = {"Webi":"webi","CrystalReport":"crystal",
                    "Excel":"ao","Pdf":"pdf"}.get(kind,"other")
            self._tv.insert("", "end", iid=str(r["id"]), tags=(tag,),
                            values=("●", meta[0],
                                    r.get("name",""), meta[1],
                                    r.get("owner",""),
                                    str(r.get("last_run",""))[:19]))
        self._status_lbl.configure(
            text=f"{len(self._reports)} total  |  {len(shown)} shown")

    def _on_select(self, event=None):
        sel = self._tv.selection()
        if not sel: return
        r = next((x for x in self._reports if str(x["id"])==sel[0]), None)
        if r:
            self._run_panel.load(r)

    def _on_double(self, event=None):
        sel = self._tv.selection()
        if not sel: return
        r = next((x for x in self._reports if str(x["id"])==sel[0]), None)
        if r:
            self._run_panel.load(r)
            if r.get("kind") == "Webi":
                self._run_panel._run()
            else:
                self._run_panel._browser()
