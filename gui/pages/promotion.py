"""
gui/pages/promotion.py  —  BO Commander Promotion Jobs  v3.0
═════════════════════════════════════════════════════════════
Production-grade LCM Promotion management.

Features matching CMC → Promotion Management:
  • List all promotion jobs with Name/Status/Created/Last Run/Source/Destination/Created By
  • Status filter tabs: All / Success / Failed / Running / Scheduled
  • Per-job actions: Edit (rename/view), Promote, RollBack, History, Delete
  • New Job wizard (name + source CMS + destination CMS)
  • Import job from BIAR file
  • Real-time status refresh
  • All REST calls try multiple endpoint paths (BO 4.x has inconsistent LCM URLs)
"""

import threading
import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog
from config import Config
from core.sapbo_connection import bo_session as _bo_session_module

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
GLASS  = "#1a2744"
CARD_BORDER = "#1e3a5f"
TEAL   = "#14b8a6"

STATUS_COLORS = {
    "SUCCESS":   GREEN,
    "COMPLETED": GREEN,
    "FAILED":    RED,
    "ERROR":     RED,
    "RUNNING":   AMBER,
    "INPROGRESS": AMBER,
    "SCHEDULED": BLUE,
    "PENDING":   TEXT2,
    "UNDEFINED": TEXT2,
}
STATUS_ICONS = {
    "SUCCESS": "✅", "COMPLETED": "✅",
    "FAILED": "❌",  "ERROR": "❌",
    "RUNNING": "⏳", "INPROGRESS": "⏳",
    "SCHEDULED": "📅",
    "PENDING": "⏸",
}


# ─────────────────────────────────────────────────────────────────────────────
#  LCM REST API helpers
#  BO 4.x has different LCM endpoint paths depending on patch level.
#  We try them all and use the first that responds.
# ─────────────────────────────────────────────────────────────────────────────

def _lcm_get(path_suffix, params=None):
    """
    Try all known LCM base paths for this BO version.
    Returns (response_or_None, used_base_path).
    """
    session = getattr(_bo_session_module, "session", None)
    base    = (getattr(_bo_session_module, "base_url", "") or "").rstrip("/")
    headers = dict(getattr(_bo_session_module, "headers", {}) or {})
    tok     = getattr(_bo_session_module, "logon_token", "") or ""
    if tok:
        headers["X-SAP-LogonToken"] = tok
    headers.setdefault("Accept", "application/json")

    if not base or not session:
        return None, ""

    # BO 4.x LCM paths — ordered most-common first
    bases = [
        f"{base}/lcm",
        f"{base}/v1/lcm",
        f"{base}/lcm/v1",
        f"{base}",            # some versions put lcm/ directly on base
    ]
    for b in bases:
        try:
            url = f"{b}/{path_suffix.lstrip('/')}"
            r = session.get(url, headers=headers, params=params or {}, timeout=15)
            if r.status_code in (200, 201):
                return r, b
            if r.status_code == 404:
                continue
        except Exception:
            pass
    return None, ""


def _lcm_post(path_suffix, xml_body=None, json_body=None):
    """POST to LCM endpoint, trying all known base paths."""
    session = getattr(_bo_session_module, "session", None)
    base    = (getattr(_bo_session_module, "base_url", "") or "").rstrip("/")
    headers = dict(getattr(_bo_session_module, "headers", {}) or {})
    tok     = getattr(_bo_session_module, "logon_token", "") or ""
    if tok:
        headers["X-SAP-LogonToken"] = tok

    if not base or not session:
        return None, "Not connected"

    if xml_body is not None:
        headers["Content-Type"] = "application/xml"
        headers["Accept"]       = "application/xml"
        body_kwargs = {"data": xml_body.encode("utf-8")}
    else:
        headers["Content-Type"] = "application/json"
        headers["Accept"]       = "application/json"
        body_kwargs = {"json": json_body}

    bases = [f"{base}/lcm", f"{base}/v1/lcm", f"{base}/lcm/v1", base]
    for b in bases:
        try:
            url = f"{b}/{path_suffix.lstrip('/')}"
            r = session.post(url, headers=headers, timeout=30, **body_kwargs)
            if r.status_code in (200, 201, 202, 204):
                return r, ""
            if r.status_code == 404:
                continue
            # Non-404 error — report it but don't try other paths
            try:
                err = r.json().get("message", r.text[:200])
            except Exception:
                err = r.text[:200]
            return r, err
        except Exception as e:
            last_err = str(e)
    return None, last_err if 'last_err' in dir() else "All LCM endpoints failed"


def _lcm_delete(path_suffix):
    """DELETE to LCM endpoint."""
    session = getattr(_bo_session_module, "session", None)
    base    = (getattr(_bo_session_module, "base_url", "") or "").rstrip("/")
    headers = dict(getattr(_bo_session_module, "headers", {}) or {})
    tok     = getattr(_bo_session_module, "logon_token", "") or ""
    if tok:
        headers["X-SAP-LogonToken"] = tok

    if not base or not session:
        return False, "Not connected"

    bases = [f"{base}/lcm", f"{base}/v1/lcm", f"{base}/lcm/v1", base]
    for b in bases:
        try:
            url = f"{b}/{path_suffix.lstrip('/')}"
            r = session.delete(url, headers=headers, timeout=15)
            if r.status_code in (200, 202, 204):
                return True, ""
            if r.status_code == 404:
                continue
        except Exception as e:
            pass
    return False, "Delete failed on all endpoints"


def _fetch_promotion_jobs():
    """
    Fetch all LCM promotion jobs from BO server.
    Tries multiple endpoint patterns used across BO 4.x versions.
    Returns list of normalised job dicts.
    """
    # Try bo_session helper methods first
    for method in ("get_promotion_jobs", "get_lcm_jobs", "get_jobs"):
        m = getattr(_bo_session_module, method, None)
        if m:
            try:
                result = m()
                if result is not None:
                    return _normalise_jobs(result)
            except Exception:
                pass

    # Try all known REST paths directly
    paths = [
        "promotionJobs",
        "jobs",
        "v1/promotionJobs",
    ]
    for path in paths:
        r, _ = _lcm_get(path, params={"offset": 0, "limit": 200})
        if r and r.status_code == 200:
            try:
                data = r.json()
                # Different BO versions use different JSON keys
                for key in ("promotionJobs", "jobs", "lcmJobs", "items"):
                    container = data.get(key)
                    if container:
                        raw = container.get("promotionJob") or container.get("job") or container
                        if isinstance(raw, dict):
                            raw = [raw]
                        if isinstance(raw, list):
                            return _normalise_jobs(raw)
                # Sometimes the list is at root level
                if isinstance(data, list):
                    return _normalise_jobs(data)
            except Exception:
                pass

        # Also try XML response
        if r and r.status_code == 200:
            try:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(r.text)
                ns = "{http://www.sap.com/rws/bip}"
                jobs = []
                for job_el in root.findall(f".//{ns}promotionJob") or root.findall(".//promotionJob"):
                    jobs.append(_parse_xml_job(job_el, ns))
                if jobs:
                    return jobs
            except Exception:
                pass

    return []


def _normalise_jobs(raw_list):
    """Normalise jobs from any API response format to a consistent dict."""
    result = []
    for j in (raw_list or []):
        if not isinstance(j, dict):
            continue
        result.append({
            "id":           str(j.get("id") or j.get("SI_ID") or j.get("jobId", "")),
            "name":         str(j.get("name") or j.get("SI_NAME") or j.get("title", "Unnamed Job")),
            "status":       str(j.get("status") or j.get("SI_STATUS") or j.get("jobStatus", "UNDEFINED")).upper(),
            "created":      str(j.get("creationTime") or j.get("created") or j.get("SI_CREATION_TIME", "")),
            "last_run":     str(j.get("lastRunTime") or j.get("lastRun") or j.get("modifiedAt", "")),
            "source":       str(j.get("sourceSystem") or j.get("source") or j.get("sourceCms", "")),
            "destination":  str(j.get("targetSystem") or j.get("destination") or j.get("destinationCms", "")),
            "created_by":   str(j.get("createdBy") or j.get("owner") or j.get("SI_OWNER", "")),
            "description":  str(j.get("description") or ""),
            "_raw":         j,
        })
    return result


def _parse_xml_job(el, ns):
    def _t(tag):
        child = el.find(f"{ns}{tag}") or el.find(tag)
        return child.text if child is not None else ""
    return _normalise_jobs([{
        "id": _t("id") or el.get("id",""),
        "name": _t("name") or _t("title"),
        "status": _t("status") or _t("jobStatus"),
        "creationTime": _t("creationTime") or _t("created"),
        "lastRunTime": _t("lastRunTime"),
        "sourceSystem": _t("sourceSystem"),
        "targetSystem": _t("targetSystem"),
        "createdBy": _t("createdBy"),
    }])[0]


# ─────────────────────────────────────────────────────────────────────────────
#  Job History popup
# ─────────────────────────────────────────────────────────────────────────────
class _JobHistoryPopup(ctk.CTkToplevel):
    def __init__(self, parent, job):
        super().__init__(parent)
        self._job = job
        self.title(f"📋 History — {job['name'][:50]}")
        self.geometry("800x440")
        self.configure(fg_color=BG0)
        self.grab_set()
        self._build()
        threading.Thread(target=self._load, daemon=True).start()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=BG2, corner_radius=0, height=46)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=f"📋  History: {self._job['name']}",
                     font=("Segoe UI", 13, "bold"), text_color=TEXT).pack(side="left", padx=14)
        ctk.CTkButton(hdr, text="✕ Close", width=80, height=28,
                      fg_color=BG2, text_color=TEXT2,
                      command=self.destroy).pack(side="right", padx=10)

        self._status_lbl = ctk.CTkLabel(self, text="⏳ Loading history…",
                                         font=F["small"], text_color=TEXT2)
        self._status_lbl.pack(anchor="w", padx=14, pady=6)

        outer = ctk.CTkFrame(self, fg_color=BG1, corner_radius=8)
        outer.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        sn = f"JH{id(self)}"
        s = ttk.Style()
        s.configure(sn, background=BG1, foreground=TEXT, fieldbackground=BG1,
                    rowheight=28, font=("Segoe UI", 10), borderwidth=0)
        s.configure(f"{sn}.Heading", background=BG2, foreground=TEXT2,
                    font=("Segoe UI", 10, "bold"), relief="flat")
        s.map(sn, background=[("selected", BLUE)], foreground=[("selected","white")])

        cols = [("status","Status",110),("started","Started",160),("ended","Ended",160),
                ("duration","Duration",90),("user","Promoted By",140)]
        self._tv = ttk.Treeview(outer, style=sn, show="headings",
                                columns=[c[0] for c in cols])
        for cid, hd, w in cols:
            self._tv.heading(cid, text=hd)
            self._tv.column(cid, width=w, minwidth=40)
        for st, col in [("ok",GREEN),("fail",RED),("run",AMBER)]:
            self._tv.tag_configure(st, foreground=col)
        vsb = ctk.CTkScrollbar(outer, orientation="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y", pady=6)
        self._tv.pack(fill="both", expand=True, padx=6, pady=6)

    def _load(self):
        history = []
        jid = self._job["id"]
        r, _ = _lcm_get(f"promotionJobs/{jid}/history")
        if not r:
            r, _ = _lcm_get(f"jobs/{jid}/history")
        if r and r.status_code == 200:
            try:
                data = r.json()
                history = data.get("history", data.get("runs", data if isinstance(data, list) else []))
            except Exception:
                pass
        try:
            if self.winfo_exists():
                self.after(0, lambda h=history: self._render(h))
        except Exception:
            pass

    def _render(self, history):
        if not self.winfo_exists():
            return
        if not history:
            self._status_lbl.configure(text="No history records found for this job.")
            return
        self._status_lbl.configure(text=f"{len(history)} history record(s)")
        for h in history:
            st = str(h.get("status","")).upper()
            tag = "ok" if "SUCCESS" in st or "COMPLETE" in st else "fail" if "FAIL" in st or "ERROR" in st else "run"
            icon = STATUS_ICONS.get(st, "⬜")
            self._tv.insert("", "end", tags=(tag,), values=(
                f"{icon} {st}",
                str(h.get("startTime") or h.get("started",""))[:19],
                str(h.get("endTime") or h.get("ended",""))[:19],
                str(h.get("duration","—")),
                str(h.get("promotedBy") or h.get("user","—")),
            ))


# ─────────────────────────────────────────────────────────────────────────────
#  New Job / Edit Job dialog
# ─────────────────────────────────────────────────────────────────────────────
class _JobDialog(ctk.CTkToplevel):
    """Create or edit a promotion job."""
    def __init__(self, parent, on_saved, job=None):
        super().__init__(parent)
        self._on_saved = on_saved
        self._job = job   # None = new job
        mode = "Edit Job" if job else "New Promotion Job"
        self.title(f"{'✏️' if job else '＋'} {mode}")
        self.geometry("540x360")
        self.configure(fg_color=BG0)
        self.grab_set()
        self._build(job)

    def _build(self, job):
        hdr = ctk.CTkFrame(self, fg_color=BG2, corner_radius=0, height=46)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        title = f"✏️  Edit Job" if job else "＋  New Promotion Job"
        ctk.CTkLabel(hdr, text=title, font=("Segoe UI", 13, "bold"),
                     text_color=CYAN).pack(side="left", padx=14)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=16)

        def _row(label, default="", placeholder=""):
            ctk.CTkLabel(body, text=label, font=F["small"],
                         text_color=TEXT2, anchor="w").pack(fill="x", pady=(8,2))
            e = ctk.CTkEntry(body, height=32, font=("Segoe UI", 12),
                             fg_color=BG2, text_color=TEXT,
                             placeholder_text=placeholder)
            e.pack(fill="x")
            if default:
                e.insert(0, default)
            return e

        self._name_entry = _row("Job Name *",
                                 default=job["name"] if job else "",
                                 placeholder="e.g. Promote_Finance_Reports")
        self._src_entry  = _row("Source CMS  (host:port)",
                                 default=job.get("source","") if job else "",
                                 placeholder="e.g. localhost:6400")
        self._dst_entry  = _row("Destination CMS  (host:port)",
                                 default=job.get("destination","") if job else "",
                                 placeholder="e.g. prod-server:6400")

        self._err_lbl = ctk.CTkLabel(body, text="", font=F["small"], text_color=RED)
        self._err_lbl.pack(anchor="w", pady=(6,0))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(btn_row, text="✓  Save", width=110, height=32,
                      fg_color=BLUE, command=self._save).pack(side="right")
        ctk.CTkButton(btn_row, text="✕  Cancel", width=90, height=32,
                      fg_color=BG2, text_color=TEXT2,
                      command=self.destroy).pack(side="right", padx=6)

    def _save(self):
        name = self._name_entry.get().strip()
        src  = self._src_entry.get().strip()
        dst  = self._dst_entry.get().strip()
        if not name:
            self._err_lbl.configure(text="⚠  Job name is required.")
            return

        payload = {"name": name, "sourceSystem": src, "targetSystem": dst}
        self.after(0, lambda: self._err_lbl.configure(text="⏳ Saving…"))

        def _do():
            if self._job:
                jid = self._job["id"]
                xml = (f'<?xml version="1.0" encoding="UTF-8"?>'
                       f'<promotionJob xmlns="http://www.sap.com/rws/bip">'
                       f'<name>{name}</name>'
                       f'<sourceSystem>{src}</sourceSystem>'
                       f'<targetSystem>{dst}</targetSystem>'
                       f'</promotionJob>')
                r, err = _lcm_post(f"promotionJobs/{jid}", xml_body=xml)
                if not r:
                    # Try JSON
                    r, err = _lcm_post(f"promotionJobs/{jid}", json_body=payload)
            else:
                xml = (f'<?xml version="1.0" encoding="UTF-8"?>'
                       f'<promotionJob xmlns="http://www.sap.com/rws/bip">'
                       f'<name>{name}</name>'
                       f'<sourceSystem>{src}</sourceSystem>'
                       f'<targetSystem>{dst}</targetSystem>'
                       f'</promotionJob>')
                r, err = _lcm_post("promotionJobs", xml_body=xml)
                if not r:
                    r, err = _lcm_post("jobs", json_body=payload)
            return r, err

        def _done(res):
            r, err = res
            if r and r.status_code in (200, 201, 202, 204):
                try:
                    if self.winfo_exists():
                        self.destroy()
                except Exception:
                    pass
                self._on_saved()
            else:
                try:
                    if self.winfo_exists():
                        self._err_lbl.configure(
                            text=f"⚠  Save failed: {err[:80]}\n"
                                 f"Note: Job creation requires LCM configuration in CMC first."
                        )
                except Exception:
                    pass

        threading.Thread(target=lambda: self.after(0, lambda: _done(_do())),
                         daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
#  Job card widget
# ─────────────────────────────────────────────────────────────────────────────
class _JobCard(ctk.CTkFrame):
    def __init__(self, parent, job, on_refresh, on_status):
        super().__init__(parent, fg_color=GLASS, corner_radius=10,
                         border_color=CARD_BORDER, border_width=1)
        self._job        = job
        self._on_refresh = on_refresh
        self._on_status  = on_status
        self._build()

    def _build(self):
        j = self._job
        st    = j.get("status","UNDEFINED").upper()
        color = STATUS_COLORS.get(st, TEXT2)
        icon  = STATUS_ICONS.get(st, "⬜")

        # ── Left accent strip ─────────────────────────────────────────────────
        strip = ctk.CTkFrame(self, fg_color=color, width=4, corner_radius=0)
        strip.pack(side="left", fill="y")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(side="left", fill="both", expand=True, padx=12, pady=10)

        # ── Row 1: job icon + name + status badge ─────────────────────────────
        row1 = ctk.CTkFrame(body, fg_color="transparent")
        row1.pack(fill="x")

        # Status badge (pill)
        badge_bg = ctk.CTkFrame(row1, fg_color=color, corner_radius=10,
                                 width=96, height=22)
        badge_bg.pack(side="left", padx=(0,10))
        badge_bg.pack_propagate(False)
        ctk.CTkLabel(badge_bg, text=f"{icon}  {st}",
                     font=("Segoe UI", 9, "bold"),
                     text_color="white", fg_color="transparent").pack(expand=True)

        # Job name
        ctk.CTkLabel(row1, text=f"📦  {j['name']}",
                     font=("Segoe UI", 13, "bold"),
                     text_color=TEXT, anchor="w").pack(side="left", fill="x", expand=True)

        # ── Row 2: metadata pills ─────────────────────────────────────────────
        row2 = ctk.CTkFrame(body, fg_color="transparent")
        row2.pack(fill="x", pady=(6, 0))

        def _pill(parent, label, value, col=TEXT):
            f = ctk.CTkFrame(parent, fg_color=BG2, corner_radius=6)
            f.pack(side="left", padx=(0,4))
            ctk.CTkLabel(f, text=label, font=("Segoe UI", 8),
                         text_color=TEXT2).pack(side="left", padx=(6,2), pady=3)
            ctk.CTkLabel(f, text=str(value)[:32], font=("Segoe UI", 9, "bold"),
                         text_color=col).pack(side="left", padx=(0,6), pady=3)

        _pill(row2, "Source",  j.get("source","—"),      CYAN)
        _pill(row2, "→",       j.get("destination","—"),  GREEN)
        _pill(row2, "Created", j.get("created","—")[:16], TEXT2)
        _pill(row2, "Last Run",j.get("last_run","—")[:16],color)
        _pill(row2, "By",      j.get("created_by","—"),   TEXT)

        # ── Action buttons (horizontal strip) ─────────────────────────────────
        row3 = ctk.CTkFrame(body, fg_color="transparent")
        row3.pack(fill="x", pady=(8, 0))

        _b = dict(height=28, corner_radius=7, font=("Segoe UI", 10, "bold"))

        ctk.CTkButton(row3, text="▶ Promote", width=100,
                      fg_color=GREEN, hover_color="#059669", text_color="white",
                      command=self._promote, **_b).pack(side="left", padx=(0,4))
        ctk.CTkButton(row3, text="↩ RollBack", width=100,
                      fg_color=AMBER, hover_color="#d97706", text_color="white",
                      command=self._rollback, **_b).pack(side="left", padx=(0,4))
        ctk.CTkButton(row3, text="📋 History", width=96,
                      fg_color=BG2, hover_color=BLUE, text_color=TEXT,
                      command=self._history, **_b).pack(side="left", padx=(0,4))
        ctk.CTkButton(row3, text="✏️ Edit", width=76,
                      fg_color=BG2, hover_color=CYAN, text_color=TEXT,
                      command=self._edit, **_b).pack(side="left", padx=(0,4))
        ctk.CTkButton(row3, text="🗑 Delete", width=90,
                      fg_color=BG2, hover_color=RED, text_color=RED,
                      command=self._delete, **_b).pack(side="left")

    # ── Actions ───────────────────────────────────────────────────────────────
    def _promote(self):
        jid  = self._job["id"]
        name = self._job["name"]
        if not messagebox.askyesno("Confirm Promote",
                f"Promote job:\n{name}\n\n"
                f"Source:  {self._job.get('source','?')}\n"
                f"Target:  {self._job.get('destination','?')}\n\n"
                "This will copy objects to the destination system. Continue?",
                parent=self.winfo_toplevel()):
            return
        self._on_status(f"⏳ Promoting: {name}…")

        def _do():
            # Try promote endpoint
            xml = ('<?xml version="1.0" encoding="UTF-8"?>'
                   '<promotionJob xmlns="http://www.sap.com/rws/bip">'
                   '<action>promote</action></promotionJob>')
            r, err = _lcm_post(f"promotionJobs/{jid}/promote", xml_body=xml)
            if not r:
                r, err = _lcm_post(f"jobs/{jid}/promote", xml_body=xml)
            if not r:
                r, err = _lcm_post(f"promotionJobs/{jid}/actions/promote",
                                    json_body={"action": "promote"})
            return r, err

        def _done(res):
            r, err = res
            if r and r.status_code in (200, 201, 202):
                self._on_status(f"✅ Promotion started: {name}")
                self._on_refresh()
            else:
                self._on_status(f"❌ Promote failed: {err[:80]}")
                messagebox.showerror("Promote Failed",
                    f"Could not promote job:\n{name}\n\nError: {err}\n\n"
                    "Note: Some BO environments require that LCM is fully configured\n"
                    "with source/destination credentials before promoting via REST API.\n"
                    "You can also promote via CMC → Promotion Management.",
                    parent=self.winfo_toplevel())

        threading.Thread(target=lambda: self.after(0, lambda: _done(_do())),
                         daemon=True).start()

    def _rollback(self):
        jid  = self._job["id"]
        name = self._job["name"]
        if not messagebox.askyesno("Confirm RollBack",
                f"Roll back job:\n{name}\n\n"
                "This will revert objects on the destination system.\n"
                "This action cannot be undone easily. Continue?",
                parent=self.winfo_toplevel(),
                icon="warning"):
            return
        self._on_status(f"⏳ Rolling back: {name}…")

        def _do():
            xml = ('<?xml version="1.0" encoding="UTF-8"?>'
                   '<promotionJob xmlns="http://www.sap.com/rws/bip">'
                   '<action>rollback</action></promotionJob>')
            r, err = _lcm_post(f"promotionJobs/{jid}/rollback", xml_body=xml)
            if not r:
                r, err = _lcm_post(f"jobs/{jid}/rollback", xml_body=xml)
            return r, err

        def _done(res):
            r, err = res
            if r and r.status_code in (200, 201, 202):
                self._on_status(f"✅ Rollback started: {name}")
                self._on_refresh()
            else:
                self._on_status(f"❌ Rollback failed: {err[:80]}")

        threading.Thread(target=lambda: self.after(0, lambda: _done(_do())),
                         daemon=True).start()

    def _history(self):
        _JobHistoryPopup(self.winfo_toplevel(), self._job)

    def _edit(self):
        _JobDialog(self.winfo_toplevel(), on_saved=self._on_refresh, job=self._job)

    def _delete(self):
        name = self._job["name"]
        if not messagebox.askyesno("Confirm Delete",
                f"Delete promotion job:\n{name}\n\nThis cannot be undone.",
                parent=self.winfo_toplevel(), icon="warning"):
            return
        jid = self._job["id"]
        self._on_status(f"⏳ Deleting: {name}…")

        def _do():
            ok, err = _lcm_delete(f"promotionJobs/{jid}")
            if not ok:
                ok, err = _lcm_delete(f"jobs/{jid}")
            return ok, err

        def _done(res):
            ok, err = res
            if ok:
                self._on_status(f"✅ Deleted: {name}")
                self._on_refresh()
            else:
                self._on_status(f"❌ Delete failed: {err[:60]}")

        threading.Thread(target=lambda: self.after(0, lambda: _done(_do())),
                         daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
#  Main Promotion Page
# ─────────────────────────────────────────────────────────────────────────────
class PromotionPage(ctk.CTkFrame):
    def __init__(self, master, bo_session=None, **kwargs):
        super().__init__(master, fg_color=BG0, corner_radius=0, **kwargs)
        self._destroyed   = False
        self._all_jobs    = []
        self._active_filter = "All"
        self._build()
        self._refresh()

    # ── lifecycle guard ───────────────────────────────────────────────────────
    def destroy(self):
        self._destroyed = True
        super().destroy()

    def _safe_ui(self, fn, *args):
        if self._destroyed:
            return
        try:
            if self.winfo_exists():
                fn(*args)
        except Exception:
            pass

    # ── UI build ─────────────────────────────────────────────────────────────
    def _build(self):
        # ── Top command bar ───────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=62)
        top.pack(fill="x")
        top.pack_propagate(False)

        title_f = ctk.CTkFrame(top, fg_color="transparent")
        title_f.pack(side="left", padx=18, fill="y")
        ctk.CTkLabel(title_f, text="📦  Promotion Jobs",
                     font=("Segoe UI", 21, "bold"),
                     text_color=CYAN).pack(side="left")
        self._status_lbl = ctk.CTkLabel(title_f, text="",
                                         font=("Segoe UI", 10),
                                         text_color=TEXT2)
        self._status_lbl.pack(side="left", padx=(14, 0))

        btn_kw = dict(height=32, corner_radius=7, font=("Segoe UI", 11))
        ctk.CTkButton(top, text="⟳  Refresh", width=108,
                      fg_color=BG2, hover_color=BLUE, text_color=TEXT,
                      command=self._refresh, **btn_kw).pack(side="right", padx=(0,14))
        ctk.CTkButton(top, text="📂  Import BIAR", width=128,
                      fg_color=BG2, hover_color=VIOLET, text_color=TEXT,
                      command=self._import_biar, **btn_kw).pack(side="right", padx=(0,6))
        ctk.CTkButton(top, text="＋  New Job", width=118,
                      fg_color=GREEN, hover_color="#059669", text_color="white",
                      command=self._new_job, **btn_kw).pack(side="right", padx=(0,6))

        # ── KPI summary tiles ─────────────────────────────────────────────────
        self._kpi_row = ctk.CTkFrame(self, fg_color="transparent")
        self._kpi_row.pack(fill="x", padx=14, pady=(12,0))
        self._kpi_tiles = {}
        for key, lbl, col, ico in [
            ("total",    "Total Jobs",    CYAN,  "📦"),
            ("success",  "Successful",    GREEN, "✅"),
            ("failed",   "Failed",        RED,   "❌"),
            ("running",  "Running",       AMBER, "⏳"),
            ("scheduled","Scheduled",     BLUE,  "📅"),
        ]:
            t = ctk.CTkFrame(self._kpi_row, fg_color=GLASS,
                             corner_radius=10, border_color=col, border_width=1)
            t.pack(side="left", padx=(0,8), fill="both", expand=True)
            ctk.CTkFrame(t, fg_color=col, height=3, corner_radius=0).pack(fill="x")
            inner = ctk.CTkFrame(t, fg_color="transparent")
            inner.pack(fill="both", expand=True, padx=12, pady=8)
            ctk.CTkLabel(inner, text=ico, font=("Segoe UI", 18)).pack(anchor="w")
            v = ctk.CTkLabel(inner, text="—",
                             font=("Segoe UI", 26, "bold"), text_color=col)
            v.pack(anchor="w")
            ctk.CTkLabel(inner, text=lbl, font=("Segoe UI", 9),
                         text_color=TEXT2).pack(anchor="w")
            self._kpi_tiles[key] = v

        # ── Status filter pills ───────────────────────────────────────────────
        filt_frame = ctk.CTkFrame(self, fg_color=BG1, corner_radius=10, height=48)
        filt_frame.pack(fill="x", padx=14, pady=10)
        filt_frame.pack_propagate(False)

        ctk.CTkLabel(filt_frame, text="Filter", font=("Segoe UI", 9, "bold"),
                     text_color=TEXT2).pack(side="left", padx=(14,6))

        self._filter_btns = {}
        for label, color in [("All", CYAN), ("Success", GREEN), ("Failed", RED),
                               ("Running", AMBER), ("Scheduled", BLUE)]:
            b = ctk.CTkButton(filt_frame, text=label, width=90, height=28,
                              corner_radius=14, font=("Segoe UI", 10),
                              fg_color=CYAN if label == "All" else BG2,
                              text_color="white" if label == "All" else TEXT,
                              hover_color=color, border_color=color, border_width=1,
                              command=lambda lbl=label, c=color: self._set_filter(lbl, c))
            b.pack(side="left", padx=3)
            self._filter_btns[label] = (b, color)

        self._count_lbl = ctk.CTkLabel(filt_frame, text="",
                                        font=("Segoe UI", 9), text_color=TEXT2)
        self._count_lbl.pack(side="right", padx=14)

        # ── Scroll area ───────────────────────────────────────────────────────
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                               scrollbar_button_color=BG2)
        self._scroll.pack(fill="both", expand=True, padx=14, pady=(0,8))

        # ── Status bar ────────────────────────────────────────────────────────
        sbar = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=28)
        sbar.pack(fill="x")
        sbar.pack_propagate(False)
        self._sbar_lbl = ctk.CTkLabel(sbar, text="",
                                       font=("Segoe UI", 9),
                                       text_color=TEXT2, anchor="w")
        self._sbar_lbl.pack(side="left", padx=14)

        # Initial placeholder
        ctk.CTkLabel(self._scroll, text="⏳  Loading promotion jobs…",
                     font=("Segoe UI", 13), text_color=TEXT2).pack(pady=60)

    # ── Filter ────────────────────────────────────────────────────────────────
    def _set_filter(self, label, color):
        self._active_filter = label
        for lbl, (b, c) in self._filter_btns.items():
            if lbl == label:
                b.configure(fg_color=c, text_color=BG0)
            else:
                b.configure(fg_color=BG2, text_color=TEXT)
        self._render_jobs()

    # ── Data loading ─────────────────────────────────────────────────────────
    def _refresh(self):
        self._status_lbl.configure(text="⏳ Fetching…")
        threading.Thread(target=self._fetch_thread, daemon=True).start()

    def _fetch_thread(self):
        jobs = _fetch_promotion_jobs()
        if not self._destroyed:
            try:
                self.after(0, lambda j=jobs: self._on_loaded(j))
            except Exception:
                pass

    def _on_loaded(self, jobs):
        self._safe_ui(self._do_load, jobs)

    def _do_load(self, jobs):
        self._all_jobs = jobs
        n = len(jobs)
        self._status_lbl.configure(text=f"{n} job{'s' if n != 1 else ''} found")
        # Update KPI tiles
        try:
            statuses = [j.get("status","").upper() for j in jobs]
            def _cnt(*vals): return sum(1 for s in statuses if s in vals)
            self._kpi_tiles["total"].configure(text=str(n))
            self._kpi_tiles["success"].configure(text=str(_cnt("SUCCESS","COMPLETED")))
            self._kpi_tiles["failed"].configure(text=str(_cnt("FAILED","ERROR")))
            self._kpi_tiles["running"].configure(text=str(_cnt("RUNNING","INPROGRESS")))
            self._kpi_tiles["scheduled"].configure(text=str(_cnt("SCHEDULED","PENDING")))
        except Exception:
            pass
        self._render_jobs()

    # ── Render ────────────────────────────────────────────────────────────────
    def _clear_scroll(self):
        if self._destroyed:
            return
        try:
            if self._scroll.winfo_exists():
                for w in self._scroll.winfo_children():
                    try:
                        w.destroy()
                    except Exception:
                        pass
        except Exception:
            pass

    def _render_jobs(self):
        if self._destroyed:
            return
        self._clear_scroll()

        filt = self._active_filter
        if filt == "All":
            visible = self._all_jobs
        else:
            visible = [j for j in self._all_jobs
                       if j.get("status","").upper() == filt.upper()
                       or (filt == "Success" and j.get("status","").upper() in ("SUCCESS","COMPLETED"))
                       or (filt == "Failed"  and j.get("status","").upper() in ("FAILED","ERROR"))
                       or (filt == "Running" and j.get("status","").upper() in ("RUNNING","INPROGRESS"))]

        self._count_lbl.configure(text=f"{len(visible)} shown / {len(self._all_jobs)} total")

        if not visible:
            msg = ("No promotion jobs found.\n\n"
                   "Make sure you have created promotion jobs in\n"
                   "CMC → Promotion Management, or click  ＋ New Job  above."
                   if filt == "All" else
                   f"No {filt.lower()} promotion jobs.")
            ctk.CTkLabel(self._scroll, text=msg, font=("Segoe UI", 13),
                         text_color=TEXT2, justify="center").pack(pady=60)
            return

        for job in visible:
            card = _JobCard(self._scroll, job,
                            on_refresh=self._refresh,
                            on_status=self._set_status)
            card.pack(fill="x", padx=4, pady=4)

    # ── Status bar helper ─────────────────────────────────────────────────────
    def _set_status(self, msg):
        try:
            if not self._destroyed and self.winfo_exists():
                self._status_lbl.configure(text=msg)
                if hasattr(self, "_sbar_lbl"):
                    self._sbar_lbl.configure(text=msg)
        except Exception:
            pass

    # ── Toolbar actions ───────────────────────────────────────────────────────
    def _new_job(self):
        _JobDialog(self.winfo_toplevel(), on_saved=self._refresh)

    def _import_biar(self):
        """Import a BIAR file as a new promotion job."""
        path = filedialog.askopenfilename(
            title="Select BIAR File",
            filetypes=[("BIAR files", "*.biar"), ("All files", "*.*")],
            parent=self.winfo_toplevel()
        )
        if not path:
            return
        self._set_status(f"⏳ Importing: {path.split('/')[-1]}…")

        def _do():
            try:
                with open(path, "rb") as f:
                    file_data = f.read()
                session = getattr(_bo_session_module, "session", None)
                base    = (getattr(_bo_session_module, "base_url", "") or "").rstrip("/")
                headers = dict(getattr(_bo_session_module, "headers", {}) or {})
                tok     = getattr(_bo_session_module, "logon_token", "") or ""
                if tok:
                    headers["X-SAP-LogonToken"] = tok

                if not session:
                    return False, "Not connected to BO server"

                import os
                fname = os.path.basename(path)
                for b in [f"{base}/lcm", f"{base}/v1/lcm", base]:
                    try:
                        url = f"{b}/promotionJobs/import"
                        r = session.post(url, files={"file": (fname, file_data, "application/octet-stream")},
                                          headers=headers, timeout=60)
                        if r.status_code in (200, 201, 202):
                            return True, ""
                        if r.status_code == 404:
                            continue
                        try:
                            err = r.json().get("message", r.text[:200])
                        except Exception:
                            err = r.text[:200]
                        return False, err
                    except Exception as e:
                        pass
                return False, "Import endpoint not found. Try importing via CMC → Promotion Management."
            except Exception as e:
                return False, str(e)

        def _done(res):
            ok, err = res
            if ok:
                self._set_status(f"✅ BIAR imported successfully")
                self._refresh()
            else:
                self._set_status(f"❌ Import failed: {err[:80]}")
                messagebox.showerror("Import Failed",
                    f"Could not import BIAR file.\n\nError: {err}",
                    parent=self.winfo_toplevel())

        threading.Thread(target=lambda: self.after(0, lambda: _done(_do())),
                         daemon=True).start()