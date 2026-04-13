"""
gui/tabs/tab_multibot.py  —  MultiBOT AI Agent  v3.0
=====================================================
Complete autonomous SAP BO operations agent.

Architecture:
  UI (CustomTkinter)
    └── CoordinatorAgent
          ├── SAPAgent        — reports, users, servers, instances (REST + Java SDK)
          ├── SystemAgent     — ports, disk, logs, services, cache (OS)
          └── MonitoringAgent — continuous health + self-healing + alerts

Features:
  • Multi-agent task routing (regex → keywords → AI)
  • Real Java Admin SDK server start/stop/restart
  • Multi-step task planning (fix failed, full diagnosis, morning check)
  • Persistent knowledge base (SQLite incidents + remediations)
  • Self-healing background monitor
  • Live alert badge
  • Conversation memory with context
  • All 20+ task types with real OS/REST execution
"""

import sys
import os
import threading
import time
import tkinter as tk
from datetime import datetime
from typing import Optional

# ── Ensure project root is on sys.path ─────────────────────────────────────
# This file lives at: <root>/gui/tabs/tab_multibot.py  (2 levels deep)
# We walk up to find the project root and add it to sys.path so that
# "agents", "bridges", "memory", "config" are all importable.
def _add_project_root():
    here = os.path.dirname(os.path.abspath(__file__))
    # Walk up until we find the folder containing bo_commander.py or agents/
    root = here
    for _ in range(5):
        if os.path.isdir(os.path.join(root, "agents")):
            break
        root = os.path.dirname(root)
    if root not in sys.path:
        sys.path.insert(0, root)
_add_project_root()

try:
    import customtkinter as ctk
except ImportError:
    import tkinter as ctk

from config import Config

C = Config.COLORS
F = Config.FONTS

# ─────────────────────────────────────────────────────────────────────────────
#  Safe imports for all agent layers
# ─────────────────────────────────────────────────────────────────────────────
_coordinator = None
_AGENT_IMPORT_ERROR = [None]   # stores last import error for display

def _get_coordinator():
    global _coordinator
    if _coordinator is None:
        try:
            from agents.coordinator_agent import CoordinatorAgent
            _coordinator = CoordinatorAgent()
        except ImportError as e:
            import logging, traceback
            _AGENT_IMPORT_ERROR[0] = (
                f"ImportError: {e}\n"
                f"sys.path[0]: {sys.path[0] if sys.path else 'empty'}\n"
                f"agents/ exists: {os.path.isdir(os.path.join(sys.path[0], 'agents')) if sys.path else False}\n"
                f"Traceback:\n{traceback.format_exc()}"
            )
            logging.getLogger("MultiBOT").error(_AGENT_IMPORT_ERROR[0])
        except Exception as e:
            import logging, traceback
            _AGENT_IMPORT_ERROR[0] = (
                f"Error: {e}\n{traceback.format_exc()}"
            )
            logging.getLogger("MultiBOT").error(_AGENT_IMPORT_ERROR[0])
    return _coordinator


# ─────────────────────────────────────────────────────────────────────────────
#  Quick-command definitions
# ─────────────────────────────────────────────────────────────────────────────
QUICK_COMMANDS = [
    # Row 1 — Health
    ("🏥 Health",          "system health"),
    ("🖥 Servers",         "list servers"),
    ("🔴 Failed",          "show failed reports"),
    ("💽 Disk",            "disk space"),
    # Row 2 — Reports
    ("📊 Reports",         "list reports"),
    ("👥 Users",           "list users"),
    ("🌐 Universes",       "list universes"),
    ("🔁 Retry Failed",    "retry failed"),
    # Row 3 — OS
    ("🔌 Port 8080",       "check port 8080"),
    ("🔌 Port 6405",       "check port 6405"),
    ("📋 Tomcat Log",      "show tomcat log"),
    ("📋 BO Log",          "show bo log"),
    # Row 4 — Actions
    ("🔄 Restart Tomcat",  "restart tomcat"),
    ("🧹 Clear Cache",     "clear cache"),
    ("🌐 Network Check",   "check network"),
    ("🗑 Purge Instances", "delete old instances"),
    # Row 5 — Plans
    ("🎯 Fix Failed",      "fix failed reports"),
    ("🔬 Full Diagnosis",  "full diagnosis"),
    ("🌅 Morning Check",   "morning check"),
    ("🔐 SSL Guide",       "configure ssl"),
]


class MultiBOTTab(ctk.CTkFrame):
    """Full autonomous agent UI."""

    def __init__(self, parent, bo_session=None, **kwargs):
        super().__init__(parent, fg_color=C["bg_primary"], **kwargs)
        self._bo   = bo_session
        self._coord = _get_coordinator()
        self._busy  = False
        self._alert_count = 0
        self._monitor_started = False

        self._build_ui()
        self._append_output(self._welcome_text(), tag="system")
        # Run a diagnostic on startup to catch import errors early
        self.after(500, self._startup_diagnostic)
        self._start_monitor()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=C["bg_secondary"], corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            hdr, text="🤖  MultiBOT", font=("Segoe UI", 22, "bold"),
            text_color=C["primary"]
        ).grid(row=0, column=0, padx=20, pady=12, sticky="w")

        ctk.CTkLabel(
            hdr,
            text="Autonomous SAP BO + OS Agent  •  Multi-Agent  •  Self-Healing  •  Persistent Memory",
            font=F["small"], text_color=C["text_secondary"]
        ).grid(row=0, column=1, padx=10, pady=12, sticky="w")

        # Alert badge
        self._alert_var = tk.StringVar(value="")
        self._alert_lbl = ctk.CTkLabel(
            hdr, textvariable=self._alert_var,
            font=("Segoe UI", 11, "bold"), text_color=C["danger"]
        )
        self._alert_lbl.grid(row=0, column=2, padx=10)

        # Status dot
        self._status_var = tk.StringVar(value="⚪ Ready")
        ctk.CTkLabel(
            hdr, textvariable=self._status_var,
            font=F["small"], text_color=C["text_secondary"]
        ).grid(row=0, column=3, padx=(0, 20), pady=12, sticky="e")

        # ── Body ──────────────────────────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color=C["bg_primary"])
        body.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        # Quick commands panel
        self._build_quick_panel(body)

        # Main split: output + side panel
        split = ctk.CTkFrame(body, fg_color=C["bg_primary"])
        split.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0,10))
        split.grid_columnconfigure(0, weight=1)
        split.grid_columnconfigure(1, weight=0)
        split.grid_rowconfigure(0, weight=1)

        # Output terminal
        self._build_terminal(split)

        # Side panel (alerts + knowledge)
        self._build_side_panel(split)

        # Input bar
        self._build_input_bar(body)

    def _build_quick_panel(self, parent):
        panel = ctk.CTkFrame(parent, fg_color=C["bg_secondary"], corner_radius=8)
        panel.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            panel, text="Quick Actions:", font=("Segoe UI", 11, "bold"),
            text_color=C["text_secondary"]
        ).grid(row=0, column=0, padx=12, pady=(8,4), sticky="w")

        btn_frame = ctk.CTkFrame(panel, fg_color="transparent")
        btn_frame.grid(row=1, column=0, columnspan=20, sticky="ew", padx=8, pady=(0, 8))

        cols = 10
        for i, (label, cmd) in enumerate(QUICK_COMMANDS):
            r, c = divmod(i, cols)
            # Color coding by category
            if any(w in label for w in ["Health","Servers","Failed","Disk","Diagnos","Morning","Fix"]):
                color = C["primary"]
            elif any(w in label for w in ["Reports","Users","Universes","Retry"]):
                color = C["accent"]
            elif any(w in label for w in ["Port","Tomcat","Log","BO Log"]):
                color = C["warning"]
            elif any(w in label for w in ["Restart","Cache","Network","Purge","SSL"]):
                color = C["secondary"]
            else:
                color = C["accent_teal"]

            def _make_cmd(c2=cmd):
                return lambda: self._send(c2)

            ctk.CTkButton(
                btn_frame, text=label, width=118, height=30,
                font=("Segoe UI", 10), fg_color=C["bg_tertiary"],
                hover_color=color, text_color=C["text_primary"],
                border_width=1, border_color=C["border"],
                corner_radius=6, command=_make_cmd()
            ).grid(row=r, column=c, padx=3, pady=2, sticky="w")

    def _build_terminal(self, parent):
        term = ctk.CTkFrame(parent, fg_color=C["bg_secondary"], corner_radius=8)
        term.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        term.grid_rowconfigure(0, weight=1)
        term.grid_columnconfigure(0, weight=1)

        # Terminal label row
        top = ctk.CTkFrame(term, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(8,0))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            top, text="● Agent Terminal", font=("Segoe UI", 11, "bold"),
            text_color="#10B981"
        ).grid(row=0, column=0, sticky="w")

        self._thinking_var = tk.StringVar(value="")
        ctk.CTkLabel(
            top, textvariable=self._thinking_var,
            font=("Segoe UI", 10), text_color=C["warning"]
        ).grid(row=0, column=1, sticky="w", padx=10)

        ctk.CTkButton(
            top, text="🗑 Clear", width=70, height=26,
            font=("Segoe UI", 10), fg_color=C["bg_tertiary"],
            hover_color=C["danger"], text_color=C["text_primary"],
            command=self._clear_output
        ).grid(row=0, column=2, sticky="e")

        # Output text widget
        self._output = tk.Text(
            term,
            bg=C["bg_primary"], fg=C["text_primary"],
            font=("Consolas", 11),
            state="disabled", wrap="word",
            relief="flat", bd=0,
            padx=14, pady=10,
            selectbackground=C["primary"],
        )
        self._output.grid(row=1, column=0, sticky="nsew", padx=0, pady=(4,0))
        term.grid_rowconfigure(1, weight=1)

        sb = ctk.CTkScrollbar(term, command=self._output.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self._output.configure(yscrollcommand=sb.set)

        # Color tags
        self._output.tag_configure("user",    foreground="#38BDF8", font=("Consolas", 11, "bold"))
        self._output.tag_configure("system",  foreground="#94A3B8", font=("Consolas", 10))
        self._output.tag_configure("ok",      foreground="#10B981")
        self._output.tag_configure("err",     foreground="#EF4444")
        self._output.tag_configure("warn",    foreground="#F59E0B")
        self._output.tag_configure("info",    foreground="#8B5CF6")
        self._output.tag_configure("section", foreground="#3B82F6", font=("Consolas", 11, "bold"))
        self._output.tag_configure("agent",   foreground="#22D3EE")

    def _build_side_panel(self, parent):
        side = ctk.CTkFrame(parent, fg_color=C["bg_secondary"], corner_radius=8, width=240)
        side.grid(row=0, column=1, sticky="nsew")
        side.grid_propagate(False)
        side.grid_rowconfigure(2, weight=1)
        side.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            side, text="🚨 Live Alerts", font=("Segoe UI", 12, "bold"),
            text_color=C["danger"]
        ).grid(row=0, column=0, padx=12, pady=(10,4), sticky="w")

        self._alerts_box = tk.Text(
            side, bg=C["bg_primary"], fg=C["text_secondary"],
            font=("Consolas", 9), state="disabled",
            wrap="word", relief="flat", bd=0, padx=8, pady=6, height=10
        )
        self._alerts_box.grid(row=1, column=0, sticky="nsew", padx=6, pady=4)

        ctk.CTkLabel(
            side, text="📚 KB Stats", font=("Segoe UI", 11, "bold"),
            text_color=C["text_secondary"]
        ).grid(row=2, column=0, padx=12, pady=(8,4), sticky="w")

        self._kb_var = tk.StringVar(value="Loading…")
        ctk.CTkLabel(
            side, textvariable=self._kb_var,
            font=("Consolas", 9), text_color=C["text_muted"],
            justify="left"
        ).grid(row=3, column=0, padx=12, pady=4, sticky="nw")

        # KB refresh button
        ctk.CTkButton(
            side, text="↻ Refresh", width=80, height=24,
            font=("Segoe UI", 10), fg_color=C["bg_tertiary"],
            hover_color=C["primary"], text_color=C["text_primary"],
            command=self._refresh_kb_stats
        ).grid(row=4, column=0, padx=12, pady=(0, 12), sticky="w")

        ctk.CTkLabel(
            side, text="🎯 Active Plan", font=("Segoe UI", 11, "bold"),
            text_color=C["text_secondary"]
        ).grid(row=5, column=0, padx=12, pady=(4, 4), sticky="w")

        self._plan_var = tk.StringVar(value="None")
        ctk.CTkLabel(
            side, textvariable=self._plan_var,
            font=("Consolas", 9), text_color=C["accent"],
            justify="left"
        ).grid(row=6, column=0, padx=12, pady=4, sticky="nw")

        self._refresh_kb_stats()

    def _build_input_bar(self, parent):
        bar = ctk.CTkFrame(parent, fg_color=C["bg_secondary"], corner_radius=8)
        bar.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            bar, text="🤖", font=("Segoe UI", 16)
        ).grid(row=0, column=0, padx=(12, 6), pady=10)

        self._input_var = tk.StringVar()
        self._entry = ctk.CTkEntry(
            bar, textvariable=self._input_var,
            font=("Segoe UI", 13),
            fg_color=C["bg_input"], text_color=C["text_primary"],
            border_color=C["border"], border_width=1,
            placeholder_text="Type a command… e.g. 'system health', 'show failed reports', 'fix failed reports'",
            height=40
        )
        self._entry.grid(row=0, column=1, sticky="ew", padx=6, pady=10)
        self._entry.bind("<Return>", lambda e: self._on_send())
        self._entry.bind("<Up>",     self._history_up)
        self._entry.bind("<Down>",   self._history_down)
        self._entry.focus()

        self._send_btn = ctk.CTkButton(
            bar, text="▶  Send", width=90, height=40,
            font=("Segoe UI", 13, "bold"),
            fg_color=C["primary"], hover_color=C["primary_hover"],
            text_color="white", command=self._on_send
        )
        self._send_btn.grid(row=0, column=2, padx=(0, 10), pady=10)

        # Stop button
        self._stop_btn = ctk.CTkButton(
            bar, text="⏹ Stop", width=70, height=40,
            font=("Segoe UI", 11),
            fg_color=C["bg_tertiary"], hover_color=C["danger"],
            text_color=C["text_primary"],
            command=self._stop_action
        )
        self._stop_btn.grid(row=0, column=3, padx=(0, 12), pady=10)

        # Command history
        self._cmd_history = []
        self._history_pos  = -1

    # ── Output helpers ────────────────────────────────────────────────────────

    def _append_output(self, text: str, tag: str = ""):
        """Thread-safe append to the output terminal."""
        def _do():
            self._output.configure(state="normal")
            if tag:
                self._output.insert("end", text + "\n", tag)
            else:
                # Auto-tag based on content
                lower = text.lower()
                if text.startswith("✅") or "success" in lower:
                    t = "ok"
                elif text.startswith("❌") or "error" in lower or "failed" in lower:
                    t = "err"
                elif text.startswith("⚠") or "warning" in lower:
                    t = "warn"
                elif text.startswith("ℹ") or text.startswith("📊") or text.startswith("📋"):
                    t = "info"
                elif text.startswith("─") or text.startswith("━"):
                    t = "section"
                elif text.startswith("🤖") or text.startswith("💡"):
                    t = "agent"
                else:
                    t = ""
                self._output.insert("end", text + "\n", t)

            self._output.configure(state="disabled")
            self._output.see("end")

        try:
            self.after(0, _do)
        except Exception:
            pass

    def _clear_output(self):
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")
        self._output.configure(state="disabled")
        self._append_output("Terminal cleared.", "system")

    def _set_status(self, text: str):
        try:
            self.after(0, lambda: self._status_var.set(text))
        except Exception:
            pass

    def _set_thinking(self, text: str):
        try:
            self.after(0, lambda: self._thinking_var.set(text))
        except Exception:
            pass

    # ── Input handling ────────────────────────────────────────────────────────

    def _on_send(self):
        text = self._input_var.get().strip()
        if not text:
            return
        self._send(text)

    def _send(self, text: str):
        if self._busy:
            self._append_output("⚠  Agent busy. Wait or click ⏹ Stop.", "warn")
            return

        # Add to history
        if text not in self._cmd_history:
            self._cmd_history.append(text)
        self._history_pos = -1

        self._input_var.set("")
        now = datetime.now().strftime("%H:%M:%S")
        self._append_output(f"\n[{now}]  🧑  {text}", "user")

        # Save to KB memory
        try:
            from memory.knowledge_base import kb
            kb.save_message("user", text)
        except Exception:
            pass

        self._busy = True
        self._set_status("🟡 Working…")
        self._set_thinking("  ⟳ Processing…")
        self._send_btn.configure(state="disabled")

        if not self._coord:
            self._coord = _get_coordinator()

        if self._coord:
            # Check for multi-step plan — show in side panel
            from agents.coordinator_agent import parse_intent
            intent = parse_intent(text)
            if intent.get("action") == "multi_step":
                plan = intent.get("plan","")
                self.after(0, lambda: self._plan_var.set(
                    f"▶ {plan}\n(running…)"
                ))

            self._coord.route(
                text,
                emit=lambda msg: self._append_output(msg),
                done=self._on_done
            )
        else:
            # Try loading once more (in case import was deferred)
            self._coord = _get_coordinator()
            if self._coord:
                self._append_output("✅  Agent loaded on retry! Running command...", "ok")
                self._coord.route(
                    text,
                    emit=lambda msg: self._append_output(msg),
                    done=self._on_done
                )
                return
            # Still failed — show the real error
            err = _AGENT_IMPORT_ERROR[0]
            if err:
                self._append_output("❌  Agent failed to load. Full error:", "err")
                for line in err.splitlines()[:25]:
                    self._append_output(f"   {line}", "err")
                self._append_output(
                    "\n💡  Fix: check that D:\\bo-commander\\claude\\bo-commander\\agents\\ exists"
                    " and contains coordinator_agent.py", "warn"
                )
            else:
                self._append_output(
                    "❌  CoordinatorAgent could not be imported.\n"
                    f"   Searched sys.path[0]: {sys.path[0] if sys.path else 'none'}\n"
                    f"   agents/ found: {os.path.isdir(os.path.join(sys.path[0], 'agents')) if sys.path else False}",
                    "err"
                )
            self._on_done(None)

    def _on_done(self, result):
        self._busy = False
        self._set_thinking("")
        self._set_status("⚪ Ready")
        try:
            self.after(0, lambda: self._send_btn.configure(state="normal"))
            self.after(0, lambda: self._plan_var.set("None"))
        except Exception:
            pass

        # Save response to KB
        if result:
            try:
                from memory.knowledge_base import kb
                kb.save_message("assistant", result.message if hasattr(result, 'message') else str(result))
            except Exception:
                pass

        # Refresh alerts
        self.after(1000, self._refresh_alerts)

    def _stop_action(self):
        self._busy = False
        self._set_thinking("")
        self._set_status("⚪ Ready (stopped)")
        self._append_output("⏹  Stopped.", "warn")
        try:
            self._send_btn.configure(state="normal")
        except Exception:
            pass

    def _history_up(self, event):
        if not self._cmd_history:
            return
        self._history_pos = min(self._history_pos + 1, len(self._cmd_history) - 1)
        self._input_var.set(self._cmd_history[-(self._history_pos + 1)])

    def _history_down(self, event):
        if self._history_pos <= 0:
            self._input_var.set("")
            self._history_pos = -1
            return
        self._history_pos -= 1
        self._input_var.set(self._cmd_history[-(self._history_pos + 1)])

    # ── Background monitor ────────────────────────────────────────────────────

    def _start_monitor(self):
        if self._monitor_started or not self._coord:
            return
        try:
            self._coord.start_monitoring(
                ui_emit=lambda msg: self._append_output(f"🔧 [Auto-Heal] {msg}", "warn"),
                auto_heal=False  # Set True to enable auto self-healing
            )
            self._monitor_started = True
        except Exception:
            pass

        # Start alert refresh loop
        def _alert_loop():
            while True:
                time.sleep(30)
                try:
                    self._refresh_alerts()
                except Exception:
                    pass

        threading.Thread(target=_alert_loop, daemon=True).start()

    def _refresh_alerts(self):
        """Pull recent alerts from MonitoringAgent and update side panel."""
        try:
            if not self._coord:
                return
            alerts = self._coord.get_alerts()
            if not alerts:
                self.after(0, self._update_alerts_display, [], 0)
                return

            crit = [a for a in alerts if a.get("severity") == "critical"]
            self._alert_count = len(crit)
            badge = f"🚨 {len(crit)} Alert{'s' if len(crit) != 1 else ''}" if crit else ""
            self.after(0, lambda: self._alert_var.set(badge))
            self.after(0, self._update_alerts_display, alerts[-8:], self._alert_count)
        except Exception:
            pass

    def _update_alerts_display(self, alerts, crit_count):
        self._alerts_box.configure(state="normal")
        self._alerts_box.delete("1.0", "end")
        if not alerts:
            self._alerts_box.insert("end", "✅ No active alerts\n")
        else:
            for a in alerts:
                icon = "🔴" if a.get("severity") == "critical" else "🟡"
                ts   = str(a.get("ts",""))[-8:]
                self._alerts_box.insert("end", f"{icon} {ts}  {a.get('message','')[:40]}\n")
        self._alerts_box.configure(state="disabled")

    def _refresh_kb_stats(self):
        """Update the knowledge base stats in the side panel."""
        try:
            from memory.knowledge_base import kb
            stats = kb.get_stats()
            text  = (
                f"Incidents:   {stats.get('incidents', 0)}\n"
                f"Remediations:{stats.get('remediations', 0)}\n"
                f"Server evts: {stats.get('server_events', 0)}\n"
                f"AI messages: {stats.get('ai_messages', 0)}\n"
                f"Playbooks:   {stats.get('playbooks', 0)}\n"
            )
            self.after(0, lambda: self._kb_var.set(text))
        except Exception as e:
            self.after(0, lambda: self._kb_var.set(f"KB unavailable\n{str(e)[:40]}"))

    # ── Welcome text ──────────────────────────────────────────────────────────

    def _startup_diagnostic(self):
        """Called 500ms after UI loads — shows real import errors."""
        coord = _get_coordinator()
        if coord:
            self._append_output("✅  Multi-agent system ready. Type 'help' for commands.", "ok")
        else:
            err = _AGENT_IMPORT_ERROR[0]
            self._append_output("❌  AGENT LOAD FAILED — Cannot import CoordinatorAgent", "err")
            self._append_output(f"   sys.path[0]: {sys.path[0] if sys.path else 'none'}", "err")
            agents_path = os.path.join(sys.path[0], "agents") if sys.path else "unknown"
            self._append_output(f"   agents/ path: {agents_path}", "err")
            self._append_output(f"   agents/ exists: {os.path.isdir(agents_path)}", "err")
            if err:
                self._append_output("   Full error:", "err")
                for line in err.splitlines()[:20]:
                    self._append_output(f"   {line}", "err")
            else:
                # Try to get the error now
                try:
                    from agents.coordinator_agent import CoordinatorAgent
                except Exception as ex:
                    import traceback
                    tb = traceback.format_exc()
                    self._append_output(f"   Import attempt: {ex}", "err")
                    for line in tb.splitlines()[:15]:
                        self._append_output(f"   {line}", "err")
            self._append_output(
                "\n💡  Make sure these files exist:\n"
                f"   {os.path.join(sys.path[0] if sys.path else '?', 'agents', 'coordinator_agent.py')}\n"
                f"   {os.path.join(sys.path[0] if sys.path else '?', 'agents', 'sap_agent.py')}\n"
                f"   {os.path.join(sys.path[0] if sys.path else '?', 'agents', 'system_agent.py')}\n"
                f"   {os.path.join(sys.path[0] if sys.path else '?', 'agents', 'base_agent.py')}",
                "warn"
            )

    def _welcome_text(self) -> str:
        try:
            from core.sapbo_connection import bo_session
            import platform
            conn = f"{'🟢' if bo_session.connected else '🔴'} {bo_session.cms_details.get('user','')}@{bo_session.cms_details.get('host','')}"
        except Exception:
            conn = "⚪ Not connected"

        try:
            from bridges.java_admin_sdk import java_sdk
            java_status = java_sdk.availability_message()
        except Exception:
            java_status = "Java bridge: checking…"

        return f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🤖  MultiBOT v3.0  —  Autonomous SAP BO Agent
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SAP BO:     {conn}
Java SDK:   {java_status}

Architecture:
  CoordinatorAgent → routes all commands
  SAPAgent         → REST API + Java Admin SDK
  SystemAgent      → OS, services, logs, ports
  MonitoringAgent  → continuous health + self-healing
  KnowledgeBase    → persistent incidents + playbooks

━━━  Quick start  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Type 'help' for all commands
  Type 'system health' for full health snapshot
  Type 'fix failed reports' for multi-step auto-fix
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""