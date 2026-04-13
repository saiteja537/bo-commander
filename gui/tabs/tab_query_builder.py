"""
gui/tabs/tab_query_builder.py  —  Query Builder + License Keys
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Two sub-panels in one tab (switched via header buttons):

  🔍 CMS Query Builder
     • 30+ templates across 8 categories
     • AI natural language → CMS SQL  (Gemini)
     • Results treeview with row/timing counter
     • Export Excel + charts

  🔑 License Keys
     • Live CMS data via bo_session.get_license_keys()
     • Summary tiles: Total / Active / Expired
     • Per-license detail cards with expiry highlighting

New file — add to bo_commander.py TABS list:
    ("🔍  Query Builder",
     _safe_import("gui.tabs.tab_query_builder", "QueryBuilderTab")),
"""

import time
import threading
import customtkinter as ctk
from tkinter import ttk, messagebox

from gui.tabs._base import *
from core.sapbo_connection import bo_session

# ── Gemini AI for NL query generation ────────────────────────────────────────
try:
    from ai.gemini_client import GeminiClient as _GC
    _QB_AI     = _GC()
    _QB_HAS_AI = True
except Exception:
    _QB_AI     = None
    _QB_HAS_AI = False


def _ai_to_cms_query(text: str) -> str:
    if not _QB_AI:
        raise RuntimeError("AI not available — add GEMINI_API_KEY to .env")
    prompt = (
        "You are an SAP BusinessObjects CMS SQL expert.\n"
        "Convert the user's plain English request into a valid CMS SQL query.\n\n"
        "CMS SQL RULES:\n"
        "- Tables: CI_INFOOBJECTS (reports/folders), "
        "CI_SYSTEMOBJECTS (users/servers/groups), "
        "CI_APPOBJECTS (universes/connections)\n"
        "- Reports: SI_KIND IN ('Webi','CrystalReport','Deski') AND SI_INSTANCE=0\n"
        "- Instances: SI_INSTANCE=1, states: 1=Pending 2=Running 3=Failed 4=Success\n"
        "- Users: SI_PROGID='crystalenterprise.user'\n"
        "- Servers: SI_PROGID='crystalenterprise.server'\n"
        "- Always include TOP N (max 500)\n"
        "OUTPUT ONLY the SQL — no explanation, no markdown, no backticks.\n\n"
        f"User request: {text}\n\nCMS SQL:"
    )
    for m_name in ("get_response","ask","generate","chat",
                   "query","generate_content"):
        m = getattr(_QB_AI, m_name, None)
        if callable(m):
            try:
                r = m(prompt)
                return (r.text if hasattr(r,"text") else str(r)).strip()
            except Exception as e:
                raise RuntimeError(f"AI call failed: {e}")
    raise RuntimeError("No usable AI method found on GeminiClient.")


# ── Template library ──────────────────────────────────────────────────────────
TEMPLATES = {
    "System / Infrastructure": {
        "All Servers Status": (
            "SELECT SI_ID, SI_NAME, SI_KIND, SI_SERVER_IS_ALIVE,\n"
            "       SI_TOTAL_NUM_FAILURES, SI_SERVER_HOST\n"
            "FROM CI_SYSTEMOBJECTS\n"
            "WHERE SI_PROGID = 'crystalenterprise.server'\n"
            "ORDER BY SI_NAME ASC"),
        "Failed Servers": (
            "SELECT SI_NAME, SI_SERVER_IS_ALIVE, SI_TOTAL_NUM_FAILURES,\n"
            "       SI_SERVER_HOST\n"
            "FROM CI_SYSTEMOBJECTS\n"
            "WHERE SI_PROGID = 'crystalenterprise.server'\n"
            "AND (SI_SERVER_IS_ALIVE = 0 OR SI_TOTAL_NUM_FAILURES > 0)\n"
            "ORDER BY SI_TOTAL_NUM_FAILURES DESC"),
        "Infrastructure Health Scan": (
            "SELECT SI_NAME, SI_SERVER_IS_ALIVE,\n"
            "       SI_TOTAL_NUM_FAILURES, SI_SERVER_HOST\n"
            "FROM CI_SYSTEMOBJECTS\n"
            "WHERE SI_PROGID = 'crystalenterprise.server'\n"
            "ORDER BY SI_TOTAL_NUM_FAILURES DESC"),
        "License Information": (
            "SELECT TOP 20 SI_ID, SI_NAME, SI_KIND, SI_DESCRIPTION\n"
            "FROM CI_SYSTEMOBJECTS\n"
            "WHERE SI_KIND LIKE '%License%'\n"
            "ORDER BY SI_NAME ASC"),
        "CMS Version & Build": (
            "SELECT SI_ID, SI_NAME, SI_KIND, SI_DESCRIPTION\n"
            "FROM CI_SYSTEMOBJECTS\n"
            "WHERE SI_KIND = 'Server' AND SI_NAME LIKE '%CMS%'"),
        "Auditing Status": (
            "SELECT SI_ID, SI_NAME, SI_SERVER_IS_ALIVE, SI_DESCRIPTION\n"
            "FROM CI_SYSTEMOBJECTS\n"
            "WHERE SI_KIND = 'Server' AND SI_NAME LIKE '%Audit%'"),
    },
    "Users & Groups": {
        "All Enterprise Users": (
            "SELECT TOP 500 SI_ID, SI_NAME, SI_FULL_NAME,\n"
            "       SI_DISABLED, SI_AUTH_TYPE, SI_UPDATE_TS\n"
            "FROM CI_SYSTEMOBJECTS\n"
            "WHERE SI_PROGID = 'crystalenterprise.user'\n"
            "ORDER BY SI_NAME ASC"),
        "Disabled Users": (
            "SELECT TOP 200 SI_ID, SI_NAME, SI_FULL_NAME, SI_AUTH_TYPE\n"
            "FROM CI_SYSTEMOBJECTS\n"
            "WHERE SI_PROGID = 'crystalenterprise.user'\n"
            "AND SI_DISABLED = 1 ORDER BY SI_NAME ASC"),
        "All Groups": (
            "SELECT TOP 200 SI_ID, SI_NAME, SI_DESCRIPTION\n"
            "FROM CI_SYSTEMOBJECTS\n"
            "WHERE SI_KIND = 'Usergroup' ORDER BY SI_NAME ASC"),
        "Inactive / Dormant Users": (
            "SELECT TOP 100 SI_ID, SI_NAME, SI_FULL_NAME,\n"
            "       SI_LAST_LOGIN_TIME, SI_CREATION_TIME\n"
            "FROM CI_SYSTEMOBJECTS\n"
            "WHERE SI_PROGID = 'crystalenterprise.user'\n"
            "ORDER BY SI_LAST_LOGIN_TIME ASC"),
        "LDAP / AD Users": (
            "SELECT TOP 200 SI_ID, SI_NAME, SI_FULL_NAME, SI_AUTH_TYPE\n"
            "FROM CI_SYSTEMOBJECTS\n"
            "WHERE SI_PROGID = 'crystalenterprise.user'\n"
            "AND SI_AUTH_TYPE <> 'secEnterprise'\n"
            "ORDER BY SI_AUTH_TYPE, SI_NAME ASC"),
        "Recently Modified Users": (
            "SELECT TOP 50 SI_ID, SI_NAME, SI_FULL_NAME, SI_UPDATE_TS\n"
            "FROM CI_SYSTEMOBJECTS\n"
            "WHERE SI_PROGID = 'crystalenterprise.user'\n"
            "ORDER BY SI_UPDATE_TS DESC"),
    },
    "Reports & Universes": {
        "All Webi Reports": (
            "SELECT TOP 200 SI_ID, SI_NAME, SI_OWNER,\n"
            "       SI_CREATION_TIME, SI_UPDATE_TS\n"
            "FROM CI_INFOOBJECTS\n"
            "WHERE SI_KIND = 'Webi' AND SI_INSTANCE = 0\n"
            "ORDER BY SI_NAME ASC"),
        "All Crystal Reports": (
            "SELECT TOP 200 SI_ID, SI_NAME, SI_OWNER,\n"
            "       SI_CREATION_TIME, SI_UPDATE_TS\n"
            "FROM CI_INFOOBJECTS\n"
            "WHERE SI_KIND = 'CrystalReport' AND SI_INSTANCE = 0\n"
            "ORDER BY SI_NAME ASC"),
        "All Reports (All Types)": (
            "SELECT TOP 300 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_UPDATE_TS\n"
            "FROM CI_INFOOBJECTS\n"
            "WHERE SI_KIND IN ('Webi','CrystalReport','Deski','FullClient')\n"
            "AND SI_INSTANCE = 0 ORDER BY SI_UPDATE_TS DESC"),
        "Reports Not Run in 90 Days": (
            "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_UPDATE_TS\n"
            "FROM CI_INFOOBJECTS\n"
            "WHERE SI_KIND IN ('Webi','CrystalReport','Deski')\n"
            "AND SI_INSTANCE = 0 ORDER BY SI_UPDATE_TS ASC"),
        "All Universes (UNV + UNX)": (
            "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_DESCRIPTION\n"
            "FROM CI_APPOBJECTS\n"
            "WHERE SI_KIND LIKE '%Universe%' OR SI_KIND = 'DSL.MetaDataFile'\n"
            "ORDER BY SI_NAME ASC"),
        "Content Ownership Mapping": (
            "SELECT TOP 300 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_CREATION_TIME\n"
            "FROM CI_INFOOBJECTS\n"
            "WHERE SI_INSTANCE = 0\n"
            "AND SI_KIND IN ('Webi','CrystalReport','Deski')\n"
            "ORDER BY SI_OWNER ASC"),
    },
    "Scheduling & Instances": {
        "All Scheduled Reports": (
            "SELECT TOP 200 SI_ID, SI_NAME, SI_KIND, SI_OWNER,\n"
            "       SI_PROCESSINFO.SI_NEXTRUNTIME, SI_STARTTIME\n"
            "FROM CI_INFOOBJECTS WHERE SI_SCHEDULE = 1\n"
            "ORDER BY SI_NAME ASC"),
        "Failed Instances (Last 100)": (
            "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER,\n"
            "       SI_STARTTIME, SI_ENDTIME\n"
            "FROM CI_INFOOBJECTS\n"
            "WHERE SI_INSTANCE = 1 AND SI_PROCESSINFO.SI_STATE = 3\n"
            "ORDER BY SI_STARTTIME DESC"),
        "Pending Instances": (
            "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_STARTTIME\n"
            "FROM CI_INFOOBJECTS\n"
            "WHERE SI_INSTANCE = 1 AND SI_PROCESSINFO.SI_STATE = 1\n"
            "ORDER BY SI_STARTTIME ASC"),
        "All Running Instances": (
            "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_STARTTIME\n"
            "FROM CI_INFOOBJECTS\n"
            "WHERE SI_INSTANCE = 1 AND SI_PROCESSINFO.SI_STATE = 2\n"
            "ORDER BY SI_STARTTIME DESC"),
        "Zombie Schedule Detector": (
            "SELECT TOP 200 SI_ID, SI_NAME, SI_KIND, SI_OWNER,\n"
            "       SI_PROCESSINFO.SI_NEXTRUNTIME, SI_STARTTIME\n"
            "FROM CI_INFOOBJECTS\n"
            "WHERE SI_SCHEDULE = 1 AND SI_INSTANCE = 0\n"
            "ORDER BY SI_PROCESSINFO.SI_NEXTRUNTIME ASC"),
        "Oldest Instances (Cleanup)": (
            "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER,\n"
            "       SI_STARTTIME, SI_ENDTIME\n"
            "FROM CI_INFOOBJECTS WHERE SI_INSTANCE = 1\n"
            "ORDER BY SI_STARTTIME ASC"),
    },
    "Folders & Structure": {
        "All Folders": (
            "SELECT TOP 200 SI_ID, SI_NAME, SI_PARENTID, SI_DESCRIPTION\n"
            "FROM CI_INFOOBJECTS WHERE SI_KIND = 'Folder'\n"
            "ORDER BY SI_NAME ASC"),
        "Top-Level Folders": (
            "SELECT TOP 100 SI_ID, SI_NAME, SI_DESCRIPTION\n"
            "FROM CI_INFOOBJECTS\n"
            "WHERE SI_KIND = 'Folder' AND SI_PARENTID = 23\n"
            "ORDER BY SI_NAME ASC"),
        "All Database Connections": (
            "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_DESCRIPTION\n"
            "FROM CI_APPOBJECTS WHERE SI_KIND LIKE '%Connection%'\n"
            "ORDER BY SI_NAME ASC"),
        "Folders by Owner": (
            "SELECT TOP 200 SI_ID, SI_NAME, SI_OWNER, SI_CREATION_TIME\n"
            "FROM CI_INFOOBJECTS WHERE SI_KIND = 'Folder'\n"
            "ORDER BY SI_OWNER, SI_NAME ASC"),
    },
    "Security & Audit": {
        "Recent Audit Events": (
            "SELECT TOP 200 SI_ID, SI_NAME,\n"
            "       SI_AUDIT_INFO.SI_AUDIT_EVTNAME AS Event,\n"
            "       SI_AUDIT_INFO.SI_AUDIT_USERNAME AS AuditUser,\n"
            "       SI_AUDIT_INFO.SI_AUDIT_STARTTIME AS AuditTime\n"
            "FROM CI_INFOOBJECTS WHERE SI_KIND='AuditEvent'\n"
            "ORDER BY SI_AUDIT_INFO.SI_AUDIT_STARTTIME DESC"),
        "Active User Sessions": (
            "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_DESCRIPTION\n"
            "FROM CI_SYSTEMOBJECTS WHERE SI_KIND = 'LogonToken'\n"
            "ORDER BY SI_NAME ASC"),
        "Security Groups with Members": (
            "SELECT TOP 200 SI_ID, SI_NAME, SI_DESCRIPTION\n"
            "FROM CI_SYSTEMOBJECTS WHERE SI_KIND = 'Usergroup'\n"
            "ORDER BY SI_NAME ASC"),
    },
    "Repository Health": {
        "Broken Objects": (
            "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_UPDATE_TS\n"
            "FROM CI_INFOOBJECTS\n"
            "WHERE SI_INSTANCE = 0\n"
            "AND SI_KIND IN ('Webi','CrystalReport')\n"
            "AND SI_STATUSINFO <> 0 ORDER BY SI_UPDATE_TS DESC"),
        "Orphan Instances": (
            "SELECT TOP 200 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_STARTTIME\n"
            "FROM CI_INFOOBJECTS WHERE SI_INSTANCE = 1\n"
            "AND SI_PROCESSINFO.SI_STATE IN (1, 2)\n"
            "AND SI_STARTTIME < '2024-01-01 00:00:00'\n"
            "ORDER BY SI_STARTTIME ASC"),
        "LCM Promotion Jobs": (
            "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_CREATION_TIME\n"
            "FROM CI_INFOOBJECTS\n"
            "WHERE SI_KIND IN ('LcmJob','PromotionJob')\n"
            "ORDER BY SI_CREATION_TIME DESC"),
    },
    "Connections & Data Sources": {
        "All Database Connections": (
            "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_DESCRIPTION\n"
            "FROM CI_APPOBJECTS WHERE SI_KIND = 'Connection'\n"
            "ORDER BY SI_NAME ASC"),
        "All UNX Universes": (
            "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER\n"
            "FROM CI_APPOBJECTS WHERE SI_KIND = 'DSL.MetaDataFile'\n"
            "ORDER BY SI_NAME ASC"),
        "All UNV Universes": (
            "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER\n"
            "FROM CI_APPOBJECTS WHERE SI_KIND = 'Universe'\n"
            "ORDER BY SI_NAME ASC"),
        "OLAP / BW Connections": (
            "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_DESCRIPTION\n"
            "FROM CI_APPOBJECTS\n"
            "WHERE SI_KIND LIKE '%OLAP%' OR SI_KIND LIKE '%BW%'\n"
            "ORDER BY SI_NAME ASC"),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Main tab (two sub-panels)
# ─────────────────────────────────────────────────────────────────────────────

class QueryBuilderTab(BaseTab):

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._last_result:   list | None = None
        self._query_history: list        = []
        self._panel_frames:  list        = []
        self._panel_btns:    list        = []
        self._build()

    # ── Header ────────────────────────────────────────────────────────────────

    def _build(self):
        rf = self._page_header("Query Builder & License Keys", "🔍",
                                "CMS SQL queries • AI generator • License info")

        for i, (lbl, col) in enumerate([
            ("🔍 CMS Query Builder", BLUE),
            ("🔑 License Keys",      VIOLET),
        ]):
            btn = ctk.CTkButton(
                rf, text=lbl, width=165, height=30,
                fg_color=col if i == 0 else BG2,
                text_color="white" if i == 0 else TEXT2,
                font=F_SM,
                command=lambda p=i: self._switch(p))
            btn.pack(side="right", padx=3)
            self._panel_btns.append(btn)

        # Stacked panels share body grid slot 0,0
        body = self._body
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        for _ in range(2):
            f = ctk.CTkFrame(body, fg_color="transparent")
            f.grid(row=0, column=0, sticky="nsew")
            self._panel_frames.append(f)

        self._build_qb(self._panel_frames[0])
        self._build_lic(self._panel_frames[1])
        self._switch(0)

    def _switch(self, idx: int):
        for i, f in enumerate(self._panel_frames):
            if i == idx:
                f.tkraise()
            self._panel_btns[i].configure(
                fg_color=[BLUE, VIOLET][i] if i == idx else BG2,
                text_color="white" if i == idx else TEXT2)
        if idx == 1:
            self._lic_load()

    # ══════════════════════════════════════════════════════════════════════════
    # PANEL 0 — CMS QUERY BUILDER
    # ══════════════════════════════════════════════════════════════════════════

    def _build_qb(self, parent: ctk.CTkFrame):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(3, weight=1)

        # ── Template pickers ──────────────────────────────────────────────────
        pick = ctk.CTkFrame(parent, fg_color="transparent")
        pick.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 4))

        ctk.CTkLabel(pick, text="Category:", font=F_SM,
                     text_color=TEXT2).pack(side="left", padx=(0, 4))

        self._cat_var = ctk.StringVar(value=list(TEMPLATES.keys())[0])
        ctk.CTkOptionMenu(
            pick, variable=self._cat_var,
            values=list(TEMPLATES.keys()), width=230,
            fg_color=BG2, button_color=BG2,
            dropdown_fg_color=BG1, text_color=TEXT, font=F_SM,
            command=self._on_cat_change,
        ).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(pick, text="Template:", font=F_SM,
                     text_color=TEXT2).pack(side="left", padx=(0, 4))

        first_cat = list(TEMPLATES.keys())[0]
        self._tmpl_var = ctk.StringVar(value=list(TEMPLATES[first_cat].keys())[0])
        self._tmpl_menu = ctk.CTkOptionMenu(
            pick, variable=self._tmpl_var,
            values=list(TEMPLATES[first_cat].keys()), width=240,
            fg_color=BG2, button_color=BG2,
            dropdown_fg_color=BG1, text_color=TEXT, font=F_SM,
            command=self._on_tmpl_change)
        self._tmpl_menu.pack(side="left")

        self._qb_status = ctk.CTkLabel(pick, text="", font=F_XS, text_color=TEXT2)
        self._qb_status.pack(side="right", padx=10)

        # ── AI natural-language strip ──────────────────────────────────────────
        nl = ctk.CTkFrame(parent, fg_color=BG1, corner_radius=8)
        nl.grid(row=1, column=0, sticky="ew", padx=14, pady=4)

        nl_top = ctk.CTkFrame(nl, fg_color="transparent")
        nl_top.pack(fill="x", padx=12, pady=(8, 4))
        ctk.CTkLabel(nl_top,
                     text="🤖  Natural Language → CMS SQL  (AI-Powered)",
                     font=("Segoe UI",11,"bold"), text_color=CYAN
                     ).pack(side="left")
        if not _QB_HAS_AI:
            ctk.CTkLabel(nl_top,
                         text="⚠ Add GEMINI_API_KEY to .env",
                         font=F_XS, text_color=AMBER
                         ).pack(side="right")

        nl_row = ctk.CTkFrame(nl, fg_color="transparent")
        nl_row.pack(fill="x", padx=12, pady=(0, 8))

        self._nl_entry = ctk.CTkEntry(
            nl_row,
            placeholder_text=(
                "e.g.  show failed webi reports  |  "
                "users not logged in 90 days  |  zombie schedules"),
            fg_color=BG2, border_color=BG2, text_color=TEXT,
            font=F_BODY, height=32)
        self._nl_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._nl_entry.bind("<Return>", lambda e: self._nl_generate())

        self._nl_btn = ctk.CTkButton(
            nl_row, text="✨ Generate", width=120, height=32,
            fg_color="#6366f1" if _QB_HAS_AI else BG2,
            text_color="white" if _QB_HAS_AI else TEXT2,
            state="normal" if _QB_HAS_AI else "disabled",
            command=self._nl_generate)
        self._nl_btn.pack(side="right")

        # ── Action buttons ─────────────────────────────────────────────────────
        acts = ctk.CTkFrame(parent, fg_color="transparent")
        acts.grid(row=2, column=0, sticky="ew", padx=14, pady=(4, 2))

        ctk.CTkButton(acts, text="▶ Run Query", width=120, height=32,
                      fg_color=BLUE, font=F_SM,
                      command=self._run_query).pack(side="left", padx=(0, 6))
        ctk.CTkButton(acts, text="⬇ Export Excel", width=135, height=32,
                      fg_color=GREEN, text_color=BG0, font=F_SM,
                      command=self._export).pack(side="left", padx=(0, 6))
        ctk.CTkButton(acts, text="✕ Clear", width=80, height=32,
                      fg_color=BG2, text_color=TEXT2, font=F_SM,
                      command=self._clear).pack(side="left")
        self._hist_lbl = ctk.CTkLabel(acts, text="", font=F_XS, text_color=TEXT2)
        self._hist_lbl.pack(side="right", padx=10)

        # ── Body split ────────────────────────────────────────────────────────
        split = ctk.CTkFrame(parent, fg_color="transparent")
        split.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 8))
        split.grid_columnconfigure(0, weight=1)
        split.grid_rowconfigure(1, weight=1)

        # SQL editor
        ef = ctk.CTkFrame(split, fg_color=BG1, corner_radius=8)
        ef.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(ef, text="CMS SQL:", font=F_XS,
                     text_color=TEXT2, anchor="w").pack(fill="x", padx=12, pady=(8,2))
        self._editor = ctk.CTkTextbox(ef, height=118, font=F_MONO,
                                       fg_color=BG0, text_color=TEAL,
                                       border_width=0, corner_radius=6)
        self._editor.pack(fill="x", padx=12, pady=(0, 10))
        first_q = list(TEMPLATES[first_cat].values())[0]
        self._editor.insert("1.0", first_q)

        # Results treeview
        rf2 = ctk.CTkFrame(split, fg_color=BG1, corner_radius=8)
        rf2.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        rf2.grid_columnconfigure(0, weight=1)
        rf2.grid_rowconfigure(1, weight=1)
        self._results_lbl = ctk.CTkLabel(rf2, text="Results:", font=F_SM,
                                          text_color=TEXT2, anchor="w")
        self._results_lbl.grid(row=0, column=0, sticky="ew", padx=12, pady=(8,4))

        tv_wrap = ctk.CTkFrame(rf2, fg_color="transparent")
        tv_wrap.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0,10))
        tv_wrap.grid_columnconfigure(0, weight=1)
        tv_wrap.grid_rowconfigure(0, weight=1)

        sty = ttk.Style()
        sty.theme_use("default")
        sty.configure("QB2.Treeview",
                       background=BG0, foreground=TEXT,
                       fieldbackground=BG0, rowheight=28,
                       font=("Segoe UI",10), borderwidth=0)
        sty.configure("QB2.Treeview.Heading",
                       background=BG1, foreground=TEXT2,
                       font=("Segoe UI",10,"bold"), relief="flat")
        sty.map("QB2.Treeview",
                background=[("selected",BLUE)],
                foreground=[("selected","white")])

        self._tree = ttk.Treeview(tv_wrap, style="QB2.Treeview",
                                   show="headings", selectmode="browse")
        vsb = ctk.CTkScrollbar(tv_wrap, orientation="vertical",
                                command=self._tree.yview)
        hsb = ctk.CTkScrollbar(tv_wrap, orientation="horizontal",
                                command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        hsb.grid(row=1, column=0, sticky="ew")
        vsb.grid(row=0, column=1, sticky="ns")
        self._tree.grid(row=0, column=0, sticky="nsew")

    # ── Template pickers ──────────────────────────────────────────────────────

    def _on_cat_change(self, cat):
        names = list(TEMPLATES[cat].keys())
        self._tmpl_menu.configure(values=names)
        self._tmpl_var.set(names[0])
        self._on_tmpl_change(names[0])

    def _on_tmpl_change(self, tmpl):
        cat = self._cat_var.get()
        q   = TEMPLATES.get(cat, {}).get(tmpl, "")
        self._editor.delete("1.0", "end")
        self._editor.insert("1.0", q)

    # ── Run query ─────────────────────────────────────────────────────────────

    def _run_query(self):
        q = self._editor.get("1.0", "end").strip()
        if not q:
            return
        self._qb_status.configure(text="⏳ Running…")
        for item in self._tree.get_children():
            self._tree.delete(item)

        def _do():
            t0 = time.time()
            r  = bo_session.run_cms_query(q)
            return r, int((time.time() - t0) * 1000)

        def _done(res):
            result, ms = res
            if not result:
                self._qb_status.configure(text="❌ No response from CMS")
                return
            entries = result.get("entries", [])
            self._last_result = entries
            self._query_history.append({"query": q[:60], "rows": len(entries), "ms": ms})
            self._hist_lbl.configure(text=f"History: {len(self._query_history)}")
            if not entries:
                self._qb_status.configure(text=f"0 rows  ({ms}ms)")
                return
            cols = list(entries[0].keys())
            self._tree["columns"] = cols
            for col in cols:
                w = min(max(len(col)*10, 80), 200)
                self._tree.heading(col, text=col)
                self._tree.column(col, width=w, minwidth=50, stretch=True)
            for e in entries:
                self._tree.insert("","end",
                                   values=[str(e.get(c,""))[:100] for c in cols])
            self._results_lbl.configure(text=f"Results: {len(entries)} rows")
            self._qb_status.configure(text=f"✅ {len(entries)} rows  ({ms}ms)")

        bg(_do, _done, self)

    # ── NL generator ─────────────────────────────────────────────────────────

    def _nl_generate(self):
        text = self._nl_entry.get().strip()
        if not text:
            return
        self._nl_btn.configure(text="⏳…", state="disabled")
        self._qb_status.configure(text="🤖 AI generating CMS SQL…")

        def _do():
            try:
                return True, _ai_to_cms_query(text)
            except Exception as e:
                return False, str(e)

        def _done(res):
            ok, result = res
            self._nl_btn.configure(
                text="✨ Generate",
                state="normal" if _QB_HAS_AI else "disabled")
            if ok:
                self._editor.delete("1.0", "end")
                self._editor.insert("1.0", result)
                self._qb_status.configure(
                    text="✅ AI query generated — review then ▶ Run")
            else:
                self._qb_status.configure(text=f"❌ AI: {result[:60]}")

        bg(_do, _done, self)

    # ── Export ────────────────────────────────────────────────────────────────

    def _export(self):
        if not self._last_result:
            messagebox.showinfo("Export", "Run a query first.", parent=self)
            return
        try:
            import openpyxl
            from tkinter.filedialog import asksaveasfilename
            path = asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel","*.xlsx")],
                initialfile="cms_query_results.xlsx",
                parent=self)
            if not path:
                return
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Results"
            if self._last_result:
                cols = list(self._last_result[0].keys())
                ws.append(cols)
                for row in self._last_result:
                    ws.append([str(row.get(c, "")) for c in cols])
            wb.save(path)
            messagebox.showinfo("Export Complete", f"Saved:\n{path}", parent=self)
        except ImportError:
            messagebox.showwarning("Missing Library",
                                   "Run:  pip install openpyxl", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", str(e), parent=self)

    # ── Clear ─────────────────────────────────────────────────────────────────

    def _clear(self):
        self._editor.delete("1.0", "end")
        for item in self._tree.get_children():
            self._tree.delete(item)
        self._tree["columns"] = []
        self._results_lbl.configure(text="Results:")
        self._qb_status.configure(text="")
        self._last_result = None

    # ══════════════════════════════════════════════════════════════════════════
    # PANEL 1 — LICENSE KEYS
    # ══════════════════════════════════════════════════════════════════════════

    def _build_lic(self, parent: ctk.CTkFrame):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        # Refresh button
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 4))
        ctk.CTkButton(top, text="⟳ Refresh", width=90, height=28,
                      fg_color=BG2, text_color=TEXT, font=F_SM,
                      command=self._lic_load).pack(side="right")
        self._lic_status = ctk.CTkLabel(top, text="", font=F_XS, text_color=TEXT2)
        self._lic_status.pack(side="left")

        # Summary tiles
        self._lic_tiles = ctk.CTkFrame(parent, fg_color="transparent")
        self._lic_tiles.grid(row=0, column=0, sticky="ew", padx=14, pady=(40, 6))

        # Scrollable cards
        self._lic_scroll = ctk.CTkScrollableFrame(
            parent, fg_color=BG1, corner_radius=8)
        self._lic_scroll.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 8))

    def _lic_load(self):
        for w in self._lic_tiles.winfo_children():
            w.destroy()
        for w in self._lic_scroll.winfo_children():
            w.destroy()
        self._lic_status.configure(text="⏳ Loading license data…")

        def _do():
            try:
                return bo_session.get_license_keys()
            except Exception:
                return []

        def _done(licenses):
            licenses = licenses or []
            if not licenses:
                ctk.CTkLabel(self._lic_scroll,
                             text=("No license data found in CMS.\n\n"
                                   "Check CMC → License Keys for details.\n\n"
                                   "Note: bo_session.get_license_keys() must be "
                                   "implemented in sapbo_connection.py"),
                             font=F_SM, text_color=TEXT2,
                             justify="center").pack(pady=40)
                self._lic_status.configure(text="No license data returned")
                return

            active  = sum(1 for l in licenses
                          if "EXPIR" not in str(l.get("status","")).upper())
            expired = len(licenses) - active

            for lbl, val, col in [
                ("Total Licenses", str(len(licenses)), CYAN),
                ("Active",  str(active),  GREEN),
                ("Expired", str(expired), RED if expired else TEXT2),
            ]:
                tile = ctk.CTkFrame(self._lic_tiles, fg_color=BG1,
                                     corner_radius=8, width=155, height=72)
                tile.pack(side="left", padx=(0, 12))
                tile.pack_propagate(False)
                ctk.CTkLabel(tile, text=val, font=("Segoe UI",26,"bold"),
                             text_color=col).pack(pady=(8,0))
                ctk.CTkLabel(tile, text=lbl, font=F_XS,
                             text_color=TEXT2).pack()

            for lic in licenses:
                self._add_lic_card(lic)

            self._lic_status.configure(
                text=f"{len(licenses)} license(s) from CMS  "
                     f"({active} active, {expired} expired)")

        bg(_do, _done, self)

    def _add_lic_card(self, lic: dict):
        status = str(lic.get("status", "Active"))
        is_exp = "EXPIR" in status.upper()
        border = RED if is_exp else BG2

        card = ctk.CTkFrame(self._lic_scroll, fg_color=BG1, corner_radius=8,
                             border_color=border, border_width=1)
        card.pack(fill="x", padx=4, pady=6)

        # Card header
        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 6))
        ctk.CTkLabel(hdr,
                     text=lic.get("product", "SAP BusinessObjects"),
                     font=F_H3, text_color=TEXT).pack(side="left")
        ctk.CTkLabel(hdr,
                     text=f"● {status}",
                     font=F_SM,
                     text_color=RED if is_exp else GREEN
                     ).pack(side="right")

        ctk.CTkFrame(card, height=1, fg_color=BG2).pack(fill="x", padx=16)

        # Details grid
        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=10)

        for lbl, val in [
            ("License Type",  lic.get("type","Standard")),
            ("License Key",   lic.get("key","N/A")),
            ("Named Users",   str(lic.get("seats","N/A"))),
            ("Concurrent",    str(lic.get("concurrent","N/A"))),
            ("Expiry Date",   str(lic.get("expiry","N/A"))),
        ]:
            sub = ctk.CTkFrame(grid, fg_color="transparent")
            sub.pack(side="left", padx=(0, 24), pady=2, anchor="n")
            ctk.CTkLabel(sub, text=lbl, font=F_XS, text_color=TEXT2).pack(anchor="w")
            ctk.CTkLabel(sub, text=str(val) if val else "N/A",
                         font=("Segoe UI",12,"bold"),
                         text_color=TEXT).pack(anchor="w")

        ctk.CTkFrame(card, height=1, fg_color="transparent").pack(pady=(0, 4))
