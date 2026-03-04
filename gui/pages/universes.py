import customtkinter as ctk
import threading
from tkinter import messagebox
from config import Config
from core.sapbo_connection import bo_session

class UniversesPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        
        # Header
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(0, 20))
        
        ctk.CTkLabel(
            top, text="Universes (UNX / UNV)", 
            font=Config.FONTS['sub_header']
        ).pack(side="left")
        
        # Actions
        actions = ctk.CTkFrame(top, fg_color="transparent")
        actions.pack(side="right")
        
        ctk.CTkButton(
            actions, text="🔄 Refresh", width=90,
            command=self.load_data
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            actions, text="📤 Publish New", width=110,
            fg_color=Config.COLORS['success']
        ).pack(side="left", padx=5)
        
        # Content
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=Config.COLORS['bg_secondary'])
        self.scroll.pack(fill="both", expand=True)
        
        self.load_data()
    
    def load_data(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        
        loading = ctk.CTkLabel(self.scroll, text="⏳ Loading universes...", text_color="gray")
        loading.pack(pady=40)
        
        threading.Thread(target=self._fetch, daemon=True).start()
    
    def _fetch(self):
        universes = bo_session.get_all_universes(limit=100)
        self.after(0, lambda: self._render(universes))
    
    def _render(self, universes):
        for w in self.scroll.winfo_children():
            w.destroy()
        
        if not universes:
            ctk.CTkLabel(
                self.scroll, 
                text="No Universes found in the repository.",
                text_color="gray",
                font=("Segoe UI", 13)
            ).pack(pady=40)
            return
        
        for univ in universes:
            row = ctk.CTkFrame(self.scroll, fg_color=Config.COLORS['bg_tertiary'], height=60)
            row.pack(fill="x", pady=2, padx=5)
            
            # Icon & Name
            icon = "🔮" if univ['type'] == 'UNV' else "💎" if univ['type'] == 'UNX' else "📊"
            
            ctk.CTkLabel(
                row, 
                text=f"{icon} {univ['name']}", 
                font=("Segoe UI", 13, "bold"),
                width=350, anchor="w"
            ).pack(side="left", padx=15)
            
            # Type Badge
            type_text = f"{univ['type']} Universe"
            ctk.CTkLabel(
                row, 
                text=type_text, 
                text_color=Config.COLORS['primary'],
                width=120
            ).pack(side="left")
            
            # Owner
            ctk.CTkLabel(
                row, 
                text=f"Owner: {univ['owner']}", 
                text_color="gray"
            ).pack(side="left", padx=10)
            
            # Actions
            ctk.CTkButton(
                row, text="📋 Details", width=80, height=26,
                command=lambda u=univ: self.show_details(u)
            ).pack(side="right", padx=5)
            
            ctk.CTkButton(
                row, text="🛡️ Security", width=80, height=26,
                fg_color=Config.COLORS['bg_secondary']
            ).pack(side="right", padx=5)
    
    def show_details(self, universe):
        """Show universe details"""
        details = bo_session.get_universe_details(universe['id'])
        
        modal = ctk.CTkToplevel(self)
        modal.title(f"Universe: {universe['name']}")
        modal.geometry("800x600")
        modal.attributes("-topmost", True)
        
        tabs = ctk.CTkTabview(modal)
        tabs.pack(fill="both", expand=True, padx=10, pady=10)
        
        tabs.add("Overview")
        tabs.add("Connections")
        tabs.add("Properties")
        
        # Overview
        info_frame = ctk.CTkFrame(tabs.tab("Overview"))
        info_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        info_items = [
            ("ID", universe['id']),
            ("Name", universe['name']),
            ("Type", universe['type']),
            ("Owner", universe['owner']),
            ("Created", universe['created']),
            ("Last Modified", universe['updated'])
        ]
        
        for label, value in info_items:
            row = ctk.CTkFrame(info_frame, fg_color=Config.COLORS['bg_secondary'])
            row.pack(fill="x", pady=5)
            
            ctk.CTkLabel(
                row, text=f"{label}:", 
                font=("Segoe UI", 12, "bold"),
                width=150, anchor="w"
            ).pack(side="left", padx=15, pady=10)
            
            ctk.CTkLabel(
                row, text=str(value),
                text_color="gray", anchor="w"
            ).pack(side="left", padx=15)
        
        # Connections
        ctk.CTkLabel(
            tabs.tab("Connections"),
            text="Connection information requires Universe SDK access.",
            text_color="gray"
        ).pack(pady=40)
        
        # Close
        ctk.CTkButton(
            modal, text="Close", width=120,
            command=modal.destroy
        ).pack(pady=15)