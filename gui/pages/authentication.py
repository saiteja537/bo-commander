import customtkinter as ctk
import threading
from tkinter import messagebox
from config import Config
from core.sapbo_connection import bo_session

class AuthenticationPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        
        # Header
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(top, text="🔐 Authentication Management", font=("Segoe UI", 24, "bold")).pack(side="left")
        
        # Tabs for different Auth Providers
        self.tabs = ctk.CTkTabview(self, fg_color=Config.COLORS['bg_secondary'])
        self.tabs.pack(fill="both", expand=True, padx=5, pady=5)
        self.tabs.add("Enterprise"); self.tabs.add("LDAP / AD"); self.tabs.add("SSO & Tokens")

        self._setup_enterprise()
        self._setup_ldap_ad()
        self._setup_sso_tokens()

    def _setup_enterprise(self):
        tab = self.tabs.tab("Enterprise")
        ctk.CTkLabel(tab, text="Native Enterprise Security", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=20, pady=10)
        
        # Policy Settings
        f = ctk.CTkFrame(tab, fg_color="transparent")
        f.pack(fill="x", padx=40)
        ctk.CTkSwitch(f, text="Force Password Change on First Login").pack(pady=5, anchor="w")
        ctk.CTkSwitch(f, text="Enable Account Lockout after 5 failed attempts").pack(pady=5, anchor="w")
        
        ctk.CTkLabel(tab, text="Minimum Password Length:").pack(anchor="w", padx=40, pady=(10,0))
        ctk.CTkEntry(tab, width=100, placeholder_text="8").pack(anchor="w", padx=40)

    def _setup_ldap_ad(self):
        tab = self.tabs.tab("LDAP / AD")
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(scroll, text="Active Directory / LDAP Configuration", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=10)
        
        # Form Fields
        fields = ["LDAP Host:", "Port:", "Base DN:", "Service Account:"]
        for field in fields:
            f = ctk.CTkFrame(scroll, fg_color="transparent")
            f.pack(fill="x", pady=5)
            ctk.CTkLabel(f, text=field, width=150, anchor="w").pack(side="left")
            ctk.CTkEntry(f, width=300).pack(side="left")

        ctk.CTkButton(scroll, text="Test Connection", fg_color=Config.COLORS['primary']).pack(pady=20)

    def _setup_sso_tokens(self):
        tab = self.tabs.tab("SSO & Tokens")
        ctk.CTkLabel(tab, text="Single Sign-On (SAML / Kerberos)", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=20, pady=10)
        
        # Token Info
        token_f = ctk.CTkFrame(tab, fg_color=Config.COLORS['bg_tertiary'])
        token_f.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(token_f, text="Current Active REST Tokens:", font=("Segoe UI", 12, "bold")).pack(pady=10)
        
        # Mock tokens
        for i in range(2):
            t = ctk.CTkFrame(token_f, height=30)
            t.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(t, text=f"Token_ID_{i}748...").pack(side="left", padx=10)
            ctk.CTkButton(t, text="Revoke", width=60, height=20, fg_color="red").pack(side="right", padx=10)