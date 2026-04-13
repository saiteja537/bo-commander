"""
gui/pages/ai_assistant.py  —  BO Commander AI Assistant  v2.0
Production-grade SAP BO expert chat with:
  • Live system context snapshot (servers, failures, stats)
  • Conversation memory (last 8 turns)
  • Copy-to-clipboard per message
  • Timestamp on every bubble
  • Quick-prompt library organised by category
  • AI engine status indicator
  • Export full chat to text file
"""

import threading
import time
from datetime import datetime
from tkinter import filedialog

import customtkinter as ctk
from config import Config
from ai.gemini_client import ai_client
from core.sapbo_connection import bo_session

C = Config.COLORS
F = Config.FONTS

# ── palette ───────────────────────────────────────────────────────────────────
BG0   = C["bg_primary"]
BG1   = C["bg_secondary"]
BG2   = C["bg_tertiary"]
CYAN  = "#22d3ee"
BLUE  = C["primary"]
VIOLET= C["secondary"]
GREEN = C["success"]
AMBER = C["warning"]
RED   = C["danger"]
TEXT  = C["text_primary"]
TEXT2 = C["text_secondary"]

# ── domain keywords ───────────────────────────────────────────────────────────
_BO_KW = {
    'sap','bo','bobj','businessobjects','business objects','webi','web intelligence',
    'crystal','xcelsius','dashboard','lumira','universe','unv','unx','bex','bics',
    'cms','cmc','bi launchpad','bilaunchpad','opendocument','auditing',
    'tomcat','wacs','aps','sia','job server','connection server','event server',
    'adaptive','schedule','instance','publication','report','session','license',
    'promotion','lcm','lifecycle','security','authentication','enterprise',
    'ldap','active directory','sso','saml','heap','memory','jvm','java',
    'log','trace','glf','error','failed','performance','cache','cluster',
    'node','patch','upgrade','install','pam','support','connection','database',
    'odbc','jdbc','data source','metadata','folder','inbox','recycle',
    'user','group','role','rights','access level','token','server',
}

_SYSTEM_PROMPT = """You are an expert SAP BusinessObjects (SAP BO / BOBJ) BI platform administrator AI, \
embedded inside BO Commander — an enterprise administration tool running on SAP BO BI 4.3.

EXPERTISE:
- Platform: CMS, Tomcat/WACS, APS, Job Server, Connection Server, Event Server, SIA nodes
- BI Launchpad, CMC administration, user/group security
- Web Intelligence (Webi), Crystal Reports, Analysis for Office (AO), Xcelsius/Dashboards
- Universes (UNV/UNX), ODBC/JDBC/BICS/OLAP connections, metadata management
- Security: Enterprise, LDAP, AD, SAML/SSO/Kerberos authentication
- Scheduling, publishing, LCM promotions, lifecycle management
- Performance: JVM heap, connection pooling, CMS DB tuning, Tomcat thread pool
- Troubleshooting: OOM, connection refused, failed instances, corrupt reports, cert errors
- Versions 4.1 / 4.2 / 4.3 / 4.4 — PAM matrix, SPs, patches, hotfixes
- Log analysis: GLF, trace, catalina.out, GC logs, SI_PROCESSINFO

RULES:
1. Answer ONLY SAP BO / BOBJ related questions.
2. Reject unrelated questions politely and redirect to BO topics.
3. Be specific: give real SQL, exact file paths (Windows), port numbers, config values.
4. Number steps for procedures. Short paragraphs for explanations.
5. When live system context is provided, refer to it for specific advice.
6. Plain text only — no markdown asterisks or headers. This is a desktop chat UI.
"""

_QUICK = [
    ("Administration", [
        ("👥 User Sync",       "How do I synchronise LDAP users into SAP BO 4.3?"),
        ("🔐 SSO SAML",        "How do I configure SAML SSO for SAP BO BI 4.3?"),
        ("📦 LCM Promote",     "How do I promote objects between environments using LCM?"),
        ("🗓 Schedule Audit",  "How do I audit all scheduled reports and their owners?"),
    ]),
    ("Performance", [
        ("💾 JVM Heap",        "My Tomcat has OutOfMemoryError. How do I size JVM heap?"),
        ("🐌 Slow Reports",    "Reports are slow. What are the top performance tuning steps?"),
        ("🗃 CMS DB",          "How do I optimise the CMS database (MSSQL)?"),
        ("🔄 Connection Pool", "How do I tune JDBC connection pooling in SAP BO?"),
    ]),
    ("Troubleshooting", [
        ("❌ Failed Instances", "My scheduled reports keep failing. How do I troubleshoot?"),
        ("🚫 Service Down",     "The CMS service won't start. What are the common causes?"),
        ("🔌 DB Connect Fail",  "WebI reports get 'Database connection failed'. How to fix?"),
        ("🌐 Launchpad 500",    "BI Launchpad shows HTTP 500. What do I check?"),
    ]),
]


def _is_bo(text: str) -> bool:
    t = text.lower()
    return any(kw in t for kw in _BO_KW)


class _Bubble(ctk.CTkFrame):
    """Single chat message bubble with timestamp + copy button."""
    def __init__(self, parent, text: str, role: str, ts: str):
        super().__init__(parent, fg_color="transparent")
        is_user = role == "user"
        wrap = 660

        outer = ctk.CTkFrame(self,
                              fg_color=BLUE  if is_user else BG2,
                              corner_radius=12)
        outer.pack(anchor="e" if is_user else "w",
                   padx=(60 if is_user else 0, 0 if is_user else 60))

        # message text
        ctk.CTkLabel(outer, text=text, wraplength=wrap, justify="left",
                     text_color=TEXT, font=("Segoe UI", 12),
                     anchor="w", padx=14, pady=10).pack(fill="x")

        # footer: timestamp + copy
        foot = ctk.CTkFrame(outer, fg_color="transparent", height=22)
        foot.pack(fill="x", padx=10, pady=(0, 6))
        ctk.CTkLabel(foot, text=ts, font=("Segoe UI", 9),
                     text_color=TEXT2).pack(side="left")
        ctk.CTkButton(foot, text="⎘ Copy", width=56, height=18,
                      font=("Segoe UI", 9), fg_color="transparent",
                      text_color=TEXT2, hover_color=BG1,
                      command=lambda: self._copy(text)).pack(side="right")

        self._text = text

    def _copy(self, text):
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception:
            pass


class AIAssistantPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=BG0, corner_radius=0)
        self._history  = []   # [(role, text), ...]
        self._thinking = None
        self._destroyed = False
        self._build()
        self._load_context_async()

    def destroy(self):
        self._destroyed = True
        super().destroy()

    # ── build layout ──────────────────────────────────────────────────────────
    def _build(self):
        # ── header bar ────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        icon_f = ctk.CTkFrame(hdr, fg_color=BLUE, width=40, height=40, corner_radius=10)
        icon_f.pack(side="left", padx=(16,10))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="🤖", font=("Segoe UI", 20)
                     ).place(relx=.5, rely=.5, anchor="center")

        ctk.CTkLabel(hdr, text="AI Assistant",
                     font=("Segoe UI", 18, "bold"),
                     text_color=TEXT).pack(side="left")
        ctk.CTkLabel(hdr, text="  SAP BO Expert · Gemini",
                     font=("Segoe UI", 10), text_color=TEXT2).pack(side="left")

        # right controls
        ctk.CTkButton(hdr, text="⬇ Export Chat", width=110, height=30,
                      fg_color=BG2, text_color=TEXT2, font=F["small"],
                      hover_color=BG0, command=self._export).pack(side="right", padx=8)
        ctk.CTkButton(hdr, text="🗑 Clear", width=74, height=30,
                      fg_color=BG2, text_color=TEXT2, font=F["small"],
                      hover_color=BG0, command=self._clear).pack(side="right")

        self._ctx_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(hdr, text="Live context",
                        variable=self._ctx_var,
                        font=("Segoe UI", 10), text_color=TEXT2,
                        checkbox_width=16, checkbox_height=16
                        ).pack(side="right", padx=10)

        # ── context status strip ───────────────────────────────────────────────
        self._ctx_strip = ctk.CTkFrame(self, fg_color=BG2, corner_radius=0, height=28)
        self._ctx_strip.pack(fill="x")
        self._ctx_strip.pack_propagate(False)
        self._ctx_lbl = ctk.CTkLabel(self._ctx_strip,
                                      text="⏳  Loading live BO context…",
                                      font=("Segoe UI", 10), text_color=TEXT2)
        self._ctx_lbl.pack(side="left", padx=14)
        self._ctx_dot = ctk.CTkLabel(self._ctx_strip, text="●",
                                      font=("Segoe UI", 12), text_color=AMBER)
        self._ctx_dot.pack(side="right", padx=14)

        # ── quick prompts ──────────────────────────────────────────────────────
        qbar = ctk.CTkFrame(self, fg_color=BG1, height=38)
        qbar.pack(fill="x", padx=0, pady=0)
        qbar.pack_propagate(False)

        ctk.CTkLabel(qbar, text="Quick:", font=("Segoe UI", 9, "bold"),
                     text_color=TEXT2).pack(side="left", padx=(12,6))

        self._quick_tab = ctk.StringVar(value=_QUICK[0][0])
        for cat, _ in _QUICK:
            ctk.CTkButton(qbar, text=cat, height=24, width=110,
                          font=("Segoe UI", 9),
                          fg_color=BLUE if cat == _QUICK[0][0] else BG2,
                          hover_color=BLUE, text_color=TEXT,
                          command=lambda c=cat: self._switch_cat(c)
                          ).pack(side="left", padx=2)

        self._prompt_row = ctk.CTkFrame(self, fg_color=BG2, height=34)
        self._prompt_row.pack(fill="x")
        self._prompt_row.pack_propagate(False)
        self._render_prompts(_QUICK[0][0])

        # ── chat scroll area ───────────────────────────────────────────────────
        self._chat = ctk.CTkScrollableFrame(self, fg_color=BG1, corner_radius=0)
        self._chat.pack(fill="both", expand=True, padx=0, pady=0)

        # ── input bar ─────────────────────────────────────────────────────────
        inp = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=58)
        inp.pack(fill="x", padx=0, pady=0)
        inp.pack_propagate(False)
        inp.grid_columnconfigure(0, weight=1)

        self._entry = ctk.CTkEntry(
            inp,
            placeholder_text="Ask anything about SAP BusinessObjects…",
            fg_color=BG2, border_color=BG2,
            text_color=TEXT, font=("Segoe UI", 13))
        self._entry.grid(row=0, column=0, sticky="ew", padx=(14,8), pady=10)
        self._entry.bind("<Return>", self._send)

        self._send_btn = ctk.CTkButton(
            inp, text="Send  ↵", width=90, height=36,
            font=("Segoe UI", 12, "bold"),
            fg_color=BLUE, hover_color="#2563eb",
            command=self._send)
        self._send_btn.grid(row=0, column=1, padx=(0, 12))

        # welcome bubble
        self._add_bubble(
            "Hello! I'm your SAP BO AI Assistant — connected to your live BI 4.3 system.\n\n"
            "I can help with:\n"
            "  • Troubleshooting: OOM, failed services, broken connections\n"
            "  • Administration: users, security, LDAP/SSO, scheduling\n"
            "  • Performance: JVM tuning, CMS DB, report speed\n"
            "  • Versions 4.1 / 4.2 / 4.3 / 4.4 — PAM, patches, upgrades\n\n"
            "I only answer SAP BusinessObjects questions. "
            "Use the quick prompts above to get started.",
            role="ai",
        )

    # ── quick prompt UI ───────────────────────────────────────────────────────
    def _switch_cat(self, cat):
        self._quick_tab.set(cat)
        # Update button colours
        for w in self._prompt_row.master.winfo_children():
            pass  # handled via re-render
        self._render_prompts(cat)

    def _render_prompts(self, cat):
        for w in self._prompt_row.winfo_children():
            w.destroy()
        prompts = next((p for c, p in _QUICK if c == cat), [])
        for label, prompt in prompts:
            ctk.CTkButton(
                self._prompt_row, text=label, height=26, width=148,
                font=("Segoe UI", 9),
                fg_color=BG0, hover_color=BLUE, text_color=TEXT,
                corner_radius=4,
                command=lambda p=prompt: self._quick_fire(p)
            ).pack(side="left", padx=(6,2))

    def _quick_fire(self, prompt):
        self._entry.delete(0, "end")
        self._entry.insert(0, prompt)
        self._send()

    # ── context loading ───────────────────────────────────────────────────────
    def _load_context_async(self):
        def _fetch():
            try:
                snap = bo_session.get_ai_context_snapshot()
                self._ctx_snapshot = snap
                stats = snap.get("stats", {})
                srv_run  = stats.get("servers_running", 0)
                srv_tot  = stats.get("servers_total", 0)
                failed   = stats.get("failed_instances", 0)
                stopped  = [s["name"] for s in snap.get("servers", [])
                            if s.get("status","").lower() not in ("running","started")]
                msg = (f"Connected: {stats.get('reports',0)} reports  "
                       f"{stats.get('users',0)} users  "
                       f"{srv_run}/{srv_tot} servers  "
                       f"{failed} failed instances")
                color = RED if stopped else (AMBER if failed > 0 else GREEN)
                if not self._destroyed:
                    self.after(0, lambda: (
                        self._ctx_lbl.configure(text=msg),
                        self._ctx_dot.configure(text_color=color)
                    ))
            except Exception as e:
                if not self._destroyed:
                    self.after(0, lambda: (
                        self._ctx_lbl.configure(text="Context unavailable — not connected"),
                        self._ctx_dot.configure(text_color=RED)
                    ))
        self._ctx_snapshot = {}
        threading.Thread(target=_fetch, daemon=True).start()

    # ── chat helpers ──────────────────────────────────────────────────────────
    def _add_bubble(self, text, role="ai"):
        ts = datetime.now().strftime("%H:%M")
        b = _Bubble(self._chat, text, role, ts)
        b.pack(fill="x", pady=4, padx=14)
        try:
            self._chat._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _clear(self):
        for w in self._chat.winfo_children():
            w.destroy()
        self._history.clear()

    def _export(self):
        if not self._history:
            return
        path = filedialog.asksaveasfilename(
            title="Export Chat",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt")],
            initialfile=f"bo_ai_chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            parent=self)
        if not path:
            return
        lines = [f"BO Commander AI Assistant — exported {datetime.now():%Y-%m-%d %H:%M}\n{'='*60}\n"]
        for role, text in self._history:
            prefix = "You" if role == "user" else "AI "
            lines.append(f"[{prefix}]  {text}\n")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except Exception as e:
            pass

    # ── send / receive ────────────────────────────────────────────────────────
    def _send(self, event=None):
        text = self._entry.get().strip()
        if not text:
            return
        self._entry.delete(0, "end")
        self._add_bubble(text, role="user")
        self._history.append(("user", text))

        # typing indicator
        self._thinking = ctk.CTkLabel(
            self._chat, text="⏳  Thinking…",
            text_color=TEXT2, font=("Segoe UI", 11, "italic"))
        self._thinking.pack(anchor="w", padx=28, pady=4)
        try:
            self._chat._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass
        self._send_btn.configure(state="disabled")
        threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _worker(self, user_text):
        try:
            if not _is_bo(user_text):
                resp = (
                    "I specialise exclusively in SAP BusinessObjects (SAP BO/BOBJ) questions.\n\n"
                    "That topic is outside my scope. I'm happy to help with:\n"
                    "  • SAP BO administration, troubleshooting, performance\n"
                    "  • Webi, Crystal Reports, universes, connections\n"
                    "  • Server setup, security, scheduling, upgrades\n\n"
                    "Please ask a SAP BO related question!"
                )
            else:
                ctx = ""
                if self._ctx_var.get() and self._ctx_snapshot:
                    snap   = self._ctx_snapshot
                    stats  = snap.get("stats", {})
                    stopped= [s["name"] for s in snap.get("servers",[])
                               if s.get("status","").lower() not in ("running","started")]
                    recent = snap.get("recent_failures", [])
                    ctx = (
                        f"Host: {bo_session.cms_details.get('host','?')}\n"
                        f"Servers: {stats.get('servers_running',0)}/{stats.get('servers_total',0)} running\n"
                        f"Failed instances: {stats.get('failed_instances',0)}\n"
                        f"Reports: {stats.get('reports',0)}  Users: {stats.get('users',0)}\n"
                    )
                    if stopped:
                        ctx += f"Stopped servers: {', '.join(stopped[:5])}\n"
                    if recent:
                        ctx += "Recent failures:\n" + "\n".join(
                            f"  - {f['name']} (owner: {f['owner']})" for f in recent[:5])

                hist = "\n".join(
                    f"{'User' if r=='user' else 'Assistant'}: {t}"
                    for r, t in self._history[-8:])

                prompt = (
                    _SYSTEM_PROMPT + "\n\n"
                    + (f"LIVE BO CONTEXT:\n{ctx}\n\n" if ctx else "")
                    + f"CONVERSATION:\n{hist}\nUser: {user_text}\nAssistant:"
                )
                resp = ai_client.get_response(prompt)
        except Exception as e:
            resp = f"Error contacting AI: {e}"

        if not self._destroyed:
            self.after(0, lambda r=resp: self._show(r))

    def _show(self, resp):
        if self._thinking:
            try:
                self._thinking.destroy()
            except Exception:
                pass
            self._thinking = None
        self._send_btn.configure(state="normal")
        self._add_bubble(resp, role="ai")
        self._history.append(("ai", resp))