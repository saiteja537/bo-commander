"""
sentinel.py — AI Sentinel Page
KEY FIX: Accepts SentinelAgent as constructor arg (agent=None).
main_window.py must pass the shared agent: SentinelPage(master, agent=self.sentinel_agent)
"""
import threading
import customtkinter as ctk
from config import Config
import logging

logger = logging.getLogger("SentinelPage")

SEVERITY_COLORS = {
    'CRITICAL': '#DC2626', 'HIGH': '#EF4444',
    'MEDIUM': '#F59E0B', 'LOW': '#10B981', 'UNKNOWN': '#6B7280',
}
PRIORITY_COLORS = {'P1': '#DC2626', 'P2': '#F59E0B', 'P3': '#3B82F6', 'P4': '#6B7280'}


class SentinelPage(ctk.CTkFrame):
    def __init__(self, master, agent=None, **kwargs):
        super().__init__(master, fg_color=Config.COLORS['bg_primary'], **kwargs)
        self._destroyed = False
        self.agent = agent
        if self.agent:
            self.agent.ui_callback = self._safe_refresh
        self._build_ui()
        if self.agent:
            self.after(800, lambda: self.agent.investigate("AUTO_STARTUP_SCAN"))

    def _safe_after(self, ms, fn):
        if not self._destroyed:
            try:
                self.after(ms, fn)
            except Exception:
                pass

    def _safe_refresh(self):
        self._safe_after(0, self.render)

    def destroy(self):
        self._destroyed = True
        if self.agent:
            self.agent.ui_callback = None
        super().destroy()

    def _build_ui(self):
        ctrl = ctk.CTkFrame(self, fg_color=Config.COLORS['bg_secondary'])
        ctrl.pack(fill='x', padx=15, pady=(15, 5))
        left = ctk.CTkFrame(ctrl, fg_color='transparent')
        left.pack(side='left', padx=12, pady=8)
        ctk.CTkLabel(left, text="🤖  AI Sentinel",
                     font=Config.FONTS['sub_header'],
                     text_color=Config.COLORS['text_primary']).pack(anchor='w')
        ctk.CTkLabel(left,
                     text="8-layer diagnostics: OS · Network · Events · BO Logs · DB · Correlation · AI",
                     font=Config.FONTS['small'],
                     text_color=Config.COLORS['text_secondary']).pack(anchor='w')
        btn_f = ctk.CTkFrame(ctrl, fg_color='transparent')
        btn_f.pack(side='right', padx=10, pady=8)
        ctk.CTkButton(btn_f, text="🚨 Emergency Scan", width=160,
                      fg_color=Config.COLORS['danger'], hover_color='#B91C1C',
                      command=self._emergency_scan).pack(side='left', padx=4)
        ctk.CTkButton(btn_f, text="⟳ Health Check", width=140,
                      fg_color=Config.COLORS['primary'],
                      command=self._health_scan).pack(side='left', padx=4)
        ctk.CTkButton(btn_f, text="🗑 Clear", width=80,
                      fg_color=Config.COLORS['bg_tertiary'],
                      command=self._clear).pack(side='left', padx=4)
        self.status_lbl = ctk.CTkLabel(self, text="Ready",
                                        font=Config.FONTS['small'],
                                        text_color=Config.COLORS['text_secondary'])
        self.status_lbl.pack(anchor='w', padx=20, pady=(0, 4))
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=Config.COLORS['bg_secondary'])
        self.scroll.pack(fill='both', expand=True, padx=15, pady=(0, 15))
        if not self.agent:
            ctk.CTkLabel(self.scroll,
                         text="⚠️  SentinelAgent not connected.\n\n"
                              "In main_window.py, pass agent=self.sentinel_agent when creating SentinelPage.",
                         font=Config.FONTS['body'],
                         text_color=Config.COLORS['warning'], justify='left').pack(pady=40, padx=20)

    def _emergency_scan(self):
        if not self.agent:
            return
        self._set_status("🚨 Emergency scan running...")
        threading.Thread(target=lambda: self.agent.investigate("EMERGENCY_BUTTON"), daemon=True).start()

    def _health_scan(self):
        if not self.agent:
            return
        self._set_status("⏳ Health scan running...")
        threading.Thread(target=lambda: self.agent.investigate("MANUAL_HEALTH_SCAN"), daemon=True).start()

    def _clear(self):
        if self.agent:
            self.agent.clear_incidents()
        self._safe_after(0, self.render)

    def _set_status(self, text):
        if not self._destroyed:
            try:
                self.status_lbl.configure(text=text)
            except Exception:
                pass

    def render(self):
        if self._destroyed:
            return
        try:
            if not self.winfo_exists():
                return
            for w in self.scroll.winfo_children():
                try:
                    w.destroy()
                except Exception:
                    pass
        except Exception:
            return
        if not self.agent:
            return
        incidents = self.agent.get_incidents()
        self._set_status(f"{len(incidents)} incident(s)" if incidents else "✅  All systems healthy")
        if not incidents:
            ctk.CTkLabel(self.scroll,
                         text="✅  No incidents recorded. Run a scan to check system health.",
                         font=Config.FONTS['body'],
                         text_color=Config.COLORS['text_secondary']).pack(pady=50)
            return
        for inc in incidents:
            self._render_card(inc)

    def _render_card(self, inc):
        try:
            sev = inc.get('severity', 'MEDIUM')
            pri = inc.get('priority', 'P2')
            card = ctk.CTkFrame(self.scroll, fg_color=Config.COLORS['bg_tertiary'],
                                border_width=1, border_color=SEVERITY_COLORS.get(sev, '#F59E0B'))
            card.pack(fill='x', pady=4, padx=5)
            tr = ctk.CTkFrame(card, fg_color='transparent')
            tr.pack(fill='x', padx=12, pady=(8, 2))
            ctk.CTkLabel(tr, text=f"  {sev}  ",
                         fg_color=SEVERITY_COLORS.get(sev, '#F59E0B'), corner_radius=4,
                         font=('Segoe UI', 11, 'bold'), text_color='white').pack(side='left', padx=(0, 8))
            ctk.CTkLabel(tr, text=inc.get('title', 'Incident'),
                         font=('Segoe UI', 13, 'bold'),
                         text_color=Config.COLORS['text_primary']).pack(side='left')
            ctk.CTkLabel(tr, text=f"{pri}  {inc.get('timestamp', '')}",
                         font=Config.FONTS['small'],
                         text_color=PRIORITY_COLORS.get(pri, '#6B7280')).pack(side='right')
            for label, key, color in [
                ("Root Cause:", 'root_cause', Config.COLORS['text_primary']),
                ("Chain:", 'failure_chain', Config.COLORS['warning']),
            ]:
                val = inc.get(key, '')
                if val:
                    row = ctk.CTkFrame(card, fg_color='transparent')
                    row.pack(fill='x', padx=12, pady=1)
                    ctk.CTkLabel(row, text=label, font=('Segoe UI', 11, 'bold'),
                                 text_color=Config.COLORS['text_secondary'], width=90).pack(side='left')
                    ctk.CTkLabel(row, text=str(val)[:130], font=Config.FONTS['small'],
                                 text_color=color, wraplength=820, justify='left').pack(side='left', padx=5)
            steps = inc.get('solution_steps', [])
            if steps:
                sf = ctk.CTkFrame(card, fg_color=Config.COLORS['bg_secondary'])
                sf.pack(fill='x', padx=12, pady=(4, 8))
                ctk.CTkLabel(sf, text="  🔧 Fix Steps:", font=('Segoe UI', 11, 'bold'),
                             text_color=Config.COLORS['accent']).pack(anchor='w', padx=8, pady=(4, 0))
                for i, step in enumerate(steps[:5], 1):
                    ctk.CTkLabel(sf, text=f"  {i}. {str(step)[:110]}",
                                 font=Config.FONTS['small'],
                                 text_color=Config.COLORS['text_primary'],
                                 wraplength=860, justify='left').pack(anchor='w', padx=12, pady=1)
            fr = ctk.CTkFrame(card, fg_color='transparent')
            fr.pack(fill='x', padx=12, pady=(0, 6))
            ctk.CTkLabel(fr,
                         text=f"Owner: {inc.get('owner','BO Admin')}   ETA: {inc.get('estimated_resolution_time','N/A')}",
                         font=Config.FONTS['small'],
                         text_color=Config.COLORS['text_secondary']).pack(side='left')
        except Exception as e:
            logger.error(f"Card render error: {e}")
