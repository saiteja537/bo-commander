import customtkinter as ctk
from tkinter import messagebox
from config import Config
from core.sapbo_connection import bo_session

class SchedulingPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        
        self.tabs = ctk.CTkTabview(self, fg_color=Config.COLORS['bg_secondary'])
        self.tabs.pack(fill="both", expand=True, padx=10, pady=10)
        self.tabs.add("Schedule New")
        self.tabs.add("Active Schedules")
        self.tabs.add("Instance History")

        self._setup_new_schedule()
        self._setup_active_schedules()
        self._setup_history()

    def _setup_new_schedule(self):
        tab = self.tabs.tab("Schedule New")
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # 1. Target
        ctk.CTkLabel(scroll, text="1. Select Report", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(10,5))
        f1 = ctk.CTkFrame(scroll, fg_color=Config.COLORS['bg_tertiary'])
        f1.pack(fill="x", pady=5)
        self.rep_id = ctk.CTkEntry(f1, placeholder_text="Report ID (e.g. 1234)", width=200)
        self.rep_id.pack(side="left", padx=10, pady=10)
        ctk.CTkButton(f1, text="Browse...", width=80).pack(side="left")

        # 2. Recurrence (Visual)
        ctk.CTkLabel(scroll, text="2. When to Run?", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(20,5))
        f2 = ctk.CTkFrame(scroll, fg_color=Config.COLORS['bg_tertiary'])
        f2.pack(fill="x", pady=5)
        
        self.freq = ctk.StringVar(value="Once")
        ctk.CTkSegmentedButton(f2, values=["Run Now", "Daily", "Weekly", "Monthly"], variable=self.freq).pack(fill="x", padx=10, pady=10)
        
        # Time Picker UI
        time_f = ctk.CTkFrame(f2, fg_color="transparent")
        time_f.pack(pady=5)
        ctk.CTkLabel(time_f, text="Start At:").pack(side="left")
        ctk.CTkComboBox(time_f, values=[f"{i:02d}" for i in range(24)], width=60).pack(side="left", padx=5) # Hour
        ctk.CTkLabel(time_f, text=":").pack(side="left")
        ctk.CTkComboBox(time_f, values=[f"{i:02d}" for i in range(0, 60, 5)], width=60).pack(side="left", padx=5) # Min

        # 3. Format & Dest
        ctk.CTkLabel(scroll, text="3. Format & Destination", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(20,5))
        f3 = ctk.CTkFrame(scroll, fg_color=Config.COLORS['bg_tertiary'])
        f3.pack(fill="x", pady=5)
        
        ctk.CTkCheckBox(f3, text="Excel").pack(side="left", padx=20, pady=15)
        ctk.CTkCheckBox(f3, text="PDF").pack(side="left", padx=20, pady=15)
        
        ctk.CTkSwitch(f3, text="Email to Users").pack(side="right", padx=20)

        # Submit
        ctk.CTkButton(scroll, text="📅 Schedule Job", height=40, fg_color=Config.COLORS['success'], command=self.submit_job).pack(fill="x", pady=30)

    def _setup_active_schedules(self):
        tab = self.tabs.tab("Active Schedules")
        # Visual Calendar Placeholder
        cal_frame = ctk.CTkFrame(tab, fg_color=Config.COLORS['bg_tertiary'], height=300)
        cal_frame.pack(fill="x", pady=10)
        ctk.CTkLabel(cal_frame, text="📅 Recurring Schedules (Visual Calendar View)", font=("Segoe UI", 16)).pack(expand=True)
        
        # Mock List
        for i in range(1, 4):
            row = ctk.CTkFrame(tab)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=f"Daily Sales Report {i}", font=("Segoe UI", 12, "bold")).pack(side="left", padx=10)
            ctk.CTkLabel(row, text="Every Mon, 8:00 AM", text_color="gray").pack(side="left")
            ctk.CTkButton(row, text="Pause", width=60, fg_color="#F59E0B").pack(side="right", padx=5)

    def _setup_history(self):
        tab = self.tabs.tab("Instance History")
        ctk.CTkButton(tab, text="🔄 Refresh", width=100, command=lambda: self.load_instances(tab)).pack(anchor="e", pady=5)
        self.inst_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self.inst_scroll.pack(fill="both", expand=True)

    def load_instances(self, parent):
        for w in self.inst_scroll.winfo_children(): w.destroy()
        # Mock Data for UI demo (Real data connects to bo_session.run_cms_query)
        mock_data = [
            {"name": "Finance Q1", "status": "Success", "time": "2024-02-14 09:00"},
            {"name": "HR Audit", "status": "Failed", "time": "2024-02-14 08:30"},
        ]
        for item in mock_data:
            row = ctk.CTkFrame(self.inst_scroll)
            row.pack(fill="x", pady=2)
            col = Config.COLORS['success'] if item['status']=="Success" else Config.COLORS['danger']
            ctk.CTkLabel(row, text=f"● {item['status']}", text_color=col).pack(side="left", padx=10)
            ctk.CTkLabel(row, text=item['name']).pack(side="left", padx=10)
            ctk.CTkLabel(row, text=item['time'], text_color="gray").pack(side="right", padx=10)

    def submit_job(self):
        if not self.rep_id.get():
            messagebox.showerror("Error", "Please enter a Report ID")
            return
        messagebox.showinfo("Success", f"Job scheduled: {self.freq.get()}")