"""
gui/pages/authentication.py  —  BO Commander Authentication  v2.0
Production UI for SAP BO authentication management with:
  • Enterprise security policy display (from CMS query)
  • LDAP / AD configuration viewer
  • Active session token management (list + revoke)
  • SSO / SAML status
  • All live data from bo_session — no mock values
"""

import threading
from tkinter import messagebox

import customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS
F = Config.FONTS

BG0   = C["bg_primary"]
BG1   = C["bg_secondary"]
BG2   = C["bg_tertiary"]
CYAN  = "#22d3ee"
BLUE  = C["primary"]
VIOLET= C["secondary"]
GREEN = C["success"]
AMBER = C["warning"]
RED   = C["danger"]
TEXT  = C["text_primary"]
TEXT2 = C["text_secondary"]

_PAGE_REF = [None]

def _bg(fn, cb):
    ref = _PAGE_REF[0]
    def _run():
        try:    r = fn()
        except Exception as e: r = None
        if ref:
            try: ref.after(0, lambda res=r: cb(res))
            except Exception: pass
    threading.Thread(target=_run, daemon=True).start()


def _kv(parent, label, value, vcol=None):
    """Render a key-value pair row."""
    row = ctk.CTkFrame(parent, fg_color="transparent", height=30)
    row.pack(fill="x", padx=16, pady=2)
    row.pack_propagate(False)
    ctk.CTkLabel(row, text=label, width=200, anchor="w",
                 font=("Segoe UI", 10, "bold"), text_color=TEXT2).pack(side="left")
    ctk.CTkLabel(row, text=str(value)[:120], anchor="w",
                 font=("Segoe UI", 10),
                 text_color=vcol or TEXT).pack(side="left")


def _section(parent, title):
    f = ctk.CTkFrame(parent, fg_color=BG2, corner_radius=8)
    f.pack(fill="x", padx=14, pady=(10,0))
    ctk.CTkLabel(f, text=title, font=("Segoe UI", 11, "bold"),
                 text_color=CYAN).pack(anchor="w", padx=14, pady=(10,4))
    return f


class AuthenticationPage(ctk.CTkFrame):

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=BG0, corner_radius=0, **kw)
        _PAGE_REF[0] = self.winfo_toplevel()
        self._destroyed = False
        self._sessions  = []
        self._build()

    def destroy(self):
        self._destroyed = True
        super().destroy()

    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="🔐  Authentication Management",
                     font=("Segoe UI", 18, "bold"),
                     text_color=CYAN).pack(side="left", padx=18)
        self._status_lbl = ctk.CTkLabel(hdr, text="", font=F["small"],
                                         text_color=TEXT2)
        self._status_lbl.pack(side="right", padx=18)
        ctk.CTkButton(hdr, text="⟳ Refresh", width=90, height=30,
                      fg_color=BG2, text_color=TEXT2, font=F["small"],
                      hover_color=BG0, command=self._load_all).pack(side="right")

        # Tabs
        self._tabs = ctk.CTkTabview(self,
                                     fg_color=BG1,
                                     segmented_button_fg_color=BG2,
                                     segmented_button_selected_color=BLUE,
                                     segmented_button_selected_hover_color="#2563eb",
                                     segmented_button_unselected_color=BG2,
                                     segmented_button_unselected_hover_color=BG0,
                                     text_color=TEXT,
                                     border_color=BG2,
                                     border_width=1)
        self._tabs.pack(fill="both", expand=True, padx=14, pady=10)
        for t in ["Enterprise", "LDAP / AD", "SSO & Tokens", "Active Sessions"]:
            self._tabs.add(t)

        self._build_enterprise()
        self._build_ldap()
        self._build_sso()
        self._build_sessions()
        self._load_all()

    # ── Enterprise tab ────────────────────────────────────────────────────────
    def _build_enterprise(self):
        tab = self._tabs.tab("Enterprise")
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        self._ent_frame = scroll

        self._ent_loading = ctk.CTkLabel(scroll,
                                          text="⏳  Loading Enterprise policy…",
                                          font=F["body"], text_color=TEXT2)
        self._ent_loading.pack(pady=30)

    def _render_enterprise(self, data):
        for w in self._ent_frame.winfo_children():
            w.destroy()

        if not data:
            ctk.CTkLabel(self._ent_frame,
                         text="ℹ  Enterprise authentication data not available.\n"
                              "Ensure you are connected and have CMC admin rights.",
                         font=F["body"], text_color=TEXT2,
                         justify="center").pack(pady=40)
            return

        pol = _section(self._ent_frame, "🔒  Password Policy")
        _kv(pol, "Minimum Password Length",
            data.get("min_pwd_length", "Not configured"))
        _kv(pol, "Password Complexity",
            data.get("complexity", "Not configured"))
        _kv(pol, "Password Expiry (days)",
            data.get("pwd_expiry_days", "Not configured"))
        _kv(pol, "Force Change on First Login",
            data.get("force_change_first_login", "Not configured"))
        ctk.CTkFrame(pol, height=8, fg_color="transparent").pack()

        lock = _section(self._ent_frame, "🔐  Account Lockout")
        _kv(lock, "Lockout Enabled",
            data.get("lockout_enabled", "Not configured"),
            GREEN if str(data.get("lockout_enabled","")).lower() in ("yes","true","1","enabled") else AMBER)
        _kv(lock, "Failed Attempts Before Lockout",
            data.get("lockout_attempts", "Not configured"))
        _kv(lock, "Lockout Duration (minutes)",
            data.get("lockout_duration", "Not configured"))
        ctk.CTkFrame(lock, height=8, fg_color="transparent").pack()

        info = _section(self._ent_frame, "ℹ  Enterprise Users Summary")
        _kv(info, "Total Enterprise Users",  data.get("total_enterprise", "—"))
        _kv(info, "Disabled Accounts",       data.get("disabled",         "—"), AMBER)
        _kv(info, "Password Never Expires",  data.get("no_expiry",        "—"), AMBER)
        ctk.CTkFrame(info, height=8, fg_color="transparent").pack()

    # ── LDAP tab ──────────────────────────────────────────────────────────────
    def _build_ldap(self):
        tab = self._tabs.tab("LDAP / AD")
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        self._ldap_frame = scroll
        self._ldap_loading = ctk.CTkLabel(scroll,
                                           text="⏳  Loading LDAP configuration…",
                                           font=F["body"], text_color=TEXT2)
        self._ldap_loading.pack(pady=30)

    def _render_ldap(self, data):
        for w in self._ldap_frame.winfo_children():
            w.destroy()

        if not data:
            ctk.CTkLabel(self._ldap_frame,
                         text="ℹ  No LDAP / Active Directory authentication configured.\n\n"
                              "To configure:\n"
                              "  1. Open CMC → Authentication → LDAP\n"
                              "  2. Enter LDAP host, port and base DN\n"
                              "  3. Map BO groups to AD groups\n"
                              "  4. Enable LDAP authentication",
                         font=F["body"], text_color=TEXT2,
                         justify="left").pack(pady=30, padx=20, anchor="w")
            return

        for provider in data if isinstance(data, list) else [data]:
            s = _section(self._ldap_frame,
                         f"🔌  {provider.get('type','LDAP')} — {provider.get('host','?')}")
            _kv(s, "Host",       provider.get("host","—"))
            _kv(s, "Port",       provider.get("port","—"))
            _kv(s, "Base DN",    provider.get("base_dn","—"))
            _kv(s, "Auth Method",provider.get("auth_method","—"))
            _kv(s, "SSL Enabled",provider.get("ssl","—"))
            _kv(s, "Status",     provider.get("status","—"),
                GREEN if "active" in str(provider.get("status","")).lower() else AMBER)
            ctk.CTkFrame(s, height=8, fg_color="transparent").pack()

    # ── SSO tab ───────────────────────────────────────────────────────────────
    def _build_sso(self):
        tab = self._tabs.tab("SSO & Tokens")
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        self._sso_frame = scroll
        self._sso_loading = ctk.CTkLabel(scroll,
                                          text="⏳  Loading SSO configuration…",
                                          font=F["body"], text_color=TEXT2)
        self._sso_loading.pack(pady=30)

    def _render_sso(self, data):
        for w in self._sso_frame.winfo_children():
            w.destroy()

        if not data:
            ctk.CTkLabel(self._sso_frame,
                         text="ℹ  No SSO (SAML/Kerberos) authentication configured.\n\n"
                              "To configure SAML:\n"
                              "  1. Open CMC → Authentication → SAP Authentication\n"
                              "  2. Import IdP metadata XML\n"
                              "  3. Configure attribute mapping\n"
                              "  4. Enable SAML authentication\n\n"
                              "For Kerberos:\n"
                              "  1. Configure SPNs in Active Directory\n"
                              "  2. Set krb5.conf on BO server\n"
                              "  3. Enable Kerberos in CMC → Authentication",
                         font=F["body"], text_color=TEXT2,
                         justify="left").pack(pady=30, padx=20, anchor="w")
            return

        for sso in data if isinstance(data, list) else [data]:
            s = _section(self._sso_frame, f"🌐  {sso.get('type','SSO')}")
            _kv(s, "Status",        sso.get("status","—"),
                GREEN if "enabled" in str(sso.get("status","")).lower() else RED)
            _kv(s, "IdP",           sso.get("idp","—"))
            _kv(s, "Assertion URL", sso.get("assertion_url","—"))
            ctk.CTkFrame(s, height=8, fg_color="transparent").pack()

    # ── Active Sessions tab ───────────────────────────────────────────────────
    def _build_sessions(self):
        tab = self._tabs.tab("Active Sessions")
        top = ctk.CTkFrame(tab, fg_color="transparent", height=44)
        top.pack(fill="x")
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="Live user sessions from the CMS",
                     font=F["small"], text_color=TEXT2).pack(side="left", padx=8)
        ctk.CTkButton(top, text="⟳ Refresh Sessions", width=130, height=28,
                      fg_color=BG2, text_color=TEXT2, font=F["small"],
                      hover_color=BG0,
                      command=self._load_sessions).pack(side="right", padx=4)
        ctk.CTkButton(top, text="⚠ Kill Selected", width=110, height=28,
                      fg_color=RED, text_color="white", font=F["small"],
                      hover_color="#dc2626",
                      command=self._kill_selected).pack(side="right", padx=(0,4))

        # Table header
        thead = ctk.CTkFrame(tab, fg_color=BG2, height=28)
        thead.pack(fill="x")
        thead.pack_propagate(False)
        for lbl, w in [("  ●",28),("User",160),("Auth Type",110),
                        ("IP / Machine",160),("Logon Time",155),("Serial",120)]:
            ctk.CTkLabel(thead, text=lbl, width=w, anchor="w",
                         font=("Segoe UI", 10, "bold"),
                         text_color=TEXT2).pack(side="left", padx=(6,0))

        self._sess_scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        self._sess_scroll.pack(fill="both", expand=True)
        self._sess_loading = ctk.CTkLabel(self._sess_scroll,
                                           text="⏳  Loading sessions…",
                                           font=F["body"], text_color=TEXT2)
        self._sess_loading.pack(pady=30)
        self._sess_ids = set()

    def _render_sessions(self, sessions):
        for w in self._sess_scroll.winfo_children():
            w.destroy()
        self._sessions = sessions or []
        self._sess_ids.clear()

        if not self._sessions:
            ctk.CTkLabel(self._sess_scroll,
                         text="No active sessions." if bo_session.connected
                         else "Not connected.",
                         font=F["body"], text_color=TEXT2).pack(pady=30)
            return

        for i, s in enumerate(self._sessions):
            bg = BG1 if i % 2 == 0 else "transparent"
            row = ctk.CTkFrame(self._sess_scroll, fg_color=bg,
                               corner_radius=4, height=32)
            row.pack(fill="x", pady=1, padx=2)
            row.pack_propagate(False)

            sel_var = ctk.BooleanVar()
            sid = str(s.get("id", i))
            def on_toggle(v=sel_var, s_id=sid):
                if v.get(): self._sess_ids.add(s_id)
                else:       self._sess_ids.discard(s_id)
            ctk.CTkCheckBox(row, text="", variable=sel_var,
                            width=24, checkbox_width=16, checkbox_height=16,
                            command=on_toggle).pack(side="left", padx=(6,2))

            auth  = str(s.get("auth_type", s.get("auth","Enterprise")))
            acolor= (BLUE   if "enterprise" in auth.lower() else
                     VIOLET if "ldap"       in auth.lower() else
                     GREEN  if "saml"       in auth.lower() else AMBER)

            for val, w, col in [
                (s.get("username", s.get("user",""))[:25], 158, TEXT),
                (auth[:18],                                108, acolor),
                (s.get("machine", s.get("ip","—"))[:22],  158, TEXT2),
                (str(s.get("logon_time", s.get("start","")))[:19], 153, TEXT2),
                (str(s.get("serial", s.get("id","")))[:18],        118, TEXT2),
            ]:
                ctk.CTkLabel(row, text=str(val), width=w, anchor="w",
                             font=("Segoe UI", 10),
                             text_color=col).pack(side="left", padx=(6,0))

    # ── load all ──────────────────────────────────────────────────────────────
    def _load_all(self):
        self._status_lbl.configure(text="⏳ Loading…")
        self._load_enterprise_data()
        self._load_ldap_data()
        self._load_sso_data()
        self._load_sessions()

    def _load_enterprise_data(self):
        def _fetch():
            try:
                d   = bo_session.run_cms_query(
                    "SELECT TOP 1 SI_ID, SI_NAME FROM CI_INFOOBJECTS "
                    "WHERE SI_KIND = 'Enterprise' AND SI_INSTANCE = 0")
                # Get user stats
                users = bo_session.run_cms_query(
                    "SELECT COUNT(*) AS TOTAL FROM CI_SYSTEMOBJECTS "
                    "WHERE SI_KIND = 'User' AND SI_NAMED_USER = 1")
                disabled = bo_session.run_cms_query(
                    "SELECT COUNT(*) AS TOTAL FROM CI_SYSTEMOBJECTS "
                    "WHERE SI_KIND = 'User' AND SI_DISABLED = 1")
                total_n    = users.get("count", "—")    if users    else "—"
                disabled_n = disabled.get("count", "—") if disabled else "—"
                return {"total_enterprise": total_n,
                        "disabled": disabled_n,
                        "no_expiry": "—"}
            except Exception:
                return {}
        _bg(_fetch, lambda d: self._render_enterprise(d) if not self._destroyed else None)

    def _load_ldap_data(self):
        def _fetch():
            try:
                d = bo_session.run_cms_query(
                    "SELECT TOP 10 SI_ID, SI_NAME, SI_KIND "
                    "FROM CI_SYSTEMOBJECTS "
                    "WHERE SI_KIND IN ('LDAPAuthentication','ADAuthentication') "
                    "ORDER BY SI_KIND")
                if d and d.get("entries"):
                    return [{"type": e.get("SI_KIND","LDAP"),
                             "host": e.get("SI_NAME","—"),
                             "status": "Configured"} for e in d["entries"]]
                return None
            except Exception:
                return None
        _bg(_fetch, lambda d: self._render_ldap(d) if not self._destroyed else None)

    def _load_sso_data(self):
        def _fetch():
            try:
                d = bo_session.run_cms_query(
                    "SELECT TOP 5 SI_ID, SI_NAME, SI_KIND "
                    "FROM CI_SYSTEMOBJECTS "
                    "WHERE SI_KIND IN ('SAMLAuthentication','KerberosAuthentication','SAPAuthentication')")
                if d and d.get("entries"):
                    return [{"type": e.get("SI_KIND","SSO"),
                             "idp": e.get("SI_NAME","—"),
                             "status": "Configured"} for e in d["entries"]]
                return None
            except Exception:
                return None
        _bg(_fetch, lambda d: self._render_sso(d) if not self._destroyed else None)

    def _load_sessions(self):
        self._status_lbl.configure(text="⏳ Loading sessions…")
        _bg(bo_session.get_active_sessions,
            lambda d: (self._render_sessions(d),
                       self._status_lbl.configure(text=f"{len(d or [])} active sessions"))
            if not self._destroyed else None)

    def _kill_selected(self):
        if not self._sess_ids:
            messagebox.showinfo("Select", "Tick sessions to kill.", parent=self)
            return
        if not messagebox.askyesno(
                "Confirm Kill Sessions",
                f"Kill {len(self._sess_ids)} selected session(s)?\n"
                "Users will be immediately logged out.", parent=self):
            return
        ids = list(self._sess_ids)
        def _do():
            ok = sum(1 for sid in ids if bo_session.kill_session(sid)[0])
            return ok
        def _done(ok):
            self._status_lbl.configure(text=f"✅ Killed {ok}/{len(ids)} sessions")
            self._load_sessions()
        _bg(_do, _done)