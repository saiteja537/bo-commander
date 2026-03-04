"""
gui/pages/ai_assistant.py
Fix: AttributeError: 'SAPBOConnection' object has no attribute 'get_ai_context_snapshot'
     The page called bo_session.get_ai_context_snapshot() which never existed.
     Replaced with a lightweight context builder that uses existing sapbo methods.

Design: AI Assistant is a CHAT tool only — it does NOT trigger the 8-layer Sentinel scan.
        It pulls a minimal live snapshot (servers + stats) as context when the checkbox
        is ticked, then sends user prompt + context to Gemini.
"""

import threading
import customtkinter as ctk
from config import Config
from ai.gemini_client import ai_client
from core.sapbo_connection import bo_session

C = Config.COLORS
F = Config.FONTS


class AIAssistantPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0)

        self._history = []   # list of (role, text)
        self._thinking = None

        # ── top bar ───────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color='transparent', height=60)
        top.pack(fill='x', padx=20, pady=(15, 0))
        top.pack_propagate(False)

        icon = ctk.CTkFrame(top, fg_color=C['primary'],
                            width=40, height=40, corner_radius=8)
        icon.pack(side='left')
        icon.pack_propagate(False)
        ctk.CTkLabel(icon, text='🤖', font=('Segoe UI', 20)).place(relx=.5, rely=.5, anchor='center')

        ctk.CTkLabel(top, text='AI Assistant',
                     font=('Segoe UI', 20, 'bold'),
                     text_color=C['text_primary']).pack(side='left', padx=12)

        ctk.CTkButton(top, text='🗑 Clear', width=80, height=30,
                      fg_color=C['bg_tertiary'], text_color=C['text_primary'],
                      command=self._clear).pack(side='right')

        self._ctx_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(top, text='Include live BO context',
                        variable=self._ctx_var,
                        font=('Segoe UI', 11),
                        text_color=C['text_secondary']).pack(side='right', padx=12)

        # ── chat area ─────────────────────────────────────────────────────────
        self.chat = ctk.CTkScrollableFrame(self, fg_color=C['bg_secondary'],
                                           corner_radius=8)
        self.chat.pack(fill='both', expand=True, padx=20, pady=10)

        # ── input bar ─────────────────────────────────────────────────────────
        bar = ctk.CTkFrame(self, fg_color=C['bg_secondary'],
                           corner_radius=10, height=55)
        bar.pack(fill='x', padx=20, pady=(0, 15))
        bar.pack_propagate(False)
        bar.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(bar, placeholder_text='Ask anything about your SAP BO system…',
                                  fg_color='transparent', border_width=0,
                                  font=('Segoe UI', 12),
                                  text_color=C['text_primary'])
        self.entry.grid(row=0, column=0, sticky='ew', padx=(15, 5), pady=10)
        self.entry.bind('<Return>', self._send)

        self._send_btn = ctk.CTkButton(bar, text='Send ↵', width=80, height=34,
                                       font=('Segoe UI', 11, 'bold'),
                                       command=self._send)
        self._send_btn.grid(row=0, column=1, padx=(0, 10))

        # welcome
        self._add_bubble(
            "Hello! I'm your SAP BO AI Assistant. I can help you with:\n"
            "  • Finding objects, users, servers\n"
            "  • Explaining BO concepts\n"
            "  • Diagnosing issues\n"
            "  • Best-practice recommendations\n\n"
            "Ask me anything about your BO system!",
            role='ai'
        )

    # ── message helpers ───────────────────────────────────────────────────────

    def _add_bubble(self, text, role='ai'):
        is_user = role == 'user'
        row = ctk.CTkFrame(self.chat, fg_color='transparent')
        row.pack(fill='x', pady=3, padx=5)

        bubble = ctk.CTkLabel(
            row,
            text=text,
            wraplength=640,
            justify='left',
            fg_color=C['primary'] if is_user else C['bg_tertiary'],
            text_color=C['text_primary'],
            corner_radius=12,
            padx=14, pady=10,
            anchor='w',
            font=('Segoe UI', 12),
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

    def _send(self, event=None):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, 'end')
        self._add_bubble(text, role='user')
        self._history.append(('user', text))

        # Thinking indicator
        self._thinking = ctk.CTkLabel(self.chat,
                                      text='⏳  Thinking…',
                                      text_color=C['text_secondary'],
                                      font=('Segoe UI', 11, 'italic'))
        self._thinking.pack(anchor='w', padx=20)
        self._send_btn.configure(state='disabled')

        threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _worker(self, user_text):
        try:
            # Build context (only if checkbox ticked) — NO 8-layer scan here
            ctx_block = ''
            if self._ctx_var.get() and bo_session.connected:
                ctx_block = self._build_live_context()

            # Build conversation prompt
            system = (
                "You are an expert SAP BusinessObjects administrator AI assistant "
                "embedded in BO Commander. Answer concisely and practically. "
                "If given live BO system context, use it to give specific answers."
            )
            history_text = '\n'.join(
                f"{'User' if r=='user' else 'Assistant'}: {t}"
                for r, t in self._history[-6:]   # last 3 turns
            )
            prompt = (
                f"{system}\n\n"
                + (f"LIVE BO CONTEXT:\n{ctx_block}\n\n" if ctx_block else '')
                + f"CONVERSATION:\n{history_text}\nUser: {user_text}\nAssistant:"
            )

            response = ai_client.get_response(prompt)

        except Exception as e:
            response = f"AI error: {e}"

        self.after(0, lambda r=response: self._show_response(r))

    def _show_response(self, response):
        if self._thinking:
            try:
                self._thinking.destroy()
            except Exception:
                pass
            self._thinking = None
        self._send_btn.configure(state='normal')
        self._add_bubble(response, role='ai')
        self._history.append(('ai', response))

    # ── lightweight BO context (NOT a full sentinel scan) ────────────────────

    def _build_live_context(self):
        """
        Collect a minimal BO snapshot for AI context.
        Only queries already-available sapbo_connection methods.
        Does NOT trigger the 8-layer Sentinel RCA.
        """
        lines = []
        try:
            stats = bo_session.get_dashboard_stats()
            lines.append(
                f"Connected to: {bo_session.cms_details.get('host','?')}:"
                f"{bo_session.cms_details.get('port','?')} "
                f"as {bo_session.cms_details.get('user','?')}"
            )
            lines.append(
                f"Users: {stats.get('users',0)} | "
                f"Reports: {stats.get('reports',0)} | "
                f"Universes: {stats.get('universes',0)} | "
                f"Connections: {stats.get('connections',0)}"
            )
            lines.append(
                f"Servers: {stats.get('servers_running',0)} running / "
                f"{stats.get('servers_total',0)} total"
            )
            lines.append(
                f"Failed instances: {stats.get('failed_instances',0)} | "
                f"Instances today: {stats.get('instances_today',0)}"
            )
            # Top stopped servers
            stopped = [s['name'] for s in stats.get('server_list', [])
                       if s.get('status') != 'Running']
            if stopped:
                lines.append(f"Stopped servers: {', '.join(stopped[:5])}")
        except Exception as e:
            lines.append(f"Context fetch error: {e}")
        return '\n'.join(lines)
