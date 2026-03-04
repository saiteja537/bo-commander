import customtkinter as ctk
import threading
import pandas as pd
from tkinter import filedialog, messagebox
from config import Config
from core.sapbo_connection import bo_session

class BulkOpsPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        
        ctk.CTkLabel(self, text="📊 Excel Data Hub", font=("Segoe UI", 24, "bold")).pack(anchor="w", pady=(0, 20))
        
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True)
        self.tabs.add("Import Data")
        self.tabs.add("Export Data")

        self._setup_import()
        self._setup_export()

    def _setup_import(self):
        tab = self.tabs.tab("Import Data")
        
        card = ctk.CTkFrame(tab, fg_color="#1E293B")
        card.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkLabel(card, text="Bulk Create / Update", font=("Segoe UI", 16, "bold")).pack(pady=10)
        
        self.action_var = ctk.StringVar(value="Create Users")
        ctk.CTkOptionMenu(card, values=["Create Users", "Update Passwords", "Assign Groups"], variable=self.action_var).pack(pady=5)
        
        ctk.CTkButton(card, text="📂 Select Excel File", height=40, command=self.run_import).pack(pady=20)
        
        ctk.CTkLabel(tab, text="Template Format: Username | Password | FullName | Email", text_color="gray").pack()
        
        self.log = ctk.CTkTextbox(tab, height=200, fg_color="#0F172A", text_color="#10B981")
        self.log.pack(fill="both", padx=20, pady=10)

    def _setup_export(self):
        tab = self.tabs.tab("Export Data")
        
        card = ctk.CTkFrame(tab, fg_color=Config.COLORS['bg_secondary'])
        card.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkLabel(card, text="System Audit Export", font=("Segoe UI", 16, "bold")).pack(pady=10)
        
        self.export_var = ctk.StringVar(value="All Users")
        ctk.CTkOptionMenu(card, values=["All Users", "All Reports", "Folder Structure", "Server List"], variable=self.export_var).pack(pady=5)
        
        ctk.CTkButton(card, text="💾 Generate Excel Report", height=40, fg_color=Config.COLORS['success'], command=self.run_export).pack(pady=20)

    def run_export(self):
        choice = self.export_var.get()
        self.log.insert("end", f"Starting export for {choice}...\n")
        
        threading.Thread(target=self._process_export, args=(choice,), daemon=True).start()

    def _process_export(self, choice):
        data = []
        if choice == "All Users":
            data = bo_session.get_users_detailed()
        elif choice == "All Reports":
            data = bo_session.get_all_reports()
        elif choice == "Server List":
            data = bo_session.get_all_servers()
        elif choice == "Folder Structure":
            # Uses the new recursive method
            data = bo_session.get_folder_structure_flat()

        if not data:
            self.after(0, lambda: messagebox.showwarning("Empty", "No data returned from CMS."))
            return

        # Save to file
        def save():
            path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
            if path:
                try:
                    df = pd.DataFrame(data)
                    df.to_excel(path, index=False)
                    messagebox.showinfo("Success", f"Exported {len(data)} rows to {path}")
                    self.log.insert("end", f"✅ Export Complete: {path}\n")
                except Exception as e:
                    messagebox.showerror("Error", str(e))
        
        self.after(0, save)

    def run_import(self):
        path = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx")])
        if path:
            self.log.insert("end", f"▶️ Parsing Excel File: {path}...\n")
            threading.Thread(target=self._process_import, args=(path,), daemon=True).start()

    def _process_import(self, path):
        try:
            df = pd.read_excel(path)
            mode = self.action_var.get()
            
            for _, row in df.iterrows():
                user = str(row.get('Username', ''))
                if not user: continue

                if mode == "Create Users":
                    success, msg = bo_session.create_user(user, str(row.get('Password','')), str(row.get('FullName','')), str(row.get('Email','')))
                    icon = "✅" if success else "❌"
                    self.after(0, lambda t=f"{icon} Created {user}: {msg}\n": self.log.insert("end", t))
            
            self.after(0, lambda: messagebox.showinfo("Done", "Bulk Operation Completed"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Import Failed: {e}"))