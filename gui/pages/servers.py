"""
servers.py — Server Management Page (Enhanced)
Preserves all original features:
  - CMC Hierarchy sidebar tree
  - PID display
  - Stop / Restart / Start controls
  - ⚙️ Properties popup (JSON)
  - 📊 Performance — Live Matplotlib CPU/RAM graph (updates every 2s)

NEW additions:
  - Inline CPU % bar + value in every server row (live, updates every 5s)
  - Inline RAM % bar + value in every server row (live, updates every 5s)
  - Color-coded bars: green < 60%, yellow < 85%, red >= 85%
  - Auto-refresh toggle in header
  - Last-updated timestamp
"""

import customtkinter as ctk
import threading
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkinter import ttk, messagebox
from datetime import datetime
from config import Config
from core.sapbo_connection import bo_session


def _bar_color(pct: float) -> str:
    """Green → Yellow → Red based on utilization."""
    if pct >= 85:
        return Config.COLORS['danger']
    if pct >= 60:
        return Config.COLORS['warning']
    return Config.COLORS['success']


class _MiniBar(ctk.CTkFrame):
    """
    A compact inline progress bar widget showing a label, fill bar, and % text.
    Width is fixed so all rows stay aligned.
    """
    BAR_W = 90
    BAR_H = 10

    def __init__(self, master, label: str, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._label = label
        self._pct   = 0.0

        ctk.CTkLabel(self, text=label, font=("Segoe UI", 9),
                     text_color=Config.COLORS['text_secondary'],
                     width=30, anchor="e").grid(row=0, column=0, padx=(0, 4))

        # Track (background)
        self._track = ctk.CTkFrame(self, width=self.BAR_W, height=self.BAR_H,
                                    fg_color=Config.COLORS['bg_primary'],
                                    corner_radius=5)
        self._track.grid(row=0, column=1)
        self._track.grid_propagate(False)

        # Fill
        self._fill = ctk.CTkFrame(self._track, width=0, height=self.BAR_H,
                                   fg_color=Config.COLORS['success'],
                                   corner_radius=5)
        self._fill.place(x=0, y=0)

        self._val_lbl = ctk.CTkLabel(self, text="—", font=("Consolas", 10),
                                      text_color=Config.COLORS['text_primary'],
                                      width=38, anchor="w")
        self._val_lbl.grid(row=0, column=2, padx=(4, 0))

    def set_value(self, pct: float):
        """Update bar fill and text. Safe to call from any thread via .after()."""
        self._pct  = max(0.0, min(100.0, float(pct or 0)))
        fill_w     = int(self.BAR_W * self._pct / 100)
        color      = _bar_color(self._pct)
        try:
            self._fill.configure(width=fill_w, fg_color=color)
            self._val_lbl.configure(text=f"{self._pct:.1f}%", text_color=color)
        except Exception:
            pass


class ServersPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._destroyed     = False
        self._auto_refresh  = True          # auto-refresh every 5 s
        self._refresh_job   = None
        self._metric_jobs   = {}            # sid → after-job id (per-row metric polling)
        self._row_widgets   = {}            # sid → {'cpu': _MiniBar, 'ram': _MiniBar}
        self._server_data   = []            # last fetched server list

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True)

        self._build_sidebar()
        self._build_body()

        self.load_sidebar_data()
        self.refresh_all()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def _safe_after(self, ms, fn):
        if not self._destroyed:
            try:
                self.after(ms, fn)
            except Exception:
                pass

    def destroy(self):
        self._destroyed = True
        # Cancel all pending after-jobs
        if self._refresh_job:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
        for job in self._metric_jobs.values():
            try:
                self.after_cancel(job)
            except Exception:
                pass
        super().destroy()

    # ── sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self.container, width=280,
                                     fg_color=Config.COLORS['bg_secondary'])
        self.sidebar.pack(side="left", fill="y", padx=(0, 5), pady=5)
        self.sidebar.pack_propagate(False)

        ctk.CTkLabel(self.sidebar, text="🖥️ CMC Hierarchy",
                     font=("Segoe UI", 16, "bold")).pack(pady=15)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
                         background="#1E293B", foreground="white",
                         fieldbackground="#1E293B", borderwidth=0)
        style.map("Treeview", background=[('selected', Config.COLORS['primary'])])

        self.tree = ttk.Treeview(self.sidebar, show="tree", selectmode="browse")
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)

        self.tree.insert("", "end", "srv_list",   text="Servers List", open=True)
        self.tree.insert("", "end", "nodes_root", text="Nodes",        open=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

    def load_sidebar_data(self):
        def fetch():
            try:
                nodes = bo_session.get_cmc_nodes_list()
                self._safe_after(0, lambda: [
                    self.tree.insert("nodes_root", "end",
                                     f"node_{n['id']}", text=f"📦 {n['col1']}")
                    for n in nodes
                ])
            except Exception:
                pass
        threading.Thread(target=fetch, daemon=True).start()

    def on_tree_select(self, event):
        sel = self.tree.focus()
        if sel == "srv_list":
            self.lbl_title.configure(text="All Managed Servers")
        elif sel.startswith("node_"):
            self.lbl_title.configure(
                text=f"Node: {self.tree.item(sel, 'text')}"
            )
        self.refresh_all()

    # ── body / header ─────────────────────────────────────────────────────────

    def _build_body(self):
        self.body = ctk.CTkFrame(self.container, fg_color="transparent")
        self.body.pack(side="right", fill="both", expand=True, padx=5, pady=5)

        # ── header bar ────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self.body, fg_color="transparent")
        hdr.pack(fill="x", pady=(0, 6))

        self.lbl_title = ctk.CTkLabel(hdr, text="Managed Servers",
                                       font=("Segoe UI", 22, "bold"))
        self.lbl_title.pack(side="left")

        # Auto-refresh toggle
        self._auto_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(hdr, text="Auto-refresh (5s)",
                        variable=self._auto_var,
                        text_color=Config.COLORS['text_secondary'],
                        command=self._toggle_auto).pack(side="right", padx=8)

        ctk.CTkButton(hdr, text="🔄 Refresh", width=100,
                      command=self.refresh_all).pack(side="right", padx=4)

        # Last updated label
        self.lbl_updated = ctk.CTkLabel(hdr, text="",
                                         font=("Segoe UI", 10),
                                         text_color=Config.COLORS['text_secondary'])
        self.lbl_updated.pack(side="right", padx=12)

        # ── column header row ─────────────────────────────────────────────────
        col_hdr = ctk.CTkFrame(self.body, fg_color=Config.COLORS['bg_tertiary'],
                                height=32)
        col_hdr.pack(fill="x", padx=5, pady=(0, 2))
        col_hdr.pack_propagate(False)

        for text, width, anchor in [
            ("Server Name",  260, "w"),
            ("PID",           80, "w"),
            ("Status",        90, "w"),
            ("CPU",          160, "w"),
            ("RAM",          160, "w"),
            ("Actions",      260, "w"),
        ]:
            ctk.CTkLabel(col_hdr, text=text, width=width, anchor=anchor,
                         font=("Segoe UI", 11, "bold"),
                         text_color=Config.COLORS['text_secondary']).pack(
                side="left", padx=6, pady=6)

        # ── scrollable server list ────────────────────────────────────────────
        self.scroll = ctk.CTkScrollableFrame(self.body,
                                              fg_color=Config.COLORS['bg_secondary'])
        self.scroll.pack(fill="both", expand=True)

    # ── data fetch ────────────────────────────────────────────────────────────

    def refresh_all(self):
        """Cancel metric pollers, clear list, fetch fresh server data."""
        # Stop per-row metric polling
        for job in list(self._metric_jobs.values()):
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._metric_jobs.clear()
        self._row_widgets.clear()

        if self._destroyed:
            return
        try:
            for w in self.scroll.winfo_children():
                w.destroy()
        except Exception:
            return

        self.loader = ctk.CTkLabel(self.scroll, text="⌛ Syncing with CMS...",
                                    text_color="gray")
        self.loader.pack(pady=40)
        threading.Thread(target=self._fetch_thread, daemon=True).start()

    def _fetch_thread(self):
        try:
            data = bo_session.get_all_servers()
            self._server_data = data or []
            self._safe_after(0, lambda: self._render_rows(self._server_data))
        except Exception as e:
            self._safe_after(0, lambda: self._safe_loader_update(f"❌ Error: {e}"))

    def _safe_loader_update(self, text):
        try:
            self.loader.configure(text=text)
        except Exception:
            pass

    # ── render ────────────────────────────────────────────────────────────────

    def _render_rows(self, data):
        if self._destroyed:
            return
        try:
            self.loader.destroy()
        except Exception:
            pass

        ts = datetime.now().strftime("%H:%M:%S")
        try:
            self.lbl_updated.configure(text=f"Updated {ts}")
        except Exception:
            pass

        if not data:
            ctk.CTkLabel(self.scroll, text="No servers found.",
                         text_color=Config.COLORS['text_secondary']).pack(pady=40)
            return

        for s in data:
            self._render_row(s)

        # Start polling metrics for all running servers
        for s in data:
            if str(s.get('status', '')).lower() == 'running':
                self._start_metric_poll(s['id'])

        # Schedule auto-refresh of full list
        if self._auto_var.get():
            self._schedule_auto_refresh()

    def _render_row(self, s):
        sid     = s['id']
        status  = str(s.get('status', 'Unknown'))
        is_run  = status.lower() == 'running'
        st_col  = Config.COLORS['success'] if is_run else Config.COLORS['danger']

        row = ctk.CTkFrame(self.scroll,
                            fg_color=Config.COLORS['bg_tertiary'], height=56)
        row.pack(fill="x", pady=2, padx=5)
        row.pack_propagate(False)

        # ── Server name + type ────────────────────────────────────────────────
        info = ctk.CTkFrame(row, fg_color="transparent", width=260)
        info.pack(side="left", padx=10, pady=8)
        info.pack_propagate(False)
        name = str(s.get('name', 'Unknown'))
        ctk.CTkLabel(info, text=name[:34],
                     font=("Segoe UI", 12, "bold"),
                     text_color=Config.COLORS['text_primary'],
                     anchor="w").pack(anchor="w")
        kind = str(s.get('kind', '')).replace('Server', '')
        ctk.CTkLabel(info, text=f"Type: {kind}",
                     font=("Consolas", 10),
                     text_color=Config.COLORS['text_secondary'],
                     anchor="w").pack(anchor="w")

        # ── PID ───────────────────────────────────────────────────────────────
        ctk.CTkLabel(row, text=f"PID: {s.get('pid', 'N/A')}",
                     font=("Consolas", 10), width=80, anchor="w",
                     text_color=Config.COLORS['text_secondary']).pack(
            side="left", padx=4)

        # ── Status dot ────────────────────────────────────────────────────────
        ctk.CTkLabel(row, text=f"● {status}",
                     font=("Segoe UI", 11, "bold"), width=90, anchor="w",
                     text_color=st_col).pack(side="left", padx=4)

        # ── CPU mini-bar ──────────────────────────────────────────────────────
        cpu_bar = _MiniBar(row, "CPU")
        cpu_bar.pack(side="left", padx=8)

        # ── RAM mini-bar ──────────────────────────────────────────────────────
        ram_bar = _MiniBar(row, "RAM")
        ram_bar.pack(side="left", padx=8)

        # Store refs for metric updates
        self._row_widgets[sid] = {'cpu': cpu_bar, 'ram': ram_bar}

        if not is_run:
            # Show dashes for stopped servers
            cpu_bar._val_lbl.configure(text="—")
            ram_bar._val_lbl.configure(text="—")

        # ── Action buttons ────────────────────────────────────────────────────
        act = ctk.CTkFrame(row, fg_color="transparent")
        act.pack(side="right", padx=10)

        ctk.CTkButton(act, text="📊 Perf", width=70, height=26,
                      fg_color="#8B5CF6",
                      command=lambda i=sid, n=name: self.open_perf_dashboard(i, n)
                      ).pack(side="left", padx=2)

        ctk.CTkButton(act, text="⚙️ Props", width=70, height=26,
                      fg_color=Config.COLORS['bg_secondary'],
                      command=lambda i=sid: self.view_properties(i)
                      ).pack(side="left", padx=2)

        if is_run:
            ctk.CTkButton(act, text="Stop", width=55, height=26,
                          fg_color=Config.COLORS['danger'],
                          command=lambda i=sid: self.execute_cmd(i, 'stop')
                          ).pack(side="left", padx=2)
            ctk.CTkButton(act, text="Restart", width=65, height=26,
                          fg_color="#F59E0B",
                          command=lambda i=sid: self.execute_cmd(i, 'restart')
                          ).pack(side="left", padx=2)
        else:
            ctk.CTkButton(act, text="Start", width=55, height=26,
                          fg_color=Config.COLORS['success'],
                          command=lambda i=sid: self.execute_cmd(i, 'start')
                          ).pack(side="left", padx=2)

    # ── inline metric polling ─────────────────────────────────────────────────

    def _start_metric_poll(self, sid):
        """Fetch metrics for one server in background, then schedule next poll."""
        def fetch():
            try:
                m = bo_session.get_server_metrics(sid)
                cpu = float(m.get('cpu', 0) or 0)
                ram = float(m.get('ram', 0) or 0)
                self._safe_after(0, lambda: self._apply_metrics(sid, cpu, ram))
            except Exception:
                pass
        threading.Thread(target=fetch, daemon=True).start()

    def _apply_metrics(self, sid, cpu: float, ram: float):
        """Push fresh metrics into the row's mini-bars, schedule next poll."""
        if self._destroyed:
            return
        widgets = self._row_widgets.get(sid)
        if widgets:
            try:
                widgets['cpu'].set_value(cpu)
                widgets['ram'].set_value(ram)
            except Exception:
                pass

        # Re-poll every 5 seconds
        if not self._destroyed and sid in self._row_widgets:
            try:
                job = self.after(5000, lambda: self._start_metric_poll(sid))
                self._metric_jobs[sid] = job
            except Exception:
                pass

    # ── auto-refresh full list ────────────────────────────────────────────────

    def _toggle_auto(self):
        if self._auto_var.get():
            self._schedule_auto_refresh()
        else:
            if self._refresh_job:
                try:
                    self.after_cancel(self._refresh_job)
                except Exception:
                    pass

    def _schedule_auto_refresh(self):
        if self._destroyed or not self._auto_var.get():
            return
        try:
            self._refresh_job = self.after(30000, self._auto_do_refresh)
        except Exception:
            pass

    def _auto_do_refresh(self):
        if not self._destroyed and self._auto_var.get():
            self.refresh_all()

    # ── server controls ───────────────────────────────────────────────────────

    def execute_cmd(self, sid, action):
        success, msg = bo_session.toggle_server_state(sid, action)
        if success:
            messagebox.showinfo("Success", f"Command '{action}' accepted.")
            self._safe_after(3000, self.refresh_all)
        else:
            messagebox.showerror("Error", f"Command failed: {msg}")

    # ── Properties popup ──────────────────────────────────────────────────────

    def view_properties(self, sid):
        modal = ctk.CTkToplevel(self)
        modal.title(f"Properties: {sid}")
        modal.geometry("800x800")
        modal.attributes("-topmost", True)
        txt = ctk.CTkTextbox(modal, font=("Consolas", 11),
                              fg_color="#0F172A", text_color="#E2E8F0")
        txt.pack(fill="both", expand=True, padx=20, pady=20)

        def fetch():
            props = bo_session.get_server_properties(sid)
            self._safe_after(0, lambda: txt.insert("1.0", json.dumps(props, indent=4)))

        threading.Thread(target=fetch, daemon=True).start()

    # ── Performance popup (Live Matplotlib) ───────────────────────────────────

    def open_perf_dashboard(self, sid, sname):
        """
        Live Matplotlib window: CPU % + RAM % updated every 2 seconds.
        Also shows current values as large numerics at the top.
        """
        modal = ctk.CTkToplevel(self)
        modal.title(f"📊 Performance — {sname}")
        modal.geometry("860x620")
        modal.attributes("-topmost", True)
        modal.configure(fg_color="#0F172A")

        # ── Live value cards at top ────────────────────────────────────────
        cards = ctk.CTkFrame(modal, fg_color="#1E293B")
        cards.pack(fill="x", padx=20, pady=(16, 0))

        def _card(parent, label, init="—"):
            f = ctk.CTkFrame(parent, fg_color="#0F172A", width=160)
            f.pack(side="left", padx=8, pady=8)
            f.pack_propagate(False)
            ctk.CTkLabel(f, text=label, font=("Segoe UI", 11),
                         text_color="#94A3B8").pack(pady=(8, 0))
            v = ctk.CTkLabel(f, text=init, font=("Segoe UI", 26, "bold"),
                              text_color="#3B82F6")
            v.pack(pady=(0, 8))
            return v

        lbl_server = ctk.CTkLabel(cards, text=sname,
                                   font=("Segoe UI", 13, "bold"),
                                   text_color="#E2E8F0")
        lbl_server.pack(side="left", padx=16)

        val_cpu  = _card(cards, "CPU %")
        val_ram  = _card(cards, "RAM %")
        val_conn = _card(cards, "Connections")
        lbl_ts   = ctk.CTkLabel(cards, text="",
                                 font=("Segoe UI", 10), text_color="#475569")
        lbl_ts.pack(side="right", padx=16)

        # ── Matplotlib figure ─────────────────────────────────────────────
        fig, (ax_cpu, ax_ram) = plt.subplots(2, 1, figsize=(8, 5), dpi=100,
                                               sharex=True)
        fig.patch.set_facecolor('#0F172A')
        fig.subplots_adjust(hspace=0.35)

        for ax, title, color in [
            (ax_cpu, "CPU %",  "#3B82F6"),
            (ax_ram, "RAM %",  "#10B981"),
        ]:
            ax.set_facecolor('#1E293B')
            ax.set_title(title, color=color, fontsize=11, pad=4)
            ax.tick_params(colors='#94A3B8', labelsize=8)
            ax.spines[:].set_color('#334155')
            ax.grid(color='#334155', linestyle='--', linewidth=0.5)
            ax.set_ylim(-2, 105)
            ax.set_ylabel("%", color='#94A3B8', fontsize=8)

        canvas = FigureCanvasTkAgg(fig, master=modal)
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=20, pady=(8, 16))

        cpu_buf  = [0.0] * 60
        ram_buf  = [0.0] * 60
        conn_buf = [0]   * 60
        xs       = list(range(60))

        def live_loop():
            if not modal.winfo_exists():
                plt.close(fig)
                return

            try:
                m    = bo_session.get_server_metrics(sid)
                cpu  = float(m.get('cpu',  0) or 0)
                ram  = float(m.get('ram',  0) or 0)
                conn = int(m.get('connections', m.get('conn', 0)) or 0)
            except Exception:
                cpu, ram, conn = 0.0, 0.0, 0

            cpu_buf.pop(0);  cpu_buf.append(cpu)
            ram_buf.pop(0);  ram_buf.append(ram)
            conn_buf.pop(0); conn_buf.append(conn)

            # Update cards
            try:
                cpu_color  = _bar_color(cpu)
                ram_color  = _bar_color(ram)
                val_cpu.configure( text=f"{cpu:.1f}%",  text_color=cpu_color)
                val_ram.configure( text=f"{ram:.1f}%",  text_color=ram_color)
                val_conn.configure(text=str(conn),       text_color="#A78BFA")
                lbl_ts.configure(  text=datetime.now().strftime("%H:%M:%S"))
            except Exception:
                pass

            # Redraw charts
            try:
                ax_cpu.clear()
                ax_cpu.set_facecolor('#1E293B')
                ax_cpu.set_title("CPU %", color="#3B82F6", fontsize=11, pad=4)
                ax_cpu.tick_params(colors='#94A3B8', labelsize=8)
                ax_cpu.spines[:].set_color('#334155')
                ax_cpu.grid(color='#334155', linestyle='--', linewidth=0.5)
                ax_cpu.set_ylim(-2, 105)
                ax_cpu.fill_between(xs, cpu_buf, alpha=0.2, color='#3B82F6')
                ax_cpu.plot(xs, cpu_buf, color='#3B82F6', linewidth=2)
                ax_cpu.axhline(85, color='#EF4444', linestyle=':', linewidth=1, alpha=0.6)
                ax_cpu.axhline(60, color='#F59E0B', linestyle=':', linewidth=1, alpha=0.4)

                ax_ram.clear()
                ax_ram.set_facecolor('#1E293B')
                ax_ram.set_title("RAM %", color="#10B981", fontsize=11, pad=4)
                ax_ram.tick_params(colors='#94A3B8', labelsize=8)
                ax_ram.spines[:].set_color('#334155')
                ax_ram.grid(color='#334155', linestyle='--', linewidth=0.5)
                ax_ram.set_ylim(-2, 105)
                ax_ram.fill_between(xs, ram_buf, alpha=0.2, color='#10B981')
                ax_ram.plot(xs, ram_buf, color='#10B981', linewidth=2)
                ax_ram.axhline(85, color='#EF4444', linestyle=':', linewidth=1, alpha=0.6)

                canvas.draw()
            except Exception:
                pass

            modal.after(2000, live_loop)

        live_loop()