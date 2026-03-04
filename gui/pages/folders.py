"""
gui/pages/folders.py
Folders page — browse BO folder tree, view contents, create/delete folders.
Calls: bo_session.get_root_folders(), bo_session.get_folder_contents(id)
"""
import customtkinter as ctk
from core.sapbo_connection import bo_session

C = {
    "bg":      "#0d1824",
    "bg2":     "#112030",
    "bg3":     "#1a2e42",
    "border":  "#1e3a52",
    "cyan":    "#22d3ee",
    "blue":    "#3b82f6",
    "green":   "#22c55e",
    "amber":   "#f59e0b",
    "red":     "#ef4444",
    "text":    "#e2eaf4",
    "text2":   "#8fafc8",
    "header":  ("Segoe UI", 18, "bold"),
    "body":    ("Segoe UI", 13),
    "small":   ("Segoe UI", 11),
    "mono":    ("Courier New", 12),
}


class FoldersPage(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._current_folder_id = None
        self._folder_stack = []   # breadcrumb stack [(id, name), ...]
        self._build()
        self._load_root()

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build(self):
        # Top bar
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(top, text="📁  Folders", font=C["header"],
                     text_color=C["cyan"]).pack(side="left")

        ctk.CTkButton(top, text="⟳  Refresh", width=110, height=34,
                      font=C["body"], fg_color=C["bg3"], border_color=C["border"],
                      border_width=1, hover_color=C["bg2"],
                      command=self._refresh).pack(side="right", padx=(8, 0))

        ctk.CTkButton(top, text="+ New Folder", width=120, height=34,
                      font=C["body"], fg_color=C["cyan"], text_color=C["bg"],
                      hover_color="#06b6d4",
                      command=self._new_folder_dialog).pack(side="right")

        # Breadcrumb bar
        self._breadcrumb_frame = ctk.CTkFrame(self, fg_color=C["bg2"],
                                               corner_radius=6, height=34)
        self._breadcrumb_frame.pack(fill="x", pady=(0, 10))

        # Split pane: tree left, contents right
        pane = ctk.CTkFrame(self, fg_color="transparent")
        pane.pack(fill="both", expand=True)

        # Left: folder tree
        left = ctk.CTkFrame(pane, fg_color=C["bg2"], corner_radius=8, width=280)
        left.pack(side="left", fill="y", padx=(0, 12))
        left.pack_propagate(False)

        ctk.CTkLabel(left, text="Folder Tree", font=("Segoe UI", 12, "bold"),
                     text_color=C["text2"]).pack(pady=(12, 6), padx=14, anchor="w")

        self._tree_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self._tree_scroll.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Right: contents table
        right = ctk.CTkFrame(pane, fg_color=C["bg2"], corner_radius=8)
        right.pack(side="left", fill="both", expand=True)

        # Table header
        hdr = ctk.CTkFrame(right, fg_color=C["bg3"], corner_radius=0, height=36)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        for col, w in [("Name", 500), ("Type", 140), ("Owner", 160), ("ID", 90)]:
            ctk.CTkLabel(hdr, text=col, font=("Segoe UI", 12, "bold"),
                         text_color=C["text2"], width=w, anchor="w"
                         ).pack(side="left", padx=(14, 0))

        self._content_scroll = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self._content_scroll.pack(fill="both", expand=True, padx=4, pady=4)

        # Status bar
        self._status = ctk.CTkLabel(self, text="", font=C["small"],
                                     text_color=C["text2"])
        self._status.pack(anchor="w", pady=(6, 0))

    # ── Data loading ───────────────────────────────────────────────────────────
    def _load_root(self):
        self._folder_stack = []
        self._current_folder_id = None
        self._populate_tree()
        self._show_root_contents()

    def _populate_tree(self):
        for w in self._tree_scroll.winfo_children():
            w.destroy()

        if not bo_session.connected:
            ctk.CTkLabel(self._tree_scroll, text="Not connected",
                         text_color=C["red"], font=C["small"]).pack(pady=8)
            return

        try:
            folders = bo_session.get_root_folders()
        except Exception as e:
            ctk.CTkLabel(self._tree_scroll, text=f"Error: {e}",
                         text_color=C["red"], font=C["small"],
                         wraplength=240).pack(pady=8, padx=8)
            return

        if not folders:
            ctk.CTkLabel(self._tree_scroll, text="No folders found",
                         text_color=C["text2"], font=C["small"]).pack(pady=8)
            return

        # Root entry
        root_btn = ctk.CTkButton(
            self._tree_scroll, text="🏠  Public Folders (root)",
            fg_color=C["bg3"], hover_color=C["border"],
            text_color=C["cyan"], font=C["small"],
            height=30, anchor="w",
            command=self._show_root_contents)
        root_btn.pack(fill="x", pady=1)

        for f in folders:
            name = f.get("name", "Unknown")
            fid  = f.get("id", 0)
            btn  = ctk.CTkButton(
                self._tree_scroll,
                text=f"   📁  {name}",
                fg_color="transparent", hover_color=C["bg3"],
                text_color=C["text"], font=C["small"],
                height=30, anchor="w",
                command=lambda fid=fid, name=name: self._open_folder(fid, name))
            btn.pack(fill="x", pady=1)

    def _show_root_contents(self):
        self._folder_stack = []
        self._current_folder_id = None
        self._update_breadcrumb()
        self._load_folder_contents(root=True)

    def _open_folder(self, folder_id, name):
        self._folder_stack.append((folder_id, name))
        self._current_folder_id = folder_id
        self._update_breadcrumb()
        self._load_folder_contents(folder_id=folder_id)

    def _load_folder_contents(self, folder_id=None, root=False):
        for w in self._content_scroll.winfo_children():
            w.destroy()

        if not bo_session.connected:
            self._row_error("Not connected to SAP BO server.")
            return

        try:
            if root or folder_id is None:
                folders = bo_session.get_root_folders()
                docs    = []
            else:
                folders, docs = bo_session.get_folder_contents(folder_id)
        except Exception as e:
            self._row_error(f"Error loading contents: {e}")
            return

        items = [(f, "Folder") for f in folders] + [(d, d.get("kind", "Document")) for d in docs]

        if not items:
            ctk.CTkLabel(self._content_scroll, text="(empty folder)",
                         text_color=C["text2"], font=C["small"]).pack(pady=20)
            self._status.configure(text="0 items")
            return

        for obj, kind in items:
            self._add_row(obj, kind)

        self._status.configure(text=f"{len(items)} item(s) — {len(folders)} folder(s), {len(docs)} document(s)")

    def _add_row(self, obj, kind):
        name  = obj.get("name", "")
        oid   = obj.get("id", "")
        owner = obj.get("owner", "")
        icon  = "📁" if kind == "Folder" else "📄"

        row = ctk.CTkFrame(self._content_scroll, fg_color="transparent",
                           height=34, corner_radius=4)
        row.pack(fill="x", pady=1)

        def _on_enter(e, r=row): r.configure(fg_color=C["bg3"])
        def _on_leave(e, r=row): r.configure(fg_color="transparent")
        row.bind("<Enter>", _on_enter)
        row.bind("<Leave>", _on_leave)

        name_lbl = ctk.CTkLabel(row, text=f"{icon}  {name}",
                                 font=C["body"], text_color=C["text"],
                                 width=500, anchor="w")
        name_lbl.pack(side="left", padx=(14, 0))

        ctk.CTkLabel(row, text=kind, font=C["small"],
                     text_color=C["text2"], width=140, anchor="w"
                     ).pack(side="left")
        ctk.CTkLabel(row, text=owner, font=C["small"],
                     text_color=C["text2"], width=160, anchor="w"
                     ).pack(side="left")
        ctk.CTkLabel(row, text=str(oid), font=C["mono"],
                     text_color=C["text2"], width=90, anchor="w"
                     ).pack(side="left")

        # Double-click to open folders
        if kind == "Folder":
            name_lbl.bind("<Double-Button-1>",
                          lambda e, fid=oid, nm=name: self._open_folder(fid, nm))
            name_lbl.configure(text_color=C["cyan"], cursor="hand2")

    def _row_error(self, msg):
        row = ctk.CTkFrame(self._content_scroll, fg_color="#1a0808",
                           corner_radius=6)
        row.pack(fill="x", pady=4, padx=4)
        ctk.CTkLabel(row, text=f"⚠  {msg}", font=C["small"],
                     text_color=C["amber"], wraplength=800,
                     justify="left").pack(padx=14, pady=10, anchor="w")

    # ── Breadcrumb ─────────────────────────────────────────────────────────────
    def _update_breadcrumb(self):
        for w in self._breadcrumb_frame.winfo_children():
            w.destroy()

        ctk.CTkLabel(self._breadcrumb_frame, text="  📍 ",
                     font=C["small"], text_color=C["text2"]).pack(side="left")

        # Root link
        root_lbl = ctk.CTkLabel(self._breadcrumb_frame, text="Public Folders",
                                 font=("Segoe UI", 12), text_color=C["cyan"],
                                 cursor="hand2")
        root_lbl.pack(side="left")
        root_lbl.bind("<Button-1>", lambda e: self._show_root_contents())

        for (fid, name) in self._folder_stack:
            ctk.CTkLabel(self._breadcrumb_frame, text=" › ",
                         font=C["small"], text_color=C["text2"]).pack(side="left")
            lbl = ctk.CTkLabel(self._breadcrumb_frame, text=name,
                                font=("Segoe UI", 12), text_color=C["cyan"],
                                cursor="hand2")
            lbl.pack(side="left")
            lbl.bind("<Button-1>",
                     lambda e, fid=fid, nm=name: self._open_folder(fid, nm))

    # ── Actions ────────────────────────────────────────────────────────────────
    def _refresh(self):
        self._populate_tree()
        if self._current_folder_id:
            self._load_folder_contents(folder_id=self._current_folder_id)
        else:
            self._show_root_contents()

    def _new_folder_dialog(self):
        if not bo_session.connected:
            return
        dlg = ctk.CTkToplevel(self)
        dlg.title("New Folder")
        dlg.geometry("360x200")
        dlg.configure(fg_color="#0d1824")
        dlg.grab_set()

        ctk.CTkLabel(dlg, text="Folder Name:", font=C["body"],
                     text_color=C["text2"]).pack(pady=(20, 4))
        entry = ctk.CTkEntry(dlg, width=300, font=C["body"],
                              fg_color=C["bg3"], border_color=C["border"],
                              text_color=C["text"])
        entry.pack()

        msg = ctk.CTkLabel(dlg, text="", font=C["small"], text_color=C["green"])
        msg.pack(pady=6)

        def _create():
            name = entry.get().strip()
            if not name:
                msg.configure(text="Please enter a folder name.", text_color=C["red"])
                return
            parent = self._current_folder_id or 23
            ok, result = bo_session.create_folder(name, parent_id=parent)
            if ok:
                msg.configure(text=f"Created: {name}", text_color=C["green"])
                dlg.after(900, dlg.destroy)
                dlg.after(950, self._refresh)
            else:
                msg.configure(text=f"Failed: {result}", text_color=C["red"])

        ctk.CTkButton(dlg, text="Create", fg_color=C["cyan"],
                      text_color=C["bg"], hover_color="#06b6d4",
                      command=_create).pack(pady=10)
