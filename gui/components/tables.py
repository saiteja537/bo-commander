import customtkinter as ctk
from config import Config

class Table(ctk.CTkScrollableFrame):
    def __init__(self, parent, columns, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.columns = columns # List of dicts: {'name': 'Name', 'width': 100}
        self.rows = []
        
        # Header Frame
        self.header = ctk.CTkFrame(self, height=40, fg_color=Config.COLORS['bg_tertiary'])
        self.header.pack(fill="x", pady=(0, 5))
        
        # Create Header Columns
        for i, col in enumerate(columns):
            lbl = ctk.CTkLabel(
                self.header, 
                text=col['name'], 
                font=("Segoe UI", 12, "bold"),
                anchor="w"
            )
            # Simple grid system simulation using pack with explicit widths? 
            # Better to use grid for alignment
            self.header.grid_columnconfigure(i, weight=1)
            lbl.grid(row=0, column=i, padx=10, pady=8, sticky="ew")

    def add_row(self, values, row_id, actions=None):
        """
        values: list of strings matching columns
        actions: list of (icon_text, callback_func)
        """
        row_frame = ctk.CTkFrame(self, height=40, fg_color=Config.COLORS['bg_secondary'])
        row_frame.pack(fill="x", pady=2)
        
        for i, val in enumerate(values):
            row_frame.grid_columnconfigure(i, weight=1)
            lbl = ctk.CTkLabel(
                row_frame, 
                text=str(val), 
                anchor="w",
                font=Config.FONTS['small']
            )
            lbl.grid(row=0, column=i, padx=10, pady=8, sticky="ew")
            
        # Actions Column (if exists)
        if actions:
            action_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
            col_idx = len(self.columns)
            row_frame.grid_columnconfigure(col_idx, weight=0)
            action_frame.grid(row=0, column=col_idx, padx=10, sticky="e")
            
            for icon, callback in actions:
                btn = ctk.CTkButton(
                    action_frame, 
                    text=icon, 
                    width=30, 
                    height=30,
                    fg_color="transparent",
                    hover_color=Config.COLORS['bg_tertiary'],
                    command=lambda i=row_id: callback(i)
                )
                btn.pack(side="left", padx=2)

    def clear(self):
        # Destroy all rows except header
        for widget in self.winfo_children():
            if widget != self.header:
                widget.destroy()