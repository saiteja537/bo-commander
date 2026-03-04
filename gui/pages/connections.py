import customtkinter as ctk
import threading
from tkinter import messagebox
from config import Config
from core.sapbo_connection import bo_session

class ConnectionsPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        
        # Header
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(0, 20))
        
        ctk.CTkLabel(
            top, text="Connection Management", 
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
            actions, text="➕ Create Connection", width=140,
            fg_color=Config.COLORS['success'],
            command=self.show_create_dialog
        ).pack(side="left", padx=5)
        
        # Content
        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True)
        
        self.load_data()
    
    def load_data(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        
        loading = ctk.CTkLabel(self.scroll, text="⏳ Loading connections...", text_color="gray")
        loading.pack(pady=40)
        
        threading.Thread(target=self._fetch, daemon=True).start()
    
    def _fetch(self):
        connections = bo_session.get_all_connections(limit=100)
        self.after(0, lambda: self._render(connections))
    
    def _render(self, connections):
        for w in self.scroll.winfo_children():
            w.destroy()
        
        if not connections:
            ctk.CTkLabel(
                self.scroll, 
                text="No connections found. Create a new connection to get started.",
                text_color="gray",
                font=("Segoe UI", 13)
            ).pack(pady=40)
            return
        
        for conn in connections:
            row = ctk.CTkFrame(self.scroll, fg_color=Config.COLORS['bg_secondary'], height=70)
            row.pack(fill="x", pady=2, padx=10)
            row.grid_columnconfigure(0, weight=1)
            
            # Main info frame
            info_frame = ctk.CTkFrame(row, fg_color="transparent")
            info_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=10)
            
            # Name
            ctk.CTkLabel(
                info_frame, 
                text=f"🔌 {conn['name']}", 
                font=("Segoe UI", 13, "bold")
            ).pack(anchor="w")
            
            # Details
            details = f"Server: {conn['server']} | Database: {conn['database']} | Owner: {conn['owner']}"
            ctk.CTkLabel(
                info_frame, 
                text=details, 
                text_color="gray",
                font=("Segoe UI", 10)
            ).pack(anchor="w", pady=(5, 0))
            
            # Actions
            actions_frame = ctk.CTkFrame(row, fg_color="transparent")
            actions_frame.grid(row=0, column=1, sticky="e", padx=15)
            
            ctk.CTkButton(
                actions_frame, text="✓ Test", width=70, height=26,
                fg_color=Config.COLORS['success'],
                command=lambda c=conn: self.test_connection(c)
            ).pack(side="left", padx=2)
            
            ctk.CTkButton(
                actions_frame, text="ℹ️ Details", width=80, height=26,
                command=lambda c=conn: self.show_details(c)
            ).pack(side="left", padx=2)
    
    def test_connection(self, conn):
        """Test database connection"""
        success = bo_session.test_connection(conn['id'])
        if success:
            messagebox.showinfo("Success", f"Connection '{conn['name']}' is working!")
        else:
            messagebox.showerror("Failed", f"Connection '{conn['name']}' test failed")
    
    def show_details(self, conn):
        """Show connection details"""
        modal = ctk.CTkToplevel(self)
        modal.title(f"Connection: {conn['name']}")
        modal.geometry("600x400")
        modal.attributes("-topmost", True)
        
        ctk.CTkLabel(
            modal, 
            text=f"🔌 {conn['name']}", 
            font=("Segoe UI", 18, "bold")
        ).pack(pady=20)
        
        details_frame = ctk.CTkFrame(modal, fg_color=Config.COLORS['bg_secondary'])
        details_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        info_items = [
            ("ID", conn['id']),
            ("Name", conn['name']),
            ("Type", conn['kind']),
            ("Server", conn['server']),
            ("Database", conn['database']),
            ("Owner", conn['owner']),
            ("Last Modified", conn['updated'])
        ]
        
        for label, value in info_items:
            row = ctk.CTkFrame(details_frame, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=5)
            
            ctk.CTkLabel(
                row, text=f"{label}:", 
                font=("Segoe UI", 11, "bold"),
                width=120, anchor="w"
            ).pack(side="left")
            
            ctk.CTkLabel(
                row, text=str(value),
                text_color="gray"
            ).pack(side="left", padx=10)
        
        ctk.CTkButton(
            modal, text="Close", width=120,
            command=modal.destroy
        ).pack(pady=15)
    
    def show_create_dialog(self):
        """Show create connection dialog"""
        messagebox.showinfo(
            "Create Connection", 
            "Connection creation via GUI requires SDK integration.\nUse CMC or IDT to create connections for now."
        )