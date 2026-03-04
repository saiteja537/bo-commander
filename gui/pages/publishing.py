import customtkinter as ctk
from config import Config

class PublishingPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(top, text="Publishing & Data Bursting", font=("Segoe UI", 24, "bold")).pack(side="left")
        ctk.CTkButton(top, text="➕ Create Publication", fg_color=Config.COLORS['success']).pack(side="right")

        self.tabs = ctk.CTkTabview(self, fg_color=Config.COLORS['bg_secondary'])
        self.tabs.pack(fill="both", expand=True)
        self.tabs.add("Active Publications")
        self.tabs.add("Personalization Profiles")
        
        self.pub_scroll = ctk.CTkScrollableFrame(self.tabs.tab("Active Publications"), fg_color="transparent")
        self.pub_scroll.pack(fill="both", expand=True)
        
        self.render_publications()

    def render_publications(self):
        # Mocking active publications
        pubs = [
            {"name": "Regional_Sales_Burst", "docs": "3 WebI", "recipients": "1,200", "status": "Ready"},
            {"name": "HR_Payroll_Distribution", "docs": "1 Crystal", "recipients": "450", "status": "Running"},
            {"name": "Daily_Inventory_Merge", "docs": "5 WebI", "recipients": "50", "status": "Failed"}
        ]
        
        for p in pubs:
            row = ctk.CTkFrame(self.pub_scroll, fg_color=Config.COLORS['bg_tertiary'], height=70)
            row.pack(fill="x", pady=2, padx=5)
            
            ctk.CTkLabel(row, text=f"📬 {p['name']}", font=("Segoe UI", 12, "bold"), width=250, anchor="w").pack(side="left", padx=15)
            
            details = f"Content: {p['docs']} | Recips: {p['recipients']}"
            ctk.CTkLabel(row, text=details, text_color="gray").pack(side="left", padx=20)
            
            # Actions
            act = ctk.CTkFrame(row, fg_color="transparent")
            act.pack(side="right", padx=10)
            ctk.CTkButton(act, text="Run Now", width=80, height=24, fg_color=Config.COLORS['primary']).pack(side="left", padx=2)
            ctk.CTkButton(act, text="Edit Profiles", width=100, height=24, fg_color=Config.COLORS['bg_secondary']).pack(side="left", padx=2)