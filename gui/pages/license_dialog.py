"""
gui/pages/license_dialog.py
──────────────────────────────────────────────────────────────────────────────
License activation / renewal dialog.
Shown automatically when:
  • First launch (never activated)
  • License expired after 30 days

After .wait_window(), check .activated (bool) and .user_name (str).
Closing the window without activating calls sys.exit(0).
──────────────────────────────────────────────────────────────────────────────
"""
import customtkinter as ctk
from core.license_manager import (
    activate, is_renewal, days_remaining,
    DEVELOPER_EMAIL, DEVELOPER_LINKEDIN, LICENSE_DAYS
)

# Colour palette matching the app dark theme
C_BG    = "#080e17"
C_BG2   = "#0d1824"
C_BG3   = "#112030"
C_BORD  = "#1a2e42"
C_BORD2 = "#1e3a52"
C_CYN   = "#22d3ee"
C_RED   = "#ef4444"
C_AMB   = "#f59e0b"
C_GRN   = "#22c55e"
C_GRY   = "#8fafc8"
C_GRY2  = "#4a6b80"
C_WHT   = "#e2eaf4"


class LicenseDialog(ctk.CTkToplevel):
    """
    Modal activation / renewal dialog.
    Usage:
        dlg = LicenseDialog(root)
        root.wait_window(dlg)
        if dlg.activated: ...
    """

    def __init__(self, parent):
        super().__init__(parent)

        self.activated = False
        self.user_name = ""
        self._renewal  = is_renewal()

        self.title("BO Commander — License" + (" Renewal" if self._renewal else " Activation"))
        self.geometry("540x660")
        self.resizable(False, False)
        self.configure(fg_color=C_BG)
        self.grab_set()
        self.lift()
        self.focus_force()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build()
        self._centre()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        PAD = {"padx": 44}

        # ── Top accent bar ────────────────────────────────────────────────────
        bar = ctk.CTkFrame(self, height=4, corner_radius=0,
                           fg_color=C_CYN)
        bar.pack(fill="x")

        # ── App name ──────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="BO Commander",
                     font=("Courier New", 30, "bold"),
                     text_color=C_CYN).pack(pady=(34, 3))
        ctk.CTkLabel(self, text="v1.0.0  ·  Intelligent SAP BO Control Center",
                     font=("Segoe UI", 11), text_color=C_GRY).pack()

        # ── Divider ───────────────────────────────────────────────────────────
        ctk.CTkFrame(self, height=1, fg_color=C_BORD).pack(
            fill="x", padx=44, pady=22)

        # ── Expired banner (only on renewal) ─────────────────────────────────
        if self._renewal:
            exp_box = ctk.CTkFrame(self, fg_color="#1a0e00",
                                   border_color="#78350f", border_width=1,
                                   corner_radius=8)
            exp_box.pack(fill="x", **PAD, pady=(0, 14))
            ctk.CTkLabel(exp_box,
                         text="⏰  Your 30-day license has expired",
                         font=("Segoe UI", 12, "bold"),
                         text_color=C_AMB).pack(anchor="w", padx=14, pady=(10, 2))
            ctk.CTkLabel(exp_box,
                         text=(
                             "License keys expire every 30 days.\n"
                             "Contact the developer for a renewal key — it's free and fast."
                         ),
                         font=("Segoe UI", 11), text_color="#d97706",
                         justify="left", wraplength=420).pack(
                anchor="w", padx=14, pady=(0, 10))

        # ── Section title ─────────────────────────────────────────────────────
        title_txt = "Renew Your License" if self._renewal else "License Activation Required"
        ctk.CTkLabel(self, text=title_txt,
                     font=("Segoe UI", 16, "bold"),
                     text_color=C_WHT).pack(**PAD, anchor="w")
        ctk.CTkLabel(self,
                     text=(
                         "Enter a new key to reset your 30-day license."
                         if self._renewal else
                         "Enter your license key to unlock BO Commander."
                     ),
                     font=("Segoe UI", 12), text_color=C_GRY,
                     justify="left").pack(**PAD, anchor="w", pady=(5, 0))

        # ── Name field ────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Your Name",
                     font=("Segoe UI", 12), text_color=C_GRY).pack(
            **PAD, anchor="w", pady=(18, 0))
        self._name_entry = ctk.CTkEntry(
            self, height=42,
            placeholder_text="e.g. John Smith",
            font=("Segoe UI", 13),
            fg_color=C_BG2, border_color=C_BORD, text_color=C_WHT)
        self._name_entry.pack(fill="x", **PAD, pady=(4, 0))

        # ── Key field ─────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="License Key",
                     font=("Segoe UI", 12), text_color=C_GRY).pack(
            **PAD, anchor="w", pady=(12, 0))
        self._key_entry = ctk.CTkEntry(
            self, height=42,
            placeholder_text="BOCMD-XXXX-XXXX-XXXXX",
            font=("Courier New", 14),
            fg_color=C_BG2, border_color=C_BORD, text_color=C_CYN)
        self._key_entry.pack(fill="x", **PAD, pady=(4, 0))
        self._key_entry.bind("<Return>", lambda _: self._submit())

        # ── Status message ────────────────────────────────────────────────────
        self._msg_lbl = ctk.CTkLabel(
            self, text="", font=("Segoe UI", 11),
            text_color=C_RED, wraplength=452, justify="left")
        self._msg_lbl.pack(**PAD, anchor="w", pady=(8, 0))

        # ── Activate button ───────────────────────────────────────────────────
        btn_txt = "Renew License" if self._renewal else "Activate BO Commander"
        self._btn = ctk.CTkButton(
            self, text=btn_txt,
            height=46, corner_radius=8,
            font=("Segoe UI", 14, "bold"),
            fg_color=C_CYN, text_color=C_BG, hover_color="#06b6d4",
            command=self._submit)
        self._btn.pack(fill="x", **PAD, pady=(14, 0))

        # ── Divider ───────────────────────────────────────────────────────────
        ctk.CTkFrame(self, height=1, fg_color=C_BORD).pack(
            fill="x", padx=44, pady=20)

        # ── Contact footer ────────────────────────────────────────────────────
        ctk.CTkLabel(self,
                     text="No key?  Need renewal?  Contact the developer:",
                     font=("Segoe UI", 11), text_color=C_GRY).pack()

        # Email row
        email_row = ctk.CTkFrame(self, fg_color="transparent")
        email_row.pack(pady=(4, 0))
        ctk.CTkLabel(email_row, text="✉",
                     font=("Segoe UI", 13), text_color=C_GRY2).pack(side="left")
        ctk.CTkLabel(email_row, text=f"  {DEVELOPER_EMAIL}",
                     font=("Segoe UI", 12, "bold"),
                     text_color=C_CYN).pack(side="left")

        # LinkedIn row
        li_row = ctk.CTkFrame(self, fg_color="transparent")
        li_row.pack(pady=(3, 0))
        ctk.CTkLabel(li_row, text="🔗",
                     font=("Segoe UI", 13), text_color=C_GRY2).pack(side="left")
        ctk.CTkLabel(li_row, text="  linkedin.com/in/sai-teja-628082288",
                     font=("Segoe UI", 11), text_color=C_GRY).pack(side="left")

        # 30-day reminder note
        ctk.CTkLabel(self,
                     text=f"⏰  License keys are valid for {LICENSE_DAYS} days from activation.",
                     font=("Segoe UI", 10), text_color=C_GRY2).pack(pady=(10, 6))

    # ── Actions ───────────────────────────────────────────────────────────────

    def _submit(self):
        name = self._name_entry.get().strip()
        key  = self._key_entry.get().strip()

        if not name:
            self._msg_lbl.configure(
                text="Please enter your name.", text_color=C_RED)
            return
        if not key:
            self._msg_lbl.configure(
                text="Please enter your license key.", text_color=C_RED)
            return

        self._btn.configure(state="disabled", text="Validating…")
        self.update()

        ok, msg = activate(name, key)

        if ok:
            self.activated = True
            self.user_name = name
            self._msg_lbl.configure(
                text=f"✔  {msg}", text_color=C_GRN)
            self._btn.configure(text="✔  Activated!  Loading BO Commander…")
            self.after(1000, self.destroy)
        else:
            self._msg_lbl.configure(text=msg, text_color=C_RED)
            self._btn.configure(
                state="normal",
                text="Renew License" if self._renewal else "Activate BO Commander")

    def _on_close(self):
        import sys
        print("License activation cancelled. Exiting.")
        sys.exit(0)

    def _centre(self):
        self.update_idletasks()
        w, h = 540, 660
        sw   = self.winfo_screenwidth()
        sh   = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
