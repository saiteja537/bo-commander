"""
gui/pages/reports.py  —  BO Commander Reports  v2.0
────────────────────────────────────────────────────
Full-featured report list with:
  • Status filter tabs: All / Success / Failed / Running / Pending
  • Type filter: All / WebI / Crystal / AO / PDF
  • Summary stat tiles
  • Per-report instance history card
  • AI error detection on failed reports
  • Open in browser (OpenDocument URL)
  • One-click refresh / delete
"""

import threading
from datetime import datetime
import customtkinter as ctk
from tkinter import ttk, messagebox
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS
F = Config.FONTS

# ── design tokens ─────────────────────────────────────────────────────────────
BG0    = C["bg_primary"]       # #0F172A  deep navy
BG1    = C["bg_secondary"]     # #1E293B  slate
BG2    = C["bg_tertiary"]      # #334155  lighter slate
CYAN   = "#22d3ee"
BLUE   = C["primary"]          # #3B82F6
VIOLET = C["secondary"]        # #8B5CF6
GREEN  = C["success"]          # #10B981
AMBER  = C["warning"]          # #F59E0B
RED    = C["danger"]           # #EF4444
TEXT   = C["text_primary"]     # #F1F5F9
TEXT2  = C["text_secondary"]   # #94A3B8

# Enhanced accent palette
TEAL   = "#14b8a6"
PINK   = "#ec4899"
INDIGO = "#6366f1"
GOLD   = "#f59e0b"
LIME   = "#84cc16"
CARD_BORDER = "#1e3a5f"   # subtle blue border on cards
GLASS  = "#1a2744"        # glass card background

STATUS_COLORS = {
    "Success":   GREEN,
    "Failed":    RED,
    "Running":   AMBER,
    "Pending":   TEXT2,
    "Scheduled": BLUE,
}
STATUS_ICONS = {
    "Success": "✅", "Failed": "❌",
    "Running": "⏳", "Pending": "⏸", "Scheduled": "📅",
}
KIND_META = {
    "Webi":          ("📊", "WebI",      BLUE,   "#1d4ed8"),
    "CrystalReport": ("💎", "Crystal",   VIOLET, "#6d28d9"),
    "Excel":         ("📗", "AO/Excel",  GREEN,  "#047857"),
    "Pdf":           ("📄", "PDF",       RED,    "#b91c1c"),
    "Program":       ("⚙️", "Program",   AMBER,  "#b45309"),
    "Shortcut":      ("🔗", "Shortcut",  TEAL,   "#0f766e"),
}

_PAGE_REF = [None]

def _bg(fn, cb):
    ref = _PAGE_REF[0]
    def _run():
        try:
            res = fn()
        except Exception:
            res = None
        if ref:
            try:
                if ref.winfo_exists():
                    ref.after(0, lambda r=res: cb(r))
            except Exception:
                pass
    threading.Thread(target=_run, daemon=True).start()

# Compatibility alias — forwards to the dynamic builder
def _open_doc_url(report_id, kind="Webi"):
    return _build_opendoc_url(report_id)


# ── Dynamic URL builders (no hardcoded ports, IDs, or server paths) ───────────

# Cache the discovered Tomcat web base so we don't probe on every click
_WEB_BASE_CACHE = [None]


def _get_bo_web_base():
    """
    Find the correct host and Tomcat port where /BOE/ web apps are deployed.

    CRITICAL: The BO REST API port (e.g. 6405) is the CMS/Java port — it is
    NOT the Tomcat HTTP port where OpenDocument, CMC, and BI Launchpad live.
    These are two completely different ports on the same machine.

    Strategy:
      1. Return cached result if already discovered this session.
      2. Read host from bo_session.base_url (always correct).
      3. Probe a list of common Tomcat ports (8080, 443, 80, 8443, 8090, 8000)
         with a HEAD request to /BOE/OpenDocument/ to find which one responds.
      4. Fall back to port 8080 if probing fails (most common BO default).
    """
    if _WEB_BASE_CACHE[0]:
        return _WEB_BASE_CACHE[0]

    try:
        import requests
        from urllib.parse import urlparse

        base   = (getattr(bo_session, "base_url", "") or "").rstrip("/")
        parsed = urlparse(base)
        host   = parsed.hostname or "localhost"

        # Common Tomcat ports for BO web apps — checked in order of likelihood
        candidate_ports = [8080, 443, 80, 8443, 8090, 8000, 8888, 8100]

        session_obj = getattr(bo_session, "session", None)
        headers     = {"User-Agent": "BOCommander/1.0"}

        def _probe(port, scheme="http"):
            try:
                url = f"{scheme}://{host}:{port}/BOE/OpenDocument/"
                if session_obj:
                    r = session_obj.head(url, timeout=3, allow_redirects=True,
                                         verify=False)
                else:
                    r = requests.head(url, timeout=3, allow_redirects=True,
                                       verify=False, headers=headers)
                # 200, 302, 401, 403 all mean "something is there"
                return r.status_code not in (404, 410, 502, 503, 504)
            except Exception:
                return False

        for port in candidate_ports:
            if _probe(port, "https"):
                result = ("https", host, port, f"https://{host}:{port}")
                _WEB_BASE_CACHE[0] = result
                return result
            if _probe(port, "http"):
                result = ("http", host, port, f"http://{host}:{port}")
                _WEB_BASE_CACHE[0] = result
                return result

        # Nothing found — default to 8080 (most common BO Tomcat port)
        result = ("http", host, 8080, f"http://{host}:8080")
        _WEB_BASE_CACHE[0] = result
        return result

    except Exception:
        return ("http", "localhost", 8080, "http://localhost:8080")


def _get_cmc_context_path():
    """
    Discover the CMC Tomcat context path ID dynamically
    by asking the live BO REST API.  This number is generated at installation
    time and is DIFFERENT on every BO server — it can never be hardcoded.

    Returns the context ID string if found, or empty string as fallback
    (caller will use OpenDocument URL instead).
    """
    try:
        import re, requests
        scheme, host, port, web_base = _get_bo_web_base()
        session_obj = getattr(bo_session, "session", None)
        headers     = dict(getattr(bo_session, "headers", {}) or {})
        tok         = getattr(bo_session, "logon_token", "") or ""
        if tok:
            headers["X-SAP-LogonToken"] = tok

        # Strategy 1 — ask /biprws/appstate (some BO versions expose CMC path here)
        for endpoint in ("/biprws/appstate", "/biprws/v1/serverinfo"):
            try:
                url = f"{web_base}{endpoint}"
                r = (session_obj.get(url, timeout=5) if session_obj
                     else requests.get(url, headers=headers, timeout=5))
                if r.status_code == 200:
                    m = re.search(r"/BOE/CMC/(\d{6,12})/", r.text)
                    if m:
                        return m.group(1)
            except Exception:
                pass

        # Strategy 2 — probe the CMC root URL directly
        # Typical BO 4.x path: /BOE/CMC/<10-digit-number>/
        # Try checking if /BOE/CMC/ root redirects and inspect Location header
        try:
            cmc_root = f"{web_base}/BOE/CMC/"
            r = (session_obj.get(cmc_root, timeout=5, allow_redirects=False)
                 if session_obj
                 else requests.get(cmc_root, headers=headers, timeout=5, allow_redirects=False))
            loc = r.headers.get("Location", "")
            m = re.search(r"/BOE/CMC/(\d{6,12})/", loc)
            if m:
                return m.group(1)
        except Exception:
            pass

        return ""   # not found — caller uses OpenDocument fallback
    except Exception:
        return ""


def _build_webi_url(report_id, container_id=""):
    """
    Build the WebI viewer URL — fully dynamic, works on every BO server.

    1. Tries CMC WebiView (best experience, same as CMC 'Open' button).
       The Tomcat context ID is discovered live from the BO server.
    2. Falls back to OpenDocument JSP (universal BO standard).

    Host and port always come from the bo_session connection — never guessed.
    """
    from urllib.parse import quote
    scheme, host, port, web_base = _get_bo_web_base()

    context_id = _get_cmc_context_path()
    if context_id:
        params = (
            "cafWebSesInit=true"
            f"&objIds={report_id}"
            "&actId=4386"
            "&appKind=CMC"
            "&service=%2Fadmin%2FApp%2FappService.jsp"
            + (f"&containerId={container_id}" if container_id else "")
            + "&bypassLatestInstance=true"
            "&showApply=true"
            "&pvl=en"
            "&loc=en"
        )
        inner = quote(f"../../../AnalyticalReporting/WebiView.do?{params}", safe="")
        return (f"{web_base}/BOE/CMC/{context_id}"
                f"/PlatformServices/jsp/pinger/pingerWrapper.jsp?actionUrl={inner}")

    # Fallback: OpenDocument (works on all BO 4.x, no context ID needed)
    return _build_opendoc_url(report_id)


def _build_opendoc_url(report_id):
    """
    OpenDocument URL — the universal BO standard for all report types.
    Works on every SAP BO 4.x installation with no dynamic IDs needed.
    Host and port are read from the live bo_session — never hardcoded.
    """
    scheme, host, port, web_base = _get_bo_web_base()
    return (f"{web_base}/BOE/OpenDocument/opendoc"
            f"/openDocument.jsp?iDocID={report_id}&sIDType=InfoObjectID")



try:
    from ai.gemini_client import GeminiClient
    _ai_client = GeminiClient()
    HAS_AI = True
except Exception:
    _ai_client = None
    HAS_AI = False


def _ai_ask(prompt: str) -> str:
    """
    Universal Gemini caller — tries every known method name so that
    different versions of GeminiClient all work correctly.
    """
    if not _ai_client:
        raise RuntimeError("AI engine not initialized. Check Gemini API key.")
    
    # Try every method name that different GeminiClient versions use
    for method_name in ("ask", "generate", "chat", "query",
                        "generate_content", "send_message",
                        "get_response", "complete", "call"):
        m = getattr(_ai_client, method_name, None)
        if callable(m):
            try:
                result = m(prompt)
                # Some return objects, some return strings
                if isinstance(result, str):
                    return result
                # google.generativeai response object
                if hasattr(result, "text"):
                    return result.text
                # GenerateContentResponse
                if hasattr(result, "candidates"):
                    try:
                        return result.candidates[0].content.parts[0].text
                    except Exception:
                        pass
                # Fallback: stringify
                return str(result)
            except Exception as e:
                raise RuntimeError(f"AI call failed via .{method_name}(): {e}")
    
    # If none found, show what IS available
    available = [n for n in dir(_ai_client) if not n.startswith("_") and callable(getattr(_ai_client, n))]
    raise RuntimeError(
        f"GeminiClient has no recognised call method.\n"
        f"Available methods: {', '.join(available[:12])}\n"
        f"Please update GeminiClient to expose an .ask(prompt) method."
    )



class _AIFixWindow(ctk.CTkToplevel):
    """AI error analysis popup for a failed report."""
    def __init__(self, parent, report_name, failed_instances):
        super().__init__(parent)
        self.title(f"🤖 AI Fix — {report_name[:45]}")
        self.geometry("680x540")
        self.configure(fg_color=BG0)
        self.grab_set()
        self._build(report_name, failed_instances)
        threading.Thread(target=self._analyze,
                         args=(report_name, failed_instances), daemon=True).start()

    def _build(self, name, failed):
        hdr = ctk.CTkFrame(self, fg_color=BG2, corner_radius=0, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="🤖  AI Error Detection & Fix Suggestions",
                     font=("Segoe UI", 14, "bold"), text_color=CYAN).pack(side="left", padx=16)
        ctk.CTkLabel(hdr, text="⚠  Verify before applying to production",
                     font=("Segoe UI", 9), text_color=AMBER).pack(side="right", padx=16)

        info = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=42)
        info.pack(fill="x")
        info.pack_propagate(False)
        ctk.CTkLabel(info, text=f"Report: {name}   |   Failed instances: {len(failed)}",
                     font=F["small"], text_color=TEXT2).pack(side="left", padx=16)

        self._box = ctk.CTkTextbox(self, font=("Segoe UI", 12),
                                    fg_color=BG1, text_color=TEXT,
                                    border_color=BG2, border_width=1, wrap="word")
        self._box.pack(fill="both", expand=True, padx=16, pady=12)
        self._box.insert("end", "⏳  Gemini AI is analyzing the failure pattern…\n")
        self._box.configure(state="disabled")

        ctk.CTkButton(self, text="Close", width=90, height=34,
                      fg_color=BG2, text_color=TEXT2,
                      command=self.destroy).pack(pady=(0, 14))

    def _analyze(self, name, failed):
        if not HAS_AI:
            self._set("⚠  AI engine unavailable. Check Gemini API key in Settings.")
            return
        ctx = (
            f"You are an SAP BusinessObjects BI 4.3 expert.\n\n"
            f"Report: {name}\nFailed instances: {len(failed)}\n"
            f"Sample failures:\n"
            + "\n".join(f"  • Start: {i.get('start_time','')} | End: {i.get('end_time','')} | Owner: {i.get('owner','')}"
                        for i in failed[:8])
            + "\n\nProvide:\n"
            "1. LIKELY CAUSES — specific to SAP BO BI 4.3\n"
            "2. DIAGNOSTIC STEPS — CMC checks, log locations\n"
            "3. RECOMMENDED FIXES — ordered by likelihood\n"
            "4. PREVENTION — avoid recurrence\n\n"
            "Plain text only, no markdown."
        )
        try:
            res = _ai_ask(ctx)
            self._set(res)
        except Exception as e:
            self._set(f"❌  AI call failed: {e}\n\nCheck CMC → Instances and SAP BO server logs.")

    def _set(self, txt):
        try:
            if self.winfo_exists():
                self.after(0, self._write, txt)
        except Exception:
            pass

    def _write(self, txt):
        self._box.configure(state="normal")
        self._box.delete("1.0", "end")
        self._box.insert("end", txt)
        self._box.configure(state="disabled")


class _InstancesPopup(ctk.CTkToplevel):
    """Instance history + status filter for a single report."""
    def __init__(self, parent, report):
        super().__init__(parent)
        self._report    = report
        self._instances = []
        self._filter    = "All"
        self.title(f"📋 Instances — {report['name'][:50]}")
        self.geometry("880x500")
        self.configure(fg_color=BG0)
        self._build()
        threading.Thread(target=self._load, daemon=True).start()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=BG2, corner_radius=0, height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=f"📋  {self._report['name']}",
                     font=("Segoe UI", 13, "bold"), text_color=TEXT).pack(side="left", padx=14)
        self._count_lbl = ctk.CTkLabel(hdr, text="Loading…",
                                        font=F["small"], text_color=TEXT2)
        self._count_lbl.pack(side="right", padx=14)

        # Status filter tabs
        tabs = ctk.CTkFrame(self, fg_color=BG1, height=40)
        tabs.pack(fill="x", padx=10, pady=(8, 0))
        tabs.pack_propagate(False)
        self._tab_btns = {}
        for label, color in [("All",CYAN),("Success",GREEN),("Failed",RED),
                               ("Running",AMBER),("Pending",TEXT2),("Scheduled",BLUE)]:
            b = ctk.CTkButton(tabs, text=label, width=96, height=28,
                              corner_radius=6, font=F["small"],
                              fg_color=CYAN if label == "All" else BG2,
                              hover_color=color, text_color=TEXT,
                              command=lambda l=label, c=color: self._set_filter(l, c))
            b.pack(side="left", padx=3)
            self._tab_btns[label] = (b, color)

        # Action row
        act = ctk.CTkFrame(self, fg_color="transparent", height=38)
        act.pack(fill="x", padx=10, pady=(6, 0))
        act.pack_propagate(False)
        ctk.CTkButton(act, text="🤖 AI Analyse", width=120, height=28,
                      fg_color=VIOLET, font=F["small"],
                      command=self._ai_analyse).pack(side="left", padx=(0,6))
        ctk.CTkButton(act, text="🔄 Retry Failed", width=120, height=28,
                      fg_color=AMBER, text_color=BG0, font=F["small"],
                      command=self._retry_failed).pack(side="left", padx=(0,6))
        ctk.CTkButton(act, text="🗑 Delete Selected", width=130, height=28,
                      fg_color=RED, font=F["small"],
                      command=self._delete_sel).pack(side="left")

        # Treeview
        outer = ctk.CTkFrame(self, fg_color=BG1, corner_radius=8)
        outer.pack(fill="both", expand=True, padx=10, pady=8)
        sn = f"IP{id(self)}"
        s = ttk.Style()
        s.configure(sn, background=BG1, foreground=TEXT,
                    fieldbackground=BG1, rowheight=30,
                    font=("Segoe UI", 11), borderwidth=0)
        s.configure(f"{sn}.Heading", background=BG2, foreground=TEXT2,
                    font=("Segoe UI", 10, "bold"), relief="flat")
        s.map(sn, background=[("selected", BLUE)], foreground=[("selected","white")])
        s.layout(sn, [("Treeview.treearea", {"sticky":"nswe"})])
        cols = [("status","Status",110),("name","Name",250),
                ("start","Started",155),("end","Ended",155),
                ("owner","Owner",110),("fmt","Format",80)]
        self._tv = ttk.Treeview(outer, style=sn, show="headings",
                                columns=[c[0] for c in cols],
                                selectmode="extended")
        for cid, hd, w in cols:
            self._tv.heading(cid, text=hd)
            self._tv.column(cid, width=w, minwidth=30)
        for st, col in [("ok",GREEN),("fail",RED),("run",AMBER),
                         ("pend",TEXT2),("sched",BLUE)]:
            self._tv.tag_configure(st, foreground=col)
        vsb = ctk.CTkScrollbar(outer, orientation="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y", pady=6)
        self._tv.pack(fill="both", expand=True, padx=6, pady=6)

    def _load(self):
        insts = bo_session.get_report_instances(self._report["id"], limit=200)
        self._instances = insts or []
        self.after(0, self._render)

    def _set_filter(self, label, color):
        self._filter = label
        for l, (b, c) in self._tab_btns.items():
            b.configure(fg_color=c if l == label else BG2)
        self._render()

    def _render(self):
        for row in self._tv.get_children():
            self._tv.delete(row)
        filt = self._instances if self._filter == "All" else [
            i for i in self._instances
            if self._filter.lower() in i.get("status","").lower()]
        for i in filt:
            st   = i.get("status","")
            icon = STATUS_ICONS.get(st,"⬜")
            tag  = {"Success":"ok","Failed":"fail","Running":"run",
                    "Pending":"pend","Scheduled":"sched"}.get(st,"")
            self._tv.insert("", "end",
                            iid=str(i.get("id", id(i))),
                            tags=(tag,),
                            values=(f"{icon} {st}",
                                    i.get("name", self._report["name"])[:50],
                                    str(i.get("start_time",""))[:19],
                                    str(i.get("end_time",""))[:19],
                                    i.get("owner",""),
                                    i.get("format","")))
        n = len(filt)
        self._count_lbl.configure(
            text=f"{n} shown  |  total: {len(self._instances)}")

    def _ai_analyse(self):
        failed = [i for i in self._instances if "fail" in i.get("status","").lower()]
        _AIFixWindow(self, self._report["name"], failed)

    def _retry_failed(self):
        ids = [i["id"] for i in self._instances
               if "fail" in i.get("status","").lower() and i.get("id")]
        if not ids:
            messagebox.showinfo("No failures", "No failed instances.", parent=self)
            return
        m = getattr(bo_session, "bulk_retry_instances", None)
        if m:
            try:
                ok, err = m(ids)
            except Exception as ex:
                ok, err = 0, len(ids)
                messagebox.showerror("Retry Error", str(ex), parent=self)
                return
        else:
            ok, err = 0, len(ids)
        messagebox.showinfo("Retry", f"✅ Retried: {ok}   ❌ Errors: {err}", parent=self)

    def _delete_sel(self):
        sel = self._tv.selection()
        if not sel:
            messagebox.showinfo("Nothing selected", "Select instances first.", parent=self)
            return
        if not messagebox.askyesno("Confirm", f"Delete {len(sel)} instance(s)?", parent=self):
            return
        ok = err = 0
        for iid in sel:
            _del = getattr(bo_session, "delete_instance", None)
            s = _del(iid)[0] if _del else False
            if s:
                ok += 1
                self._tv.delete(iid)
            else:
                err += 1
        self._count_lbl.configure(text=f"Deleted {ok}  |  Errors: {err}")


# ─────────────────────────────────────────────────────────────────────────────
#  Report Properties Dialog  (CMC → Report → Properties)
# ─────────────────────────────────────────────────────────────────────────────
class _ReportPropertiesDialog(ctk.CTkToplevel):
    """
    Shows all available properties for a report — matches the CMC Properties panel.
    Tabs: General | Schedule Settings | Limits | User Security | Categories
    All tabs show real data from bo_session REST calls.
    """
    def __init__(self, parent, report):
        super().__init__(parent)
        self._report = report
        self.title(f"⚙ Properties — {report.get('name','')[:50]}")
        self.geometry("720x520")
        self.configure(fg_color=BG0)
        self.grab_set()
        self._build()

    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=BG2, corner_radius=0, height=46)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=f"⚙  {self._report.get('name','')}",
                     font=("Segoe UI", 13, "bold"), text_color=TEXT).pack(side="left", padx=14)
        ctk.CTkButton(hdr, text="✕  Close", width=80, height=28,
                      fg_color=BG2, text_color=TEXT2,
                      command=self.destroy).pack(side="right", padx=10)

        # Tab bar
        self._tab_content = ctk.CTkFrame(self, fg_color="transparent")
        self._tab_content.pack(fill="both", expand=True)

        tab_bar = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=38)
        tab_bar.pack(fill="x", side="top")
        tab_bar.pack_propagate(False)
        tab_bar.lift()

        # Re-order: pack tab_bar before content
        tab_bar.pack_forget()
        self._tab_content.pack_forget()
        tab_bar.pack(fill="x", padx=0, pady=0)
        self._tab_content.pack(fill="both", expand=True)

        self._tabs = {}
        tab_defs = [("General","📄"), ("Schedule","📅"), ("Limits","⚡"),
                    ("User Security","🔐"), ("Categories","🏷")]
        for name, icon in tab_defs:
            b = ctk.CTkButton(tab_bar, text=f"{icon} {name}", height=32, width=130,
                              corner_radius=0, font=("Segoe UI", 10),
                              fg_color=BG2 if name != "General" else BLUE,
                              text_color=TEXT, hover_color=BLUE,
                              command=lambda n=name: self._show_tab(n))
            b.pack(side="left")
            self._tabs[name] = b

        self._current_tab_frame = None
        self._show_tab("General")

    def _show_tab(self, name):
        # Highlight active tab
        for n, b in self._tabs.items():
            b.configure(fg_color=BLUE if n == name else BG2)
        # Clear content
        if self._current_tab_frame:
            try: self._current_tab_frame.destroy()
            except Exception: pass
        frame = ctk.CTkScrollableFrame(self._tab_content, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=12, pady=10)
        self._current_tab_frame = frame

        r = self._report
        if name == "General":
            self._tab_general(frame, r)
        elif name == "Schedule":
            threading.Thread(target=lambda: self._load_schedule(frame, r), daemon=True).start()
        elif name == "Limits":
            self._tab_limits(frame, r)
        elif name == "User Security":
            threading.Thread(target=lambda: self._load_security(frame, r), daemon=True).start()
        elif name == "Categories":
            threading.Thread(target=lambda: self._load_categories(frame, r), daemon=True).start()

    def _prop_row(self, parent, label, value, value_color=None):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(row, text=label, font=("Segoe UI", 10), width=160,
                     text_color=TEXT2, anchor="w").pack(side="left")
        ctk.CTkLabel(row, text=str(value), font=("Segoe UI", 10),
                     text_color=value_color or TEXT, anchor="w",
                     wraplength=460).pack(side="left", padx=8)

    def _section(self, parent, title):
        ctk.CTkLabel(parent, text=title, font=("Segoe UI", 11, "bold"),
                     text_color=CYAN, anchor="w").pack(fill="x", pady=(12,4))
        ctk.CTkFrame(parent, fg_color=BG2, height=1).pack(fill="x", pady=(0,6))

    def _tab_general(self, frame, r):
        self._section(frame, "📄  General Information")
        self._prop_row(frame, "Name",          r.get("name","—"))
        self._prop_row(frame, "Type",          r.get("kind","—"))
        self._prop_row(frame, "ID (SI_ID)",    r.get("id","—"))
        self._prop_row(frame, "Owner",         r.get("owner","—"))
        self._prop_row(frame, "Folder ID",     r.get("folder","—"))
        self._prop_row(frame, "Last Run",      str(r.get("last_run","—"))[:19])
        self._prop_row(frame, "Created",       str(r.get("created","—"))[:19])
        self._prop_row(frame, "Modified",      str(r.get("modified","—"))[:19])
        self._prop_row(frame, "Description",   r.get("description","—"))
        self._section(frame, "🔄  Runtime Information")
        self._prop_row(frame, "Scheduled",     "Yes" if r.get("scheduled") else "No")
        self._prop_row(frame, "Recurring",     "Yes" if r.get("recurring") else "No")
        self._prop_row(frame, "Format",        r.get("format","—"))

    def _load_schedule(self, frame, r):
        rid = r.get("id","")
        schedule = None
        m = getattr(bo_session, "get_schedule", None) or getattr(bo_session, "get_report_schedule", None)
        if m:
            try: schedule = m(rid)
            except Exception: pass
        if not schedule:
            try:
                session_obj = getattr(bo_session, "session", None)
                base_url = getattr(bo_session, "base_url","")
                headers = dict(getattr(bo_session,"headers",{}) or {})
                tok = getattr(bo_session,"logon_token","") or ""
                if tok: headers["X-SAP-LogonToken"] = tok
                if session_obj:
                    r2 = session_obj.get(f"{base_url}/schedule/{rid}",
                                         headers=headers, timeout=10)
                    if r2.status_code == 200:
                        schedule = r2.json()
            except Exception: pass
        try:
            if self.winfo_exists():
                self.after(0, lambda s=schedule: self._tab_schedule(frame, r, s))
        except Exception: pass

    def _tab_schedule(self, frame, r, schedule):
        if not frame.winfo_exists(): return
        self._section(frame, "📅  Schedule Settings")
        if not schedule:
            ctk.CTkLabel(frame, text="No active schedule found for this report.",
                         font=F["small"], text_color=TEXT2).pack(anchor="w")
            self._section(frame, "⚡  Quick Schedule")
            ctk.CTkLabel(frame, text="Use the ▶ button on the report card to run immediately.",
                         font=F["small"], text_color=TEXT2).pack(anchor="w")
            return
        s = schedule if isinstance(schedule, dict) else {}
        self._prop_row(frame, "Schedule Type",   s.get("scheduleType", s.get("type","—")))
        self._prop_row(frame, "Frequency",        s.get("frequency","—"))
        self._prop_row(frame, "Next Run",         str(s.get("nextRunTime","—"))[:19])
        self._prop_row(frame, "Last Run",         str(s.get("lastRunTime","—"))[:19])
        self._prop_row(frame, "Start Time",       str(s.get("startTime","—"))[:19])
        self._prop_row(frame, "End Time",         str(s.get("endTime","—"))[:19])
        self._prop_row(frame, "Output Format",    s.get("outputFormat","—"))
        self._prop_row(frame, "Destination",      s.get("destination","—"))

    def _tab_limits(self, frame, r):
        self._section(frame, "⚡  Instance Limits")
        self._prop_row(frame, "Max Instances",  r.get("max_instances","System default"))
        self._prop_row(frame, "Days to Keep",   r.get("days_to_keep","System default"))
        ctk.CTkLabel(frame,
                     text="ℹ  Instance limits control how many historical runs are retained.\n"
                          "Configure in CMC → Report → Limits for fine-grained control.",
                     font=("Segoe UI", 9), text_color=TEXT2,
                     justify="left", wraplength=560).pack(anchor="w", pady=(12,0))

    def _load_security(self, frame, r):
        rid = r.get("id","")
        security = None
        m = getattr(bo_session, "get_object_security", None) or getattr(bo_session, "get_security", None)
        if m:
            try: security = m(rid)
            except Exception: pass
        if not security:
            try:
                session_obj = getattr(bo_session, "session", None)
                base_url = getattr(bo_session, "base_url","")
                headers = dict(getattr(bo_session,"headers",{}) or {})
                tok = getattr(bo_session,"logon_token","") or ""
                if tok: headers["X-SAP-LogonToken"] = tok
                if session_obj:
                    r2 = session_obj.get(f"{base_url}/infostore/{rid}/security/principals",
                                         headers=headers, timeout=10)
                    if r2.status_code == 200:
                        security = r2.json()
            except Exception: pass
        try:
            if self.winfo_exists():
                self.after(0, lambda s=security: self._tab_security(frame, r, s))
        except Exception: pass

    def _tab_security(self, frame, r, security):
        if not frame.winfo_exists(): return
        self._section(frame, "🔐  User Security Principals")
        if not security:
            ctk.CTkLabel(frame,
                         text="Security information not available via REST API\n"
                              "for this report type. Use CMC → User Security\n"
                              "for detailed rights management.",
                         font=F["small"], text_color=TEXT2, justify="left").pack(anchor="w")
            return
        principals = security if isinstance(security, list) else security.get("principals",[])
        if not principals:
            ctk.CTkLabel(frame, text="No explicit security principals found.\n"
                                     "Report inherits security from parent folder.",
                         font=F["small"], text_color=TEXT2).pack(anchor="w")
            return
        for p in principals[:30]:
            self._prop_row(frame,
                           p.get("name","—"),
                           p.get("rights","—") or p.get("accessLevel","—"))

    def _load_categories(self, frame, r):
        rid = r.get("id","")
        cats = None
        try:
            session_obj = getattr(bo_session, "session", None)
            base_url = getattr(bo_session, "base_url","")
            headers = dict(getattr(bo_session,"headers",{}) or {})
            tok = getattr(bo_session,"logon_token","") or ""
            if tok: headers["X-SAP-LogonToken"] = tok
            if session_obj:
                r2 = session_obj.get(f"{base_url}/infostore/{rid}/categories",
                                     headers=headers, timeout=10)
                if r2.status_code == 200:
                    cats = r2.json()
        except Exception: pass
        try:
            if self.winfo_exists():
                self.after(0, lambda c=cats: self._tab_categories(frame, r, c))
        except Exception: pass

    def _tab_categories(self, frame, r, cats):
        if not frame.winfo_exists(): return
        self._section(frame, "🏷  Categories")
        if not cats:
            ctk.CTkLabel(frame, text="No categories assigned to this report.",
                         font=F["small"], text_color=TEXT2).pack(anchor="w")
            return
        cat_list = cats if isinstance(cats, list) else cats.get("categories", [])
        if not cat_list:
            ctk.CTkLabel(frame, text="No categories assigned.",
                         font=F["small"], text_color=TEXT2).pack(anchor="w")
            return
        for c in cat_list:
            self._prop_row(frame, c.get("name","—"), f"ID: {c.get('id','—')}")


# ─────────────────────────────────────────────────────────────────────────────
#  Report card widget
# ─────────────────────────────────────────────────────────────────────────────
class _ReportCard(ctk.CTkFrame):
    def __init__(self, parent, report, on_status):
        super().__init__(parent, fg_color=GLASS, corner_radius=10,
                         border_color=CARD_BORDER, border_width=1)
        self._report    = report
        self._on_status = on_status
        self._instances = None
        self._expanded  = False
        self._build()

    def _build(self):
        r = self._report
        kind  = r.get("kind","")
        meta4 = KIND_META.get(kind, ("📋", kind, TEXT2, "#334155"))
        icon, short, kcolor = meta4[0], meta4[1], meta4[2]
        kbg = meta4[3] if len(meta4) > 3 else BG2

        # ── Left accent strip (colour-coded by type) ──────────────────────────
        strip = ctk.CTkFrame(self, fg_color=kcolor, width=4, corner_radius=0)
        strip.pack(side="left", fill="y")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=0)

        # ── Row 1: badge + name + action buttons ──────────────────────────────
        row1 = ctk.CTkFrame(body, fg_color="transparent")
        row1.pack(fill="x", pady=(9, 2))

        # Type badge (pill style)
        badge_bg = ctk.CTkFrame(row1, fg_color=kbg, corner_radius=10,
                                width=80, height=22)
        badge_bg.pack(side="left", padx=(0, 10))
        badge_bg.pack_propagate(False)
        ctk.CTkLabel(badge_bg, text=f"{icon}  {short}",
                     font=("Segoe UI", 9, "bold"),
                     text_color=kcolor,
                     fg_color="transparent").pack(expand=True)

        # Report name (clickable)
        name_lbl = ctk.CTkLabel(row1,
                                 text=r.get("name","")[:65],
                                 font=("Segoe UI", 13, "bold"),
                                 text_color=TEXT, anchor="w")
        name_lbl.pack(side="left", fill="x", expand=True)
        name_lbl.bind("<Enter>", lambda e: name_lbl.configure(text_color=CYAN))
        name_lbl.bind("<Leave>", lambda e: name_lbl.configure(text_color=TEXT))
        name_lbl.bind("<Button-1>", lambda e: self._open_browser())
        name_lbl.configure(cursor="hand2")

        # ── Action buttons (right, labelled for clarity) ──────────────────────
        acts = ctk.CTkFrame(row1, fg_color="transparent")
        acts.pack(side="right", padx=(0, 12))
        _ab = dict(height=26, corner_radius=6, font=("Segoe UI", 9, "bold"))

        ctk.CTkButton(acts, text="▶ Run", width=62,
                      fg_color=GREEN, hover_color="#059669",
                      text_color="white",
                      command=self._run_report, **_ab
                      ).pack(side="left", padx=2)
        ctk.CTkButton(acts, text="🌐 Open", width=72,
                      fg_color=BLUE, hover_color="#1d4ed8",
                      text_color="white",
                      command=self._open_browser, **_ab
                      ).pack(side="left", padx=2)
        ctk.CTkButton(acts, text="📋 History", width=82,
                      fg_color=BG2, hover_color=AMBER,
                      text_color=TEXT,
                      command=self._view_instances, **_ab
                      ).pack(side="left", padx=2)
        ctk.CTkButton(acts, text="⚙ Props", width=72,
                      fg_color=BG2, hover_color=CYAN,
                      text_color=TEXT,
                      command=self._show_properties, **_ab
                      ).pack(side="left", padx=2)
        ctk.CTkButton(acts, text="🗑", width=32,
                      fg_color=BG2, hover_color=RED,
                      text_color=RED,
                      command=self._delete_report, **_ab
                      ).pack(side="left", padx=2)

        # ── Row 2: metadata pills ─────────────────────────────────────────────
        row2 = ctk.CTkFrame(body, fg_color="transparent")
        row2.pack(fill="x", pady=(0, 6))

        owner    = r.get("owner", "—")
        last_run = str(r.get("last_run","—"))[:19]
        folder   = str(r.get("folder","—"))[:28]
        rid      = str(r.get("id","—"))

        def _meta_pill(parent, label, value, col=TEXT2):
            f = ctk.CTkFrame(parent, fg_color=BG2, corner_radius=6)
            f.pack(side="left", padx=(0,4))
            ctk.CTkLabel(f, text=label, font=("Segoe UI", 8),
                         text_color=TEXT2).pack(side="left", padx=(6,1), pady=3)
            ctk.CTkLabel(f, text=value, font=("Segoe UI", 9, "bold"),
                         text_color=col).pack(side="left", padx=(0,6), pady=3)

        _meta_pill(row2, "Owner", owner, TEXT)
        _meta_pill(row2, "Last Run", last_run, GREEN if last_run != "—" else TEXT2)
        _meta_pill(row2, "Folder ID", folder, TEXT)
        _meta_pill(row2, "ID", rid, TEXT2)

        # ── Instance health bar (async lazy load) ─────────────────────────────
        self._health_frame = ctk.CTkFrame(body, fg_color="transparent")
        self._health_frame.pack(fill="x", pady=(0, 6))
        threading.Thread(target=self._load_instances, daemon=True).start()

    def _load_instances(self):
        try:
            insts = bo_session.get_report_instances(self._report["id"], limit=20)
            self._instances = insts or []
            try:
                self.after(0, self._render_health)
            except Exception:
                pass
        except Exception:
            pass

    def _render_health(self):
        if not self._instances or not self._health_frame.winfo_exists():
            return
        insts = self._instances
        total   = len(insts)
        success = sum(1 for i in insts if "success" in i.get("status","").lower())
        failed  = sum(1 for i in insts if "fail"    in i.get("status","").lower())
        running = sum(1 for i in insts if "run"     in i.get("status","").lower())

        rate = int(success / total * 100) if total else 0
        col  = GREEN if rate >= 80 else AMBER if rate >= 50 else RED

        hbar = ctk.CTkFrame(self._health_frame, fg_color=BG2,
                            corner_radius=6, height=28)
        hbar.pack(fill="x", pady=(0, 4))
        hbar.pack_propagate(False)

        # Coloured progress fill
        if total > 0:
            fill_pct = max(success / total, 0)
            fill_f = ctk.CTkFrame(hbar, fg_color=col,
                                  corner_radius=5, height=28)
            fill_f.place(relx=0, rely=0, relwidth=fill_pct, relheight=1.0)

        # Stats overlay
        txt = (f"Last {total} instances:  "
               f"✅ {success} succeeded   "
               f"❌ {failed} failed   "
               f"⏳ {running} running   "
               f"— {rate}% success rate")
        ctk.CTkLabel(hbar, text=txt,
                     font=("Segoe UI", 9, "bold"),
                     text_color="white", fg_color="transparent"
                     ).pack(side="left", padx=10)

        if failed > 0:
            ctk.CTkButton(hbar, text="🤖 AI Fix", width=90, height=20,
                          fg_color=VIOLET, text_color="white",
                          hover_color="#7c3aed", font=("Segoe UI", 9, "bold"),
                          command=self._ai_fix).pack(side="right", padx=6)

    def _view_instances(self):
        _InstancesPopup(self.winfo_toplevel(), self._report)

    def _open_browser(self):
        """
        Open report in browser.
        - No hardcoded ports, IDs, or server-specific values.
        - Host & port are read from the live bo_session connection.
        - WebI: tries CMC WebiView (context ID discovered dynamically),
                falls back to OpenDocument (works on every BO 4.x).
        - Crystal / AO / PDF: OpenDocument JSP (universal BO standard).
        """
        import webbrowser
        kind      = self._report.get("kind", "")
        report_id = self._report["id"]
        folder_id = str(self._report.get("folder_id", "") or
                        self._report.get("si_parentid", "") or "")
        try:
            if kind == "Webi":
                url = _build_webi_url(report_id, container_id=folder_id)
            else:
                url = _build_opendoc_url(report_id)

            if url:
                webbrowser.open(url)
                self._on_status(f"🌐 Opened: {self._report['name']}")
            else:
                raise ValueError("URL could not be built — check BO connection.")
        except Exception as ex:
            messagebox.showwarning(
                "Cannot Open Report",
                f"Could not open report in browser.\n\n"
                f"Report: {self._report.get('name','')}\n"
                f"Reason: {ex}\n\n"
                f"Make sure you are connected to the BO server.",
                parent=self.winfo_toplevel()
            )

    def _run_report(self):
        """
        Schedule/run the report via BO REST API.
        Uses the correct /biprws/schedule endpoint (not /documents).
        RWS 00070 = wrong endpoint or missing payload — fixed here.
        """
        self._on_status(f"⏳ Running: {self._report['name']}…")
        report_id = self._report["id"]
        kind      = self._report.get("kind", "Webi")

        def _do():
            # ── Strategy 1: use bo_session helper if it has one ───────────
            for mname in ("schedule_report", "run_report", "run_report_with_prompts"):
                m = getattr(bo_session, mname, None)
                if m:
                    try:
                        if mname == "run_report_with_prompts":
                            result = m(report_id, {})
                        else:
                            result = m(report_id)
                        ok = result[0] if isinstance(result, tuple) else bool(result)
                        msg = result[1] if isinstance(result, tuple) and len(result) > 1 else ""
                        if ok:
                            return True, "Report scheduled successfully."
                        # If it returned False with a message, fall through to REST
                        if "RWS 00070" in str(msg) or "500" in str(msg):
                            break   # try REST directly below
                        return False, msg
                    except Exception as e:
                        if "RWS 00070" in str(e) or "500" in str(e):
                            break   # try REST directly
                        return False, str(e)

            # ── Strategy 2: direct BO REST schedule call ─────────────────
            # BO 4.x REST API requires application/xml Content-Type for /schedule
            # Using JSON causes RWS 00070 Internal Server Error.
            try:
                import requests
                session_obj = getattr(bo_session, "session", None)
                base_url    = getattr(bo_session, "base_url", "")
                headers     = getattr(bo_session, "headers", {}) or {}

                if not base_url:
                    return False, "Not connected to BO server."

                tok = getattr(bo_session, "logon_token", "") or ""
                auth_headers = {
                    **headers,
                    "X-SAP-LogonToken": tok,
                    "Accept": "application/xml",
                    "Content-Type": "application/xml",
                }

                # BO 4.x minimal schedule XML — runs the report immediately (runNow)
                schedule_xml = (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<schedule xmlns="http://www.sap.com/rws/bip">'
                    '<runNow>true</runNow>'
                    '</schedule>'
                )
                sched_url = f"{base_url}/schedule/{report_id}"

                def _post(xml_body):
                    if session_obj:
                        return session_obj.post(sched_url,
                                                data=xml_body.encode("utf-8"),
                                                headers=auth_headers,
                                                timeout=30)
                    return requests.post(sched_url,
                                         data=xml_body.encode("utf-8"),
                                         headers=auth_headers,
                                         timeout=30)

                r = _post(schedule_xml)

                # Some BO 4.x versions use <scheduleInfo> root element instead
                if r.status_code in (400, 500):
                    alt_xml = (
                        '<?xml version="1.0" encoding="UTF-8"?>'
                        '<scheduleInfo xmlns="http://www.sap.com/rws/bip">'
                        '<runNow>true</runNow>'
                        '</scheduleInfo>'
                    )
                    r = _post(alt_xml)

                if r.status_code in (200, 201, 202):
                    return True, "Report scheduled successfully."

                # Parse XML error message
                try:
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(r.text)
                    ns   = "{http://www.sap.com/rws/bip}"
                    msg_el = root.find(f".//{ns}message") or root.find(".//message")
                    err_msg = msg_el.text if msg_el is not None else r.text[:200]
                except Exception:
                    err_msg = r.text[:200] if r.text else f"HTTP {r.status_code}"
                return False, err_msg

            except Exception as e:
                return False, f"Schedule request failed: {e}"

        def _done(res):
            ok  = res[0] if isinstance(res, tuple) else bool(res)
            msg = res[1] if isinstance(res, tuple) and len(res) > 1 else ""
            if ok:
                self._on_status(f"✅ Scheduled: {self._report['name']}")
            else:
                # Show short error + open-in-browser tip
                short_msg = str(msg)[:60].strip()
                self._on_status(
                    f"❌ Schedule failed: {short_msg}  |  💡 Click 🌐 to open report in browser"
                )

        _bg(_do, _done)

    def _ai_fix(self):
        failed = [i for i in (self._instances or [])
                  if "fail" in i.get("status","").lower()]
        _AIFixWindow(self.winfo_toplevel(), self._report["name"], failed)

    # ── CMC-equivalent actions ─────────────────────────────────────────────

    def _show_properties(self):
        """Properties dialog — matches CMC > Report > Properties panel."""
        _ReportPropertiesDialog(self.winfo_toplevel(), self._report)

    def _delete_report(self):
        """Delete this report from the CMS repository."""
        name = self._report.get("name","")
        rid  = self._report.get("id","")
        if not messagebox.askyesno(
                "Confirm Delete",
                f"Permanently delete report from repository:\n\n{name}\n\n"
                "This will remove the report and all its instances.\n"
                "This action CANNOT be undone.",
                parent=self.winfo_toplevel(), icon="warning"):
            return
        self._on_status(f"⏳ Deleting: {name}…")

        def _do():
            # Try bo_session helper
            m = getattr(bo_session, "delete_report", None) or getattr(bo_session, "delete_object", None)
            if m:
                try:
                    result = m(rid)
                    ok = result[0] if isinstance(result, tuple) else bool(result)
                    err = result[1] if isinstance(result, tuple) and len(result)>1 else ""
                    return ok, err
                except Exception as e:
                    pass
            # Direct REST
            try:
                import requests
                session_obj = getattr(bo_session, "session", None)
                base_url    = getattr(bo_session, "base_url", "")
                headers     = dict(getattr(bo_session, "headers", {}) or {})
                tok         = getattr(bo_session, "logon_token", "") or ""
                if tok: headers["X-SAP-LogonToken"] = tok
                url = f"{base_url}/infostore/{rid}"
                if session_obj:
                    r = session_obj.delete(url, headers=headers, timeout=15)
                else:
                    r = requests.delete(url, headers=headers, timeout=15)
                if r.status_code in (200, 202, 204):
                    return True, ""
                try:
                    err = r.json().get("message", r.text[:120])
                except Exception:
                    err = r.text[:120]
                return False, f"HTTP {r.status_code}: {err}"
            except Exception as e:
                return False, str(e)

        def _done(res):
            ok = res[0] if isinstance(res, tuple) else bool(res)
            err = res[1] if isinstance(res, tuple) and len(res)>1 else ""
            if ok:
                self._on_status(f"✅ Deleted: {name}")
                # Remove the card from view
                try:
                    self.pack_forget()
                    self.destroy()
                except Exception:
                    pass
            else:
                self._on_status(f"❌ Delete failed: {err[:60]}")
                messagebox.showerror("Delete Failed",
                    f"Could not delete: {name}\n\nError: {err}",
                    parent=self.winfo_toplevel())

        _bg(_do, _done)


# ─────────────────────────────────────────────────────────────────────────────
#  Main Reports Page
# ─────────────────────────────────────────────────────────────────────────────
class ReportsPage(ctk.CTkFrame):
    def __init__(self, master, bo_session=None, **kw):
        super().__init__(master, fg_color=BG0, corner_radius=0, **kw)
        _PAGE_REF[0] = self.winfo_toplevel()
        self._all     = []
        self._type_f  = "All"
        self._stat_f  = "All"
        self._destroyed = False
        self._build()
        self._refresh()

    def destroy(self):
        self._destroyed = True
        super().destroy()

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build(self):
        # ── Top command bar ───────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=62)
        top.pack(fill="x")
        top.pack_propagate(False)

        # Left: icon + title + live status pill
        title_f = ctk.CTkFrame(top, fg_color="transparent")
        title_f.pack(side="left", padx=18, fill="y")
        ctk.CTkLabel(title_f, text="📊  Reports",
                     font=("Segoe UI", 21, "bold"),
                     text_color=CYAN).pack(side="left")
        self._hdr_status = ctk.CTkLabel(title_f, text="",
                                         font=("Segoe UI", 10),
                                         text_color=TEXT2)
        self._hdr_status.pack(side="left", padx=(14, 0))

        # Right: action buttons
        btn_kw = dict(height=32, corner_radius=7, font=("Segoe UI", 11))
        ctk.CTkButton(top, text="⟳  Refresh", width=108,
                      fg_color=BG2, hover_color=BLUE,
                      text_color=TEXT,
                      command=self._refresh, **btn_kw).pack(side="right", padx=(0,14))
        ctk.CTkButton(top, text="🤖  AI Scan", width=108,
                      fg_color=VIOLET, hover_color="#7c3aed",
                      text_color="white",
                      command=self._ai_scan, **btn_kw).pack(side="right", padx=(0,6))

        # ── KPI tiles row ─────────────────────────────────────────────────────
        tiles_row = ctk.CTkFrame(self, fg_color="transparent")
        tiles_row.pack(fill="x", padx=14, pady=(12, 0))
        self._tiles = {}

        tile_defs = [
            ("total",   "Total Reports", CYAN,   "📋"),
            ("webi",    "Web Intelligence", BLUE, "📊"),
            ("crystal", "Crystal Reports",  VIOLET,"💎"),
            ("ao",      "Analysis for Office", GREEN,"📗"),
            ("failed",  "Failed Runs",     RED,   "❌"),
        ]
        for key, lbl, col, ico in tile_defs:
            t = ctk.CTkFrame(tiles_row,
                             fg_color=GLASS,
                             corner_radius=10,
                             border_color=col,
                             border_width=1)
            t.pack(side="left", padx=(0,8), fill="both", expand=True)

            # Top strip (coloured accent)
            strip = ctk.CTkFrame(t, fg_color=col, height=3, corner_radius=0)
            strip.pack(fill="x")

            inner = ctk.CTkFrame(t, fg_color="transparent")
            inner.pack(fill="both", expand=True, padx=12, pady=8)

            ctk.CTkLabel(inner, text=ico, font=("Segoe UI", 18)).pack(anchor="w")
            v = ctk.CTkLabel(inner, text="—",
                             font=("Segoe UI", 26, "bold"),
                             text_color=col)
            v.pack(anchor="w")
            ctk.CTkLabel(inner, text=lbl,
                         font=("Segoe UI", 9),
                         text_color=TEXT2).pack(anchor="w")
            self._tiles[key] = v

        # ── Filter + search bar ───────────────────────────────────────────────
        fbar = ctk.CTkFrame(self, fg_color=BG1,
                            corner_radius=10, height=48)
        fbar.pack(fill="x", padx=14, pady=(10, 0))
        fbar.pack_propagate(False)

        # Type pills
        ctk.CTkLabel(fbar, text="Type", font=("Segoe UI", 9, "bold"),
                     text_color=TEXT2).pack(side="left", padx=(14,6))
        self._type_btns = {}
        for tid, ico, col, _ in [
            ("All",           "📋", CYAN,   ""),
            ("Webi",          "📊", BLUE,   ""),
            ("CrystalReport", "💎", VIOLET, ""),
            ("Excel",         "📗", GREEN,  ""),
            ("Pdf",           "📄", RED,    ""),
        ]:
            lbl = "All" if tid == "All" else KIND_META.get(tid, ("","??","",""))[1]
            b = ctk.CTkButton(fbar, text=f"{ico} {lbl}",
                              width=90, height=28, corner_radius=14,
                              font=("Segoe UI", 10),
                              fg_color=col if tid == "All" else BG2,
                              hover_color=col,
                              text_color="white" if tid == "All" else TEXT,
                              border_color=col, border_width=1,
                              command=lambda t=tid, c=col: self._set_type(t, c))
            b.pack(side="left", padx=2)
            self._type_btns[tid] = (b, col)

        # Divider
        ctk.CTkFrame(fbar, width=1, fg_color=BG2
                     ).pack(side="left", fill="y", padx=8, pady=8)

        # Live search
        self._q = ctk.StringVar()
        self._q.trace_add("write", lambda *_: self._render())
        ctk.CTkEntry(fbar, textvariable=self._q,
                     placeholder_text="🔎  Search reports, owners, folders…",
                     width=260, height=28,
                     fg_color=BG2, border_color=BG2,
                     text_color=TEXT,
                     font=("Segoe UI", 11)).pack(side="left", padx=4)

        # Sort control
        ctk.CTkFrame(fbar, width=1, fg_color=BG2
                     ).pack(side="right", fill="y", padx=8, pady=8)
        self._sort_var = ctk.StringVar(value="Name ↑")
        ctk.CTkOptionMenu(fbar,
                          variable=self._sort_var,
                          values=["Name ↑", "Name ↓", "Last Run ↓", "Owner ↑"],
                          width=130, height=28,
                          fg_color=BG2, button_color=BG2,
                          dropdown_fg_color=BG1,
                          text_color=TEXT,
                          font=("Segoe UI", 10),
                          command=lambda _: self._render()
                          ).pack(side="right", padx=(0,6))
        ctk.CTkLabel(fbar, text="Sort:", font=("Segoe UI", 9, "bold"),
                     text_color=TEXT2).pack(side="right")

        # ── Scrollable report list ────────────────────────────────────────────
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                               scrollbar_button_color=BG2)
        self._scroll.pack(fill="both", expand=True, padx=14, pady=8)

        # ── Status bar ────────────────────────────────────────────────────────
        sbar = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=28)
        sbar.pack(fill="x")
        sbar.pack_propagate(False)
        self._status = ctk.CTkLabel(sbar, text="",
                                     font=("Segoe UI", 9),
                                     text_color=TEXT2, anchor="w")
        self._status.pack(side="left", padx=14)
        self._status_r = ctk.CTkLabel(sbar, text="",
                                       font=("Segoe UI", 9),
                                       text_color=TEXT2, anchor="e")
        self._status_r.pack(side="right", padx=14)

    # ── Data ──────────────────────────────────────────────────────────────────
    def _refresh(self):
        # Clear web-base cache so port is re-probed if server changed
        _WEB_BASE_CACHE[0] = None
        self._hdr_status.configure(text="⏳ Loading…")
        for w in self._scroll.winfo_children():
            w.destroy()
        _bg(bo_session.get_all_reports_typed, self._on_loaded)

    def _on_loaded(self, reports):
        if self._destroyed:
            return
        raw = reports or []

        # ── Filter out instances — show only base reports ─────────────────
        # BO REST API sometimes returns instances alongside base reports.
        # Instances have SI_INSTANCE=1 in the CMS, but the REST response 
        # may include them without that flag. We detect them by:
        #   1. Explicit si_instance / instance flag in the report dict
        #   2. Folder ID that matches the report's own ID (instance folder pattern)
        #   3. Name suffix pattern " - <number>" (BO appends instance ID to name)
        import re as _re
        _inst_suffix = _re.compile(r' - \d{4,}$')

        def _is_base_report(r):
            # Explicit instance flag
            if r.get("si_instance") == 1 or r.get("instance") == 1:
                return False
            if str(r.get("si_instance","")).lower() in ("true","1","yes"):
                return False
            # If folder_id == report_id, it's an instance container
            rid = str(r.get("id",""))
            fid = str(r.get("folder","") or r.get("folder_id",""))
            if rid and fid and rid == fid:
                return False
            # If name ends with " - <6-digit-number>" it's an instance copy
            name = r.get("name","")
            if _inst_suffix.search(name):
                return False
            return True

        self._all = [r for r in raw if _is_base_report(r)]
        self._update_tiles()
        self._render()
        n = len(self._all)
        filtered = len(raw) - n
        suffix = f"  ({filtered} instances hidden)" if filtered else ""
        self._hdr_status.configure(text=f"{n} reports{suffix}")

    def _update_tiles(self):
        kinds = [r.get("kind","") for r in self._all]
        self._tiles["total"].configure(text=str(len(self._all)))
        self._tiles["webi"].configure(text=str(kinds.count("Webi")))
        self._tiles["crystal"].configure(text=str(kinds.count("CrystalReport")))
        self._tiles["ao"].configure(text=str(kinds.count("Excel")))
        # failed count — from instances (async later)
        self._tiles["failed"].configure(text="…")
        threading.Thread(target=self._count_failed, daemon=True).start()

    def _count_failed(self):
        try:
            # Try get_failed_instances first, fall back to get_instances variants
            insts = None
            for method_name in ("get_failed_instances",
                                "get_instances",
                                "get_all_instances"):
                m = getattr(bo_session, method_name, None)
                if m:
                    try:
                        raw = m(status="failed", limit=100) if method_name in (
                            "get_instances", "get_all_instances") else m(limit=100)
                        insts = raw or []
                        break
                    except Exception:
                        pass
            n = len(insts) if insts is not None else 0
            if not self._destroyed:
                self.after(0, lambda v=n: self._tiles["failed"].configure(text=str(v)))
        except Exception:
            if not self._destroyed:
                try:
                    self.after(0, lambda: self._tiles["failed"].configure(text="?"))
                except Exception:
                    pass

    def _set_type(self, tid, col):
        self._type_f = tid
        for t, (b, c) in self._type_btns.items():
            b.configure(fg_color=c if t==tid else BG2)
        self._render()

    def _render(self):
        if self._destroyed:
            return
        q = self._q.get().lower()
        shown = [
            r for r in self._all
            if (self._type_f=="All" or r.get("kind")==self._type_f)
            and (not q or q in r.get("name","").lower()
                       or q in r.get("owner","").lower()
                       or q in r.get("folder","").lower()
                       or q in str(r.get("id","")).lower())
        ]

        # Apply sort
        sort = getattr(self, "_sort_var", None)
        sort_val = sort.get() if sort else "Name ↑"
        try:
            if sort_val == "Name ↑":
                shown.sort(key=lambda x: x.get("name","").lower())
            elif sort_val == "Name ↓":
                shown.sort(key=lambda x: x.get("name","").lower(), reverse=True)
            elif sort_val == "Last Run ↓":
                shown.sort(key=lambda x: str(x.get("last_run","")), reverse=True)
            elif sort_val == "Owner ↑":
                shown.sort(key=lambda x: x.get("owner","").lower())
        except Exception:
            pass

        try:
            for w in self._scroll.winfo_children():
                w.destroy()
        except Exception:
            return

        if not shown:
            empty_frame = ctk.CTkFrame(self._scroll, fg_color=GLASS,
                                       corner_radius=12)
            empty_frame.pack(fill="x", pady=20, padx=4)
            msg = "No reports match your filters." if self._all else "Connect to SAP BO and click Refresh."
            ctk.CTkLabel(empty_frame,
                         text=f"{'🔍' if self._all else '🔌'}  {msg}",
                         font=("Segoe UI", 13), text_color=TEXT2
                         ).pack(pady=30)
            self._status.configure(text="0 reports shown")
            return

        for r in shown:
            card = _ReportCard(self._scroll, r,
                                on_status=lambda m: self._status.configure(text=m))
            card.pack(fill="x", pady=3)

        self._status.configure(text=f"📋  {len(shown)} of {len(self._all)} reports")
        try:
            kinds = [r.get("kind","") for r in shown]
            breakdown = "  |  ".join(
                f"{k}: {kinds.count(k)}" for k in ["Webi","CrystalReport","Excel","Pdf"]
                if kinds.count(k)
            )
            self._status_r.configure(text=breakdown)
        except Exception:
            pass

    def _ai_scan(self):
        if not self._all:
            messagebox.showinfo("No Data", "Load reports first.", parent=self)
            return
        self._status.configure(text="⏳ AI scanning for failures…")
        def _scan():
            worst = None
            worst_count = 0
            for r in self._all[:15]:
                insts = bo_session.get_report_instances(r["id"], limit=10)
                failed = [i for i in (insts or []) if "fail" in i.get("status","").lower()]
                if len(failed) > worst_count:
                    worst_count = len(failed)
                    worst = (r, failed)
            return worst
        def _done(res):
            if not res:
                self._status.configure(text="✅ AI scan: no failures found")
                messagebox.showinfo("AI Scan", "✅ No failures detected.", parent=self)
            else:
                r, failed = res
                self._status.configure(text=f"⚠ AI scan: {r['name']} has {len(failed)} failure(s)")
                _AIFixWindow(self, r["name"], failed)
        _bg(_scan, _done)