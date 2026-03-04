import customtkinter as ctk
import threading
from config import Config
from gui.components.cards import StatCard
from core.sapbo_connection import bo_session

class DashboardPage(ctk.CTkFrame):
    """
    THE CENTRAL COMMAND DASHBOARD
    - Real-time counts for Users, Servers, and Reports.
    - Live Server Health Grid.
    - Automatic Refresh every 30 seconds.
    """
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        
        # Main container scrollable to handle different screen sizes
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True)
        
        # Start the heartbeat
        self.run_auto_refresh()

    def run_auto_refresh(self):
        """Refreshes data and schedules the next refresh in 30 seconds."""
        self.refresh_ui()
        # 30,000 milliseconds = 30 seconds
        self.after(30000, self.run_auto_refresh)

    def refresh_ui(self):
        """Clears the dashboard and shows the loading state."""
        for widget in self.scroll.winfo_children():
            widget.destroy()
            
        self.loader = ctk.CTkLabel(
            self.scroll, 
            text="🔄 Syncing Real-Time Stats with SAP BO...", 
            font=Config.FONTS['sub_header'],
            text_color=Config.COLORS['text_secondary']
        )
        self.loader.pack(pady=50)
        
        # Start background data fetch
        threading.Thread(target=self._fetch_stats, daemon=True).start()

    def _fetch_stats(self):
        """Background thread logic to query the Master Connection Engine."""
        try:
            stats = bo_session.get_dashboard_stats()
            self.after(0, lambda: self._render_dashboard(stats))
        except Exception as e:
            print(f"Dashboard Fetch Error: {e}")
            self.after(0, lambda: self.loader.configure(text=f"❌ Sync Error: {e}"))

    def _render_dashboard(self, stats):
        """Draws the final UI elements once data is received."""
        if hasattr(self, 'loader'):
            self.loader.destroy()
        
        # --- ROW 1: STATISTIC CARDS ---
        row1 = ctk.CTkFrame(self.scroll, fg_color="transparent")
        row1.pack(fill="x", pady=10)
        row1.grid_columnconfigure((0,1,2,3), weight=1)

        # 1. Total Users
        StatCard(row1, "Total Users", str(stats.get('users', 0)), 
                 "Registered in CMS", "👤", "primary").grid(row=0, column=0, padx=5, sticky="ew")
        
        # 2. Server Uptime
        StatCard(row1, "Servers", f"{stats.get('servers_running', 0)}/{stats.get('servers_total', 0)}", 
                 "Active / Total", "🖥️", "success").grid(row=0, column=1, padx=5, sticky="ew")
        
        # 3. Reports Count
        StatCard(row1, "Reports", str(stats.get('reports', 0)), 
                 "WebI & Crystal", "📊", "secondary").grid(row=0, column=2, padx=5, sticky="ew")
        
        # 4. System Status
        StatCard(row1, "API Status", "Healthy", 
                 "REST Port 6405", "⚡", "accent").grid(row=0, column=3, padx=5, sticky="ew")

        # --- ROW 2: LIVE SERVER HEALTH GRID ---
        ctk.CTkLabel(
            self.scroll, 
            text="Live Server Health Monitor", 
            font=Config.FONTS['sub_header'],
            text_color=Config.COLORS['text_primary']
        ).pack(anchor="w", pady=(25, 15), padx=5)

        grid = ctk.CTkFrame(self.scroll, fg_color="transparent")
        grid.pack(fill="x", padx=5)
        grid.grid_columnconfigure((0,1,2), weight=1)

        server_list = stats.get('server_list', [])
        if not server_list:
            ctk.CTkLabel(grid, text="No server data available from CMS.", text_color="gray").pack(pady=20)
            return

        for i, srv in enumerate(server_list):
            r, c = divmod(i, 3)
            
            # Individual Server Status Card
            card = ctk.CTkFrame(grid, fg_color=Config.COLORS['bg_secondary'], corner_radius=10)
            card.grid(row=r, column=c, padx=5, pady=5, sticky="nsew")
            
            # Status Indicator Color
            dot_color = Config.COLORS['success'] if srv['status'] == "Running" else Config.COLORS['danger']
            
            # Server Name (Truncated if too long)
            display_name = (srv['name'][:25] + '..') if len(srv['name']) > 25 else srv['name']
            
            ctk.CTkLabel(
                card, 
                text=display_name, 
                font=("Segoe UI", 12, "bold"),
                text_color=Config.COLORS['text_primary']
            ).pack(side="left", padx=15, pady=15)
            
            ctk.CTkLabel(
                card, 
                text=f"● {srv['status']}", 
                text_color=dot_color,
                font=("Segoe UI", 11, "bold")
            ).pack(side="right", padx=15)