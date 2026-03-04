import customtkinter as ctk
from config import Config

class StatCard(ctk.CTkFrame):
    def __init__(self, parent, title, value, subtext, icon="📊", color="primary"):
        """
        A beautiful dashboard statistic card.
        color: 'primary', 'secondary', 'accent', 'warning', 'danger'
        """
        # Determine color hex
        card_color = Config.COLORS.get(color, Config.COLORS['primary'])
        
        super().__init__(parent, fg_color=Config.COLORS['bg_secondary'], corner_radius=10)
        
        # Grid Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Left Accent Border (Colored Strip)
        self.accent = ctk.CTkFrame(self, width=5, fg_color=card_color, corner_radius=5)
        self.accent.pack(side="left", fill="y", padx=(0, 15))

        # Content Frame
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        # Title (Top)
        self.lbl_title = ctk.CTkLabel(
            self.content, 
            text=title.upper(), 
            font=Config.FONTS['small'],
            text_color=Config.COLORS['text_secondary'],
            anchor="w"
        )
        self.lbl_title.pack(fill="x")

        # Value (Middle)
        self.lbl_value = ctk.CTkLabel(
            self.content, 
            text=str(value), 
            font=("Segoe UI", 28, "bold"),
            text_color=Config.COLORS['text_primary'],
            anchor="w"
        )
        self.lbl_value.pack(fill="x", pady=0)

        # Subtext (Bottom)
        self.lbl_sub = ctk.CTkLabel(
            self.content, 
            text=subtext, 
            font=Config.FONTS['small'],
            text_color=Config.COLORS['text_secondary'],
            anchor="w"
        )
        self.lbl_sub.pack(fill="x")

        # Icon (Right Side)
        self.icon_lbl = ctk.CTkLabel(
            self, 
            text=icon, 
            font=("Segoe UI Emoji", 30), # Use Emoji font for icons
            text_color=Config.COLORS['text_secondary']
        )
        self.icon_lbl.pack(side="right", padx=20)