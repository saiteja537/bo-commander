import customtkinter as ctk
import threading
from config import Config
from core.sapbo_connection import bo_session

class SettingsPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        
        # Title
        ctk.CTkLabel(
            self, text="Global Platform Settings", 
            font=Config.FONTS['sub_header']
        ).pack(pady=(0, 20))
        
        # Tabs
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True)
        
        self.tabview.add("Auditing")
        self.tabview.add("Monitoring")
        self.tabview.add("Cluster Info")
        
        # Auditing Tab
        self._setup_auditing_tab()
        
        # Monitoring Tab
        self._setup_monitoring_tab()
        
        # Cluster Info Tab
        self._setup_cluster_tab()
    
    def _setup_auditing_tab(self):
        """Setup auditing configuration"""
        frame = self.tabview.tab("Auditing")
        
        ctk.CTkLabel(
            frame, 
            text="📊 Audit Configuration",
            font=("Segoe UI", 16, "bold")
        ).pack(pady=20)
        
        ctk.CTkLabel(
            frame, 
            text="Auditing settings require administrator access to modify.",
            text_color="gray"
        ).pack(pady=10)
        
        # Audit Status
        status_frame = ctk.CTkFrame(frame, fg_color=Config.COLORS['bg_secondary'])
        status_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(
            status_frame, 
            text="✓ Auditing Enabled", 
            text_color=Config.COLORS['success'],
            font=("Segoe UI", 12, "bold")
        ).pack(pady=15)
    
    def _setup_monitoring_tab(self):
        """Setup monitoring tab with server metrics"""
        frame = self.tabview.tab("Monitoring")
        
        # Header
        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(10, 20))
        
        ctk.CTkLabel(
            header_frame, 
            text="📈 Server Monitoring",
            font=("Segoe UI", 16, "bold")
        ).pack(side="left", padx=20)
        
        ctk.CTkButton(
            header_frame, text="🔄 Refresh", width=90,
            command=lambda: self.load_monitoring_data(frame)
        ).pack(side="right", padx=20)
        
        # Content frame
        self.monitoring_content = ctk.CTkScrollableFrame(frame)
        self.monitoring_content.pack(fill="both", expand=True, padx=10)
        
        # Load initial data
        self.load_monitoring_data(frame)
    
    def load_monitoring_data(self, parent_frame):
        """Load server monitoring metrics"""
        for w in self.monitoring_content.winfo_children():
            w.destroy()
        
        loading = ctk.CTkLabel(
            self.monitoring_content, 
            text="⏳ Loading metrics...", 
            text_color="gray"
        )
        loading.pack(pady=40)
        
        threading.Thread(
            target=self._fetch_monitoring_data, 
            daemon=True
        ).start()
    
    def _fetch_monitoring_data(self):
        """Fetch monitoring metrics from BO"""
        # Get server list and their status
        servers = bo_session.get_all_servers()
        metrics = bo_session.get_server_metrics()
        stats = bo_session.get_dashboard_stats()
        
        self.after(0, lambda: self._render_monitoring_data(servers, metrics, stats))
    
    def _render_monitoring_data(self, servers, metrics, stats):
        """Render monitoring data"""
        for w in self.monitoring_content.winfo_children():
            w.destroy()
        
        if not servers and not stats:
            ctk.CTkLabel(
                self.monitoring_content, 
                text="No monitoring data available.",
                text_color="gray"
            ).pack(pady=40)
            return
        
        # Summary Cards
        summary_frame = ctk.CTkFrame(self.monitoring_content, fg_color="transparent")
        summary_frame.pack(fill="x", padx=10, pady=10)
        summary_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
        
        # Card 1: Total Servers
        self._create_metric_card(
            summary_frame, 
            "Total Servers", 
            stats.get('servers_total', 0), 
            "🖥️", 
            Config.COLORS['primary']
        ).grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        
        # Card 2: Running Servers
        self._create_metric_card(
            summary_frame, 
            "Running", 
            stats.get('servers_running', 0), 
            "✓", 
            Config.COLORS['success']
        ).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # Card 3: Total Users
        self._create_metric_card(
            summary_frame, 
            "Users", 
            stats.get('users', 0), 
            "👥", 
            Config.COLORS['accent']
        ).grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        
        # Card 4: Reports
        self._create_metric_card(
            summary_frame, 
            "Reports", 
            stats.get('reports', 0), 
            "📊", 
            Config.COLORS['secondary']
        ).grid(row=0, column=3, padx=5, pady=5, sticky="ew")
        
        # Server List
        if servers:
            ctk.CTkLabel(
                self.monitoring_content, 
                text="Server Status",
                font=("Segoe UI", 14, "bold")
            ).pack(anchor="w", padx=20, pady=(20, 10))
            
            for server in servers:
                self._create_server_row(server)
    
    def _create_metric_card(self, parent, title, value, icon, color):
        """Create a metric card"""
        card = ctk.CTkFrame(parent, fg_color=Config.COLORS['bg_secondary'], height=100)
        
        ctk.CTkLabel(
            card, 
            text=icon, 
            font=("Segoe UI", 24)
        ).pack(pady=(15, 5))
        
        ctk.CTkLabel(
            card, 
            text=str(value), 
            font=("Segoe UI", 20, "bold"),
            text_color=color
        ).pack()
        
        ctk.CTkLabel(
            card, 
            text=title, 
            font=("Segoe UI", 10),
            text_color="gray"
        ).pack(pady=(0, 15))
        
        return card
    
    def _create_server_row(self, server):
        """Create a server status row"""
        row = ctk.CTkFrame(self.monitoring_content, fg_color=Config.COLORS['bg_secondary'])
        row.pack(fill="x", padx=20, pady=2)
        
        # Status indicator
        status_color = Config.COLORS['success'] if server['alive'] else Config.COLORS['danger']
        status_text = "● Running" if server['alive'] else "● Stopped"
        
        ctk.CTkLabel(
            row, 
            text=status_text, 
            text_color=status_color,
            font=("Segoe UI", 11, "bold"),
            width=100
        ).pack(side="left", padx=15, pady=10)
        
        # Server name
        ctk.CTkLabel(
            row, 
            text=f"🖥️ {server['name']}", 
            font=("Segoe UI", 12, "bold"),
            anchor="w"
        ).pack(side="left", padx=10)
        
        # Failures (if any)
        if server['failures'] > 0:
            ctk.CTkLabel(
                row, 
                text=f"⚠️ {server['failures']} failures", 
                text_color=Config.COLORS['warning'],
                font=("Segoe UI", 10)
            ).pack(side="right", padx=15)
    
    def _setup_cluster_tab(self):
        """Setup cluster information tab"""
        frame = self.tabview.tab("Cluster Info")
        
        ctk.CTkLabel(
            frame, 
            text="🌐 Cluster Configuration",
            font=("Segoe UI", 16, "bold")
        ).pack(pady=20)
        
        ctk.CTkLabel(
            frame, 
            text="Cluster information requires administrator access.",
            text_color="gray"
        ).pack(pady=10)
        
        # CMS Info
        cms_frame = ctk.CTkFrame(frame, fg_color=Config.COLORS['bg_secondary'])
        cms_frame.pack(fill="x", padx=20, pady=10)
        
        cms_info = bo_session.cms_details
        
        info_items = [
            ("CMS Host", cms_info.get('host', 'Unknown')),
            ("Port", cms_info.get('port', '6405')),
            ("Connected User", cms_info.get('user', 'Unknown'))
        ]
        
        for label, value in info_items:
            row = ctk.CTkFrame(cms_frame, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=5)
            
            ctk.CTkLabel(
                row, text=f"{label}:", 
                font=("Segoe UI", 11, "bold"),
                width=150, anchor="w"
            ).pack(side="left")
            
            ctk.CTkLabel(
                row, text=str(value),
                text_color="gray"
            ).pack(side="left", padx=10)
