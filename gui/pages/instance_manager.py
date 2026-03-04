import customtkinter as ctk
import threading
from tkinter import messagebox
from config import Config
from core.sapbo_connection import bo_session

class InstanceManagerPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        
        # Header
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(0, 20))
        
        ctk.CTkLabel(
            top, text="Instance Manager", 
            font=Config.FONTS['sub_header']
        ).pack(side="left")
        
        # Actions
        actions = ctk.CTkFrame(top, fg_color="transparent")
        actions.pack(side="right")
        
        ctk.CTkButton(
            actions, text="🗑️ Purge Old", width=100,
            fg_color=Config.COLORS['danger'],
            command=self.purge_old_instances
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            actions, text="📅 Reschedule Failed", width=140,
            fg_color=Config.COLORS['warning'],
            command=self.reschedule_failed
        ).pack(side="left", padx=5)
        
        # Filter Tabs
        self.tab_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.tab_frame.pack(fill="x", pady=(0, 10))
        
        self.filter_buttons = {}
        filters = ["All", "Success", "Failed", "Running"]
        for i, filt in enumerate(filters):
            btn = ctk.CTkButton(
                self.tab_frame, text=filt, width=120,
                fg_color=Config.COLORS['bg_tertiary'] if i != 0 else Config.COLORS['primary'],
                command=lambda f=filt: self.apply_filter(f)
            )
            btn.pack(side="left", padx=2)
            self.filter_buttons[filt] = btn
        
        # Content
        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True)
        
        self.current_filter = "All"
        self.load_data()
    
    def apply_filter(self, filter_name):
        """Apply status filter"""
        self.current_filter = filter_name
        
        # Update button colors
        for name, btn in self.filter_buttons.items():
            if name == filter_name:
                btn.configure(fg_color=Config.COLORS['primary'])
            else:
                btn.configure(fg_color=Config.COLORS['bg_tertiary'])
        
        self.load_data()
    
    def load_data(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        
        loading = ctk.CTkLabel(self.scroll, text="⏳ Loading instances...", text_color="gray")
        loading.pack(pady=40)
        
        threading.Thread(target=self._fetch, daemon=True).start()
    
    def _fetch(self):
        # Convert filter to status parameter
        status = None if self.current_filter == "All" else self.current_filter.lower()
        
        instances = bo_session.get_instances(status=status, limit=200)
        self.after(0, lambda: self._render(instances))
    
    def _render(self, instances):
        for w in self.scroll.winfo_children():
            w.destroy()
        
        if not instances:
            ctk.CTkLabel(
                self.scroll, 
                text="No instances found for this filter.",
                text_color="gray",
                font=("Segoe UI", 13)
            ).pack(pady=40)
            return
        
        for inst in instances:
            self._create_instance_row(inst)
    
    def _create_instance_row(self, instance):
        """Create instance row"""
        row = ctk.CTkFrame(self.scroll, fg_color=Config.COLORS['bg_secondary'], height=70)
        row.pack(fill="x", pady=2, padx=10)
        
        # Status Badge
        status_colors = {
            'Success': Config.COLORS['success'],
            'Failed': Config.COLORS['danger'],
            'Running': Config.COLORS['warning'],
            'Pending': Config.COLORS['primary']
        }
        
        status_color = status_colors.get(instance['status'], 'gray')
        
        status_badge = ctk.CTkLabel(
            row, 
            text=f"● {instance['status']}", 
            text_color=status_color,
            font=("Segoe UI", 11, "bold"),
            width=80
        )
        status_badge.pack(side="left", padx=15, pady=10)
        
        # Instance Info
        info_frame = ctk.CTkFrame(row, fg_color="transparent")
        info_frame.pack(side="left", fill="x", expand=True, padx=10)
        
        # Name
        ctk.CTkLabel(
            info_frame, 
            text=f"📄 {instance['name']}", 
            font=("Segoe UI", 12, "bold"),
            anchor="w"
        ).pack(anchor="w")
        
        # Details
        details = f"Started: {instance['start_time']} | Duration: {instance.get('duration', 0)}s | Owner: {instance['owner']}"
        ctk.CTkLabel(
            info_frame, 
            text=details, 
            text_color="gray",
            font=("Segoe UI", 9),
            anchor="w"
        ).pack(anchor="w", pady=(3, 0))
        
        # Actions
        if instance['status'] != 'Running':
            ctk.CTkButton(
                row, text="🗑️ Delete", width=70, height=26,
                fg_color=Config.COLORS['danger'],
                command=lambda i=instance: self.delete_instance(i)
            ).pack(side="right", padx=5)
    
    def delete_instance(self, instance):
        """Delete an instance"""
        if messagebox.askyesno("Confirm Delete", f"Delete instance '{instance['name']}'?"):
            success, msg = bo_session.delete_instance(instance['id'])
            if success:
                messagebox.showinfo("Success", "Instance deleted")
                self.load_data()
            else:
                messagebox.showerror("Error", f"Delete failed: {msg}")
    
    def purge_old_instances(self):
        """Purge instances older than 30 days"""
        if messagebox.askyesno(
            "Confirm Purge", 
            "Delete all instances older than 30 days?\nThis cannot be undone!"
        ):
            count, msg = bo_session.purge_old_instances(days=30)
            messagebox.showinfo("Purge Complete", f"Deleted {count} old instances")
            self.load_data()
    
    def reschedule_failed(self):
        """Reschedule all failed instances"""
        if messagebox.askyesno("Confirm Reschedule", "Reschedule all failed instances?"):
            count, msg = bo_session.reschedule_failed_instances()
            messagebox.showinfo("Reschedule Complete", msg)
            self.load_data()
