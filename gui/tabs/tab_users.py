"""
gui/tabs/tab_users.py  —  Users & Groups  (Full CRUD)
GET  list users / groups / hierarchy
POST create user
PUT  reset password, disable, enable
DEL  delete user
"""
from gui.tabs._base import *


class UsersTab(BaseTab):

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._users  = []
        self._groups = []
        self._mode   = "users"   # "users" | "groups"
        self._build()
        self._load()

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build(self):
        # Header
        rf = self._page_header("Users & Groups", "👥",
                                "Manage enterprise users, groups, and access")
        ctk.CTkButton(rf, text="⟳ Refresh", width=90, height=30,
                      fg_color=BG2, text_color=TEXT, font=F_SM,
                      command=self._load).pack(side="right", padx=3)
        ctk.CTkButton(rf, text="➕ Create User", width=110, height=30,
                      fg_color=GREEN, text_color="white", font=F_SM,
                      command=self._create_user_dialog).pack(side="right", padx=3)

        body = self._body
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)

        # ── Stat tiles row ────────────────────────────────────────────────────
        tiles = ctk.CTkFrame(body, fg_color="transparent")
        tiles.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
        self._t = {}
        for key, label, color, icon in [
            ("total",    "Total Users",   CYAN,   "👥"),
            ("enterprise","Enterprise",   BLUE,   "🏢"),
            ("ldap",     "LDAP/AD",       VIOLET, "🔗"),
            ("disabled", "Disabled",      AMBER,  "⛔"),
            ("groups",   "Groups",        TEAL,   "🗂"),
        ]:
            card, val = stat_tile(tiles, label, "—", color, icon)
            card.pack(side="left", padx=(0, 8), fill="both", expand=True)
            self._t[key] = val

        # ── Mode toggle + search ──────────────────────────────────────────────
        bar = ctk.CTkFrame(body, fg_color=BG1, corner_radius=8, height=44)
        bar.grid(row=1, column=0, sticky="ew", padx=14, pady=8)
        bar.pack_propagate(False)

        self._mode_user_btn = ctk.CTkButton(bar, text="👤 Users", width=100, height=30,
                                             fg_color=BLUE, text_color="white", font=F_SM,
                                             command=lambda: self._set_mode("users"))
        self._mode_user_btn.pack(side="left", padx=8, pady=6)

        self._mode_grp_btn  = ctk.CTkButton(bar, text="🗂 Groups", width=100, height=30,
                                              fg_color=BG2, text_color=TEXT2, font=F_SM,
                                              command=lambda: self._set_mode("groups"))
        self._mode_grp_btn.pack(side="left", padx=2, pady=6)

        self._q = ctk.StringVar()
        self._q.trace_add("write", lambda *_: self._render())
        ctk.CTkEntry(bar, textvariable=self._q,
                     placeholder_text="🔎 Search…",
                     width=240, height=30, fg_color=BG2, border_color=BG2,
                     text_color=TEXT, font=F_SM).pack(side="left", padx=8)

        # ── Tree ──────────────────────────────────────────────────────────────
        cols_users = [
            ("name",    "Username",        180),
            ("email",   "Email",           200),
            ("auth",    "Auth Type",        90),
            ("status",  "Status",           90),
            ("last",    "Last Login",       150),
            ("created", "Created",         140),
        ]
        self._tree_u, tree_frame_u = make_tree(body, cols_users)
        tree_frame_u.grid(row=2, column=0, sticky="nsew", padx=14, pady=0)
        self._tree_frame_u = tree_frame_u

        cols_groups = [
            ("name",    "Group Name",      200),
            ("desc",    "Description",     300),
            ("owner",   "Owner",           120),
            ("created", "Created",         150),
        ]
        self._tree_g, tree_frame_g = make_tree(body, cols_groups)
        tree_frame_g.grid(row=2, column=0, sticky="nsew", padx=14, pady=0)
        self._tree_frame_g = tree_frame_g
        tree_frame_g.grid_remove()

        # ── Action bar ────────────────────────────────────────────────────────
        act = ctk.CTkFrame(body, fg_color=BG1, corner_radius=0, height=42)
        act.grid(row=3, column=0, sticky="ew")
        act.pack_propagate(False)

        for text, color, cmd in [
            ("🔑 Reset Password", AMBER,  self._reset_password),
            ("⛔ Disable",        RED,    lambda: self._toggle_disable(True)),
            ("✅ Enable",         GREEN,  lambda: self._toggle_disable(False)),
            ("🗑 Delete",         RED,    self._delete_user),
        ]:
            ctk.CTkButton(act, text=text, width=130, height=30,
                          fg_color=BG2, hover_color=color,
                          text_color=TEXT, font=F_SM,
                          command=cmd).pack(side="left", padx=4, pady=6)

    # ── Data loading ──────────────────────────────────────────────────────────
    def _load(self):
        self.set_status("⏳ Loading users and groups…", AMBER)
        bg(lambda: (bo_session.get_users_detailed_full(),
                    bo_session.get_groups_detailed()),
           self._on_loaded, self)

    def _on_loaded(self, result):
        if not result:
            self.set_status("❌ Failed to load users", RED)
            return
        self._users, self._groups = result
        self._update_tiles()
        self._render()
        self.set_status(f"✅ {len(self._users)} users  |  {len(self._groups)} groups", GREEN)

    def _update_tiles(self):
        self._t["total"].configure(text=str(len(self._users)))
        ent = sum(1 for u in self._users if "enterprise" in str(u.get("auth_type","")).lower())
        ldp = sum(1 for u in self._users if any(x in str(u.get("auth_type","")).lower() for x in ("ldap","ad","win")))
        dis = sum(1 for u in self._users if u.get("disabled"))
        self._t["enterprise"].configure(text=str(ent))
        self._t["ldap"].configure(text=str(ldp))
        self._t["disabled"].configure(text=str(dis))
        self._t["groups"].configure(text=str(len(self._groups)))

    # ── Mode + render ─────────────────────────────────────────────────────────
    def _set_mode(self, mode: str):
        self._mode = mode
        if mode == "users":
            self._mode_user_btn.configure(fg_color=BLUE, text_color="white")
            self._mode_grp_btn.configure(fg_color=BG2, text_color=TEXT2)
            self._tree_frame_u.grid()
            self._tree_frame_g.grid_remove()
        else:
            self._mode_grp_btn.configure(fg_color=BLUE, text_color="white")
            self._mode_user_btn.configure(fg_color=BG2, text_color=TEXT2)
            self._tree_frame_g.grid()
            self._tree_frame_u.grid_remove()
        self._render()

    def _render(self):
        q = self._q.get().lower()
        if self._mode == "users":
            tree = self._tree_u
            for r in tree.get_children(): tree.delete(r)
            for u in self._users:
                name = u.get("name", "")
                if q and q not in name.lower() and q not in u.get("email","").lower():
                    continue
                status = u.get("account_status", "Enabled")
                auth   = u.get("auth_type", "Enterprise")
                col_tag = "dis" if status == "Disabled" else ("lock" if status == "Locked" else "ok")
                tree.insert("", "end", iid=str(u.get("id","")), tags=(col_tag,),
                            values=(name, u.get("email",""), auth, status,
                                    str(u.get("last_login",""))[:19],
                                    str(u.get("created",""))[:16]))
            tree.tag_configure("ok",   foreground=TEXT)
            tree.tag_configure("dis",  foreground=RED)
            tree.tag_configure("lock", foreground=AMBER)
            self.set_status(f"👤 {len(self._tree_u.get_children())} users shown")
        else:
            tree = self._tree_g
            for r in tree.get_children(): tree.delete(r)
            for g in self._groups:
                if q and q not in g.get("name","").lower():
                    continue
                tree.insert("", "end", iid=str(g.get("id","")),
                            values=(g.get("name",""), g.get("description",""),
                                    g.get("owner",""), str(g.get("created",""))[:16]))
            self.set_status(f"🗂 {len(self._tree_g.get_children())} groups shown")

    def _selected_ids(self):
        tree = self._tree_u if self._mode == "users" else self._tree_g
        return tree.selection()

    # ── CRUD actions ──────────────────────────────────────────────────────────
    def _create_user_dialog(self):
        _CreateUserDialog(self)

    def _reset_password(self):
        sel = self._selected_ids()
        if not sel:
            show_info("Select User", "Select a user first.", parent=self)
            return
        uid = sel[0]
        uname = self._tree_u.item(uid)["values"][0]
        d = _PasswordDialog(self, uname)
        self.wait_window(d)
        if not d.result:
            return
        self.set_status(f"⏳ Resetting password for {uname}…", AMBER)
        bg(lambda: bo_session.reset_user_password(uid, d.result),
           lambda r: self._handle_write(r, f"Password reset for {uname}"), self)

    def _toggle_disable(self, disable: bool):
        sel = self._selected_ids()
        if not sel:
            show_info("Select User", "Select a user first.", parent=self)
            return
        action = "Disable" if disable else "Enable"
        uname  = self._tree_u.item(sel[0])["values"][0]
        if not confirm(f"{action} User", f"{action} user: {uname}?", parent=self):
            return
        uid = sel[0]
        self.set_status(f"⏳ {action}ing {uname}…", AMBER)
        bg(lambda: bo_session.disable_user(uid, disable),
           lambda r: (self._handle_write(r, f"{uname} {action}d"), self._load()), self)

    def _delete_user(self):
        sel = self._selected_ids()
        if not sel:
            show_info("Select User", "Select a user first.", parent=self)
            return
        uid   = sel[0]
        uname = self._tree_u.item(uid)["values"][0]
        if not confirm("Delete User",
                       f"Permanently delete user:\n\n{uname}\n\n"
                       "This cannot be undone.", parent=self):
            return
        self.set_status(f"⏳ Deleting {uname}…", AMBER)
        bg(lambda: bo_session.delete_user(uid),
           lambda r: (self._handle_write(r, f"User {uname} deleted"), self._load()), self)

    def _handle_write(self, result, success_msg: str):
        if isinstance(result, tuple):
            ok, msg = result[0], result[1] if len(result) > 1 else ""
        else:
            ok, msg = bool(result), ""
        if ok:
            self.set_status(f"✅ {success_msg}", GREEN)
        else:
            self.set_status(f"❌ {msg[:80]}", RED)
            show_error("Operation Failed", msg, parent=self)


# ── Dialogs ───────────────────────────────────────────────────────────────────
class _CreateUserDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self._parent = parent
        self.title("➕ Create New User")
        self.geometry("460x480")
        self.configure(fg_color=BG0)
        self.grab_set()
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="➕  Create New User",
                     font=F_H2, text_color=CYAN).pack(pady=(20, 6))
        ctk.CTkFrame(self, fg_color=BG2, height=1).pack(fill="x", padx=20)

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=24, pady=10)

        self._entries = {}
        fields = [
            ("username",  "Username *",          ""),
            ("password",  "Password *",           ""),
            ("full_name", "Full Name",            ""),
            ("email",     "Email Address",        ""),
        ]
        for key, label, placeholder in fields:
            ctk.CTkLabel(form, text=label, font=F_SM,
                         text_color=TEXT2, anchor="w").pack(fill="x", pady=(6, 1))
            show = "*" if key == "password" else ""
            e = ctk.CTkEntry(form, placeholder_text=placeholder,
                              fg_color=BG2, border_color=BG2,
                              text_color=TEXT, font=F_BODY, show=show)
            e.pack(fill="x")
            self._entries[key] = e

        ctk.CTkLabel(form, text="Auth Type", font=F_SM,
                     text_color=TEXT2, anchor="w").pack(fill="x", pady=(6, 1))
        self._auth = ctk.CTkOptionMenu(form,
                                        values=["secEnterprise", "secLDAP",
                                                "secWindowsAD", "secSAPR3"],
                                        fg_color=BG2, button_color=BG2,
                                        dropdown_fg_color=BG1, text_color=TEXT,
                                        font=F_BODY)
        self._auth.pack(fill="x")

        ctk.CTkButton(self, text="✅ Create User", height=38,
                      fg_color=GREEN, text_color="white", font=F_H3,
                      command=self._create).pack(fill="x", padx=24, pady=8)
        ctk.CTkButton(self, text="Cancel", height=34,
                      fg_color=BG2, text_color=TEXT2, font=F_SM,
                      command=self.destroy).pack(fill="x", padx=24, pady=(0, 16))

    def _create(self):
        name  = self._entries["username"].get().strip()
        pwd   = self._entries["password"].get().strip()
        fname = self._entries["full_name"].get().strip()
        email = self._entries["email"].get().strip()
        auth  = self._auth.get()

        if not name or not pwd:
            show_error("Missing Fields", "Username and Password are required.", parent=self)
            return

        self.destroy()

        def _do():
            return bo_session.create_user(name, pwd, email, fname, auth)

        def _done(r):
            ok  = r[0] if isinstance(r, tuple) else bool(r)
            msg = r[1] if isinstance(r, tuple) and len(r) > 1 else ""
            if ok:
                self._parent.set_status(f"✅ User '{name}' created", GREEN)
                self._parent._load()
            else:
                show_error("Create Failed", msg, parent=self._parent)
                self._parent.set_status(f"❌ Create failed: {msg[:60]}", RED)

        bg(_do, _done, self._parent)


class _PasswordDialog(ctk.CTkToplevel):
    def __init__(self, parent, username: str):
        super().__init__(parent)
        self.result = None
        self.title("🔑 Reset Password")
        self.geometry("380x220")
        self.configure(fg_color=BG0)
        self.grab_set()
        ctk.CTkLabel(self, text=f"Reset password for:\n{username}",
                     font=F_H3, text_color=TEXT).pack(pady=(20, 8))
        self._pwd = ctk.CTkEntry(self, placeholder_text="New password",
                                  fg_color=BG2, border_color=BG2,
                                  text_color=TEXT, font=F_BODY, show="*")
        self._pwd.pack(fill="x", padx=24)
        ctk.CTkButton(self, text="✅ Reset", height=36, fg_color=GREEN,
                      text_color="white", font=F_SM,
                      command=self._ok).pack(fill="x", padx=24, pady=12)
        ctk.CTkButton(self, text="Cancel", height=30, fg_color=BG2,
                      text_color=TEXT2, font=F_SM,
                      command=self.destroy).pack(fill="x", padx=24)

    def _ok(self):
        pwd = self._pwd.get().strip()
        if not pwd:
            return
        self.result = pwd
        self.destroy()
