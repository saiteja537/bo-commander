"""
gui/pages/ai_assistant.py
Enhanced AI Assistant:
  - SAP BO domain-only: rejects non-BO questions with a polite message
  - Richer system prompt with BO expertise (admin, troubleshooting, best practices)
  - Live BO context injected from existing sapbo_connection methods (no new methods needed)
  - Chat history (last 6 turns sent for context)
  - Suggested quick-action buttons
  - No 8-layer scan triggered
"""

import threading
import customtkinter as ctk
from config import Config
from ai.gemini_client import ai_client
from core.sapbo_connection import bo_session

C = Config.COLORS
F = Config.FONTS

# ── SAP BO domain detection ────────────────────────────────────────────────────
BO_KEYWORDS = {
    'sap', 'bo', 'bobj', 'businessobjects', 'business objects', 'webi', 'web intelligence',
    'crystal', 'xcelsius', 'dashboard', 'lumira', 'universe', 'unv', 'unx', 'bex', 'bics',
    'cms', 'cmc', 'bi launchpad', 'bilaunchpad', 'opendocument', 'fiorbi', 'auditing',
    'server', 'tomcat', 'wacs', 'aps', 'sia', 'cms', 'job server', 'connection server',
    'event server', 'adaptive', 'schedule', 'instance', 'publication', 'report',
    'session', 'license', 'promotion', 'lcm', 'lifecycle', 'security', 'authentication',
    'enterprise', 'ldap', 'ad', 'active directory', 'sso', 'saml', 'heap', 'memory',
    'jvm', 'java', 'log', 'trace', 'glf', 'error', 'failed', 'performance', 'cache',
    'cluster', 'node', 'patch', 'upgrade', 'install', 'pam', 'support', 'connection',
    'database', 'odbc', 'jdbc', 'data source', 'metadata', 'folder', 'inbox', 'recycle',
    'user', 'group', 'role', 'rights', 'access level', 'principal', 'token',
}

BO_SYSTEM_PROMPT = """You are an expert SAP BusinessObjects (SAP BO / BOBJ) administrator AI assistant 
embedded inside BO Commander — a desktop administration tool.

YOUR EXPERTISE COVERS:
- SAP BO platform: CMS, Tomcat/WACS, APS, Job Server, Connection Server, Event Server, SIA
- BI Launchpad, CMC (Central Management Console) administration  
- Web Intelligence (Webi), Crystal Reports, Xcelsius/Dashboards, Analysis for Office (AO)
- Universes (UNV/UNX), connections (ODBC/JDBC/BICS/OLAP), metadata management
- User security: Enterprise, LDAP, AD, SAML/SSO authentication
- Scheduling, publishing, promotions, Lifecycle Management (LCM)
- Performance tuning: JVM heap sizing, connection pooling, CMS database optimization
- Troubleshooting: OutOfMemoryError, connection refused, failed instances, corrupt reports
- SAP BO versions 4.1, 4.2, 4.3, 4.4 — PAM compatibility, patch levels, support packs
- Monitoring: server metrics, audit database, log files (GLF, trace, GC logs)
- BO Commander tool features: Sentinel, Self Healing, Housekeeping, Security Scanner

RULES:
1. Answer ONLY SAP BO related questions
2. If asked about something unrelated to SAP BO, politely decline and redirect
3. Be specific and practical — give real SQL queries, config values, file paths when relevant
4. If you reference a config file path, use Windows paths (this is a Windows BO install)
5. Always consider the live BO context if provided

RESPONSE FORMAT:
- Use plain text (no markdown bold/headers — this is a chat UI)
- Be concise but complete
- For step-by-step fixes, number the steps
- Include specific values (port numbers, file paths, heap sizes) when helpful
"""

QUICK_PROMPTS = [
    ("🔧 Fix OOM Error",        "My Tomcat is throwing OutOfMemoryError. How do I fix it?"),
    ("📊 Slow Reports",         "Reports are running slowly. What should I check and tune?"),
    ("🔐 LDAP Setup",           "How do I configure LDAP authentication in SAP BO 4.3?"),
    ("🗃 CMS DB Tuning",        "How do I optimize the CMS database for better performance?"),
    ("📅 Schedule Fails",       "My scheduled reports keep failing. How do I troubleshoot?"),
    ("🔄 Restart Order",        "What is the correct order to restart all SAP BO services?"),
]


def _is_bo_related(text: str) -> bool:
    """Check if the user's question is related to SAP BO."""
    t = text.lower()
    return any(kw in t for kw in BO_KEYWORDS)


class AIAssistantPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0)
        self._history = []
        self._thinking = None

        # ── header ────────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color='transparent', height=60)
        top.pack(fill='x', padx=20, pady=(15, 0))
        top.pack_propagate(False)

        icon_f = ctk.CTkFrame(top, fg_color=C['primary'], width=44, height=44, corner_radius=10)
        icon_f.pack(side='left')
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text='🤖', font=('Segoe UI', 22)).place(relx=.5, rely=.5, anchor='center')

        ctk.CTkLabel(top, text='AI Assistant',
                     font=('Segoe UI', 20, 'bold'),
                     text_color=C['text_primary']).pack(side='left', padx=12)

        ctk.CTkLabel(top, text='SAP BO Expert · Powered by Gemini',
                     font=('Segoe UI', 10),
                     text_color=C['text_secondary']).pack(side='left')

        ctk.CTkButton(top, text='🗑 Clear', width=70, height=28,
                      fg_color=C['bg_tertiary'], text_color=C['text_primary'],
                      command=self._clear).pack(side='right')

        self._ctx_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(top, text='Include live BO context',
                        variable=self._ctx_var,
                        font=('Segoe UI', 11),
                        text_color=C['text_secondary']).pack(side='right', padx=10)

        # ── quick prompts ─────────────────────────────────────────────────────
        qrow = ctk.CTkFrame(self, fg_color='transparent')
        qrow.pack(fill='x', padx=20, pady=(8, 0))
        ctk.CTkLabel(qrow, text='Quick questions:',
                     font=('Segoe UI', 10), text_color=C['text_secondary']).pack(side='left')
        for label, prompt in QUICK_PROMPTS:
            ctk.CTkButton(qrow, text=label, height=26, width=130,
                          font=('Segoe UI', 9),
                          fg_color=C['bg_tertiary'],
                          hover_color=C['primary'],
                          text_color=C['text_primary'],
                          command=lambda p=prompt: self._quick_send(p)
                          ).pack(side='left', padx=3)

        # ── chat area ─────────────────────────────────────────────────────────
        self.chat = ctk.CTkScrollableFrame(self, fg_color=C['bg_secondary'], corner_radius=8)
        self.chat.pack(fill='both', expand=True, padx=20, pady=8)

        # ── input bar ─────────────────────────────────────────────────────────
        bar = ctk.CTkFrame(self, fg_color=C['bg_secondary'], corner_radius=10, height=55)
        bar.pack(fill='x', padx=20, pady=(0, 15))
        bar.pack_propagate(False)
        bar.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(bar, placeholder_text='Ask anything about SAP BusinessObjects…',
                                  fg_color='transparent', border_width=0,
                                  font=('Segoe UI', 12), text_color=C['text_primary'])
        self.entry.grid(row=0, column=0, sticky='ew', padx=(15, 5), pady=10)
        self.entry.bind('<Return>', self._send)

        self._send_btn = ctk.CTkButton(bar, text='Send ↵', width=80, height=34,
                                       font=('Segoe UI', 11, 'bold'), command=self._send)
        self._send_btn.grid(row=0, column=1, padx=(0, 10))

        # welcome
        self._add_bubble(
            "Hello! I'm your SAP BO AI Assistant.\n\n"
            "I specialise in:\n"
            "  • Troubleshooting: OOM errors, failed services, connection issues\n"
            "  • Administration: users, security, scheduling, promotions\n"
            "  • Performance: JVM tuning, CMS DB optimisation, caching\n"
            "  • Versions 4.1 / 4.2 / 4.3 / 4.4 — PAM, patches, upgrades\n\n"
            "Note: I only answer SAP BusinessObjects questions.",
            role='ai'
        )

    # ── bubble ────────────────────────────────────────────────────────────────

    def _add_bubble(self, text, role='ai'):
        is_user = role == 'user'
        row = ctk.CTkFrame(self.chat, fg_color='transparent')
        row.pack(fill='x', pady=3, padx=5)
        bubble = ctk.CTkLabel(
            row, text=text, wraplength=700, justify='left',
            fg_color=C['primary'] if is_user else C['bg_tertiary'],
            text_color=C['text_primary'], corner_radius=12,
            padx=14, pady=10, anchor='w', font=('Segoe UI', 12),
        )
        bubble.pack(anchor='e' if is_user else 'w')
        try:
            self.chat._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _clear(self):
        for w in self.chat.winfo_children():
            w.destroy()
        self._history.clear()

    # ── send ──────────────────────────────────────────────────────────────────

    def _quick_send(self, prompt):
        self.entry.delete(0, 'end')
        self.entry.insert(0, prompt)
        self._send()

    def _send(self, event=None):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, 'end')
        self._add_bubble(text, role='user')
        self._history.append(('user', text))

        self._thinking = ctk.CTkLabel(self.chat, text='⏳  Thinking…',
                                      text_color=C['text_secondary'],
                                      font=('Segoe UI', 11, 'italic'))
        self._thinking.pack(anchor='w', padx=20)
        self._send_btn.configure(state='disabled')
        threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _worker(self, user_text):
        try:
            # Domain check — reject non-BO questions
            if not _is_bo_related(user_text):
                response = (
                    "I'm specialised for SAP BusinessObjects (SAP BO) questions only.\n\n"
                    "I can't help with that topic, but I'm happy to assist with:\n"
                    "  • SAP BO administration, troubleshooting, performance\n"
                    "  • Webi, Crystal Reports, universes, connections\n"
                    "  • Server setup, security, scheduling, upgrades\n\n"
                    "Please ask a SAP BO related question!"
                )
            else:
                ctx = self._build_context() if self._ctx_var.get() else ''
                history_text = '\n'.join(
                    f"{'User' if r == 'user' else 'Assistant'}: {t}"
                    for r, t in self._history[-6:]
                )
                prompt = (
                    BO_SYSTEM_PROMPT + '\n\n'
                    + (f'LIVE BO SYSTEM CONTEXT:\n{ctx}\n\n' if ctx else '')
                    + f'CONVERSATION:\n{history_text}\nUser: {user_text}\nAssistant:'
                )
                response = ai_client.get_response(prompt)
        except Exception as e:
            response = f"Error: {e}"

        self.after(0, lambda r=response: self._show(r))

    def _show(self, response):
        if self._thinking:
            try:
                self._thinking.destroy()
            except Exception:
                pass
            self._thinking = None
        self._send_btn.configure(state='normal')
        self._add_bubble(response, role='ai')
        self._history.append(('ai', response))

    # ── live context (no new sapbo methods needed) ────────────────────────────

    def _build_context(self):
        lines = []
        try:
            if not bo_session.connected:
                return ''
            d = bo_session.cms_details
            lines.append(f"Host: {d.get('host','?')}:{d.get('port','?')} | User: {d.get('user','?')}")
            stats = bo_session.get_dashboard_stats()
            lines.append(
                f"Servers: {stats.get('servers_running',0)}/{stats.get('servers_total',0)} running | "
                f"Users: {stats.get('users',0)} | Reports: {stats.get('reports',0)} | "
                f"Universes: {stats.get('universes',0)} | Connections: {stats.get('connections',0)}"
            )
            lines.append(
                f"Failed instances: {stats.get('failed_instances',0)} | "
                f"Active sessions: {stats.get('active_sessions',0)}"
            )
            stopped = [s['name'] for s in stats.get('server_list', []) if not s.get('alive')]
            if stopped:
                lines.append(f"Stopped servers: {', '.join(stopped[:5])}")
        except Exception as e:
            lines.append(f"Context unavailable: {e}")
        return '\n'.join(lines)
