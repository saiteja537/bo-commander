"""gui/pages/recycle_bin.py — BO Recycle Bin / deleted objects viewer"""
import threading
import customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session

C = Config.COLORS


class RecycleBinPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0)

        top = ctk.CTkFrame(self, fg_color='transparent', height=50)
        top.pack(fill='x', padx=20, pady=(15, 0))
        top.pack_propagate(False)
        ctk.CTkLabel(top, text='🗑  Recycle Bin',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')

        self._restore_btn = ctk.CTkButton(top, text='♻ Restore Selected',
                                          width=140, height=32,
                                          fg_color=C['accent'],
                                          hover_color='#059669',
                                          state='disabled',
                                          command=self._restore_selected)
        self._restore_btn.pack(side='right')

        self._del_btn = ctk.CTkButton(top, text='🗑 Purge Selected',
                                      width=120, height=32,
                                      fg_color=C['danger'],
                                      hover_color='#DC2626',
                                      state='disabled',
                                      command=self._purge_selected)
        self._del_btn.pack(side='right', padx=6)

        ctk.CTkButton(top, text='🔄 Refresh', width=90, height=30,
                      fg_color=C['bg_tertiary'], text_color=C['text_primary'],
                      command=self._load).pack(side='right', padx=(0, 8))

        self._status = ctk.CTkLabel(top, text='', font=('Segoe UI', 11),
                                    text_color=C['text_secondary'])
        self._status.pack(side='left', padx=14)

        ctk.CTkLabel(self, text='Objects deleted by users and stored in the BO Recycle Bin (Inbox).',
                     font=('Segoe UI', 11), text_color=C['text_secondary']).pack(anchor='w', padx=22, pady=(2,8))

        hdr = ctk.CTkFrame(self, fg_color=C['bg_tertiary'], corner_radius=6)
        hdr.pack(fill='x', padx=15, pady=(0, 2))
        ctk.CTkLabel(hdr, text='', width=28).pack(side='left', padx=6)
        for label, width in [('Name', 320), ('Kind', 160), ('Owner', 130),
                              ('Deleted', 150), ('Original Folder', 200)]:
            ctk.CTkLabel(hdr, text=label, width=width, anchor='w',
                         font=('Segoe UI', 10, 'bold'),
                         text_color=C['text_secondary']).pack(side='left', padx=4, pady=6)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=C['bg_secondary'], corner_radius=8)
        self.scroll.pack(fill='both', expand=True, padx=15, pady=(0, 15))

        self._checkboxes = {}
        self._load()

    def _load(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        self._checkboxes.clear()
        self._status.configure(text='Loading…')
        self._restore_btn.configure(state='disabled')
        self._del_btn.configure(state='disabled')
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        rows = []
        if not bo_session.connected:
            self.after(0, lambda: self._render([])); return
        try:
            # Recycle Bin objects have SI_RECYCLABLE=1 or live under a Trash folder
            d = bo_session.run_cms_query(
                "SELECT TOP 200 SI_ID, SI_NAME, SI_KIND, SI_OWNER, "
                "SI_CREATION_TIME, SI_PARENTID, SI_UPDATE_TS "
                "FROM CI_INFOOBJECTS "
                "WHERE SI_INSTANCE=0 AND SI_RECYCLABLE=1 "
                "ORDER BY SI_UPDATE_TS DESC"
            )
            if d and d.get('entries'):
                for e in d['entries']:
                    rows.append({
                        'id':      e.get('SI_ID', 0),
                        'name':    e.get('SI_NAME', ''),
                        'kind':    e.get('SI_KIND', ''),
                        'owner':   e.get('SI_OWNER', ''),
                        'deleted': str(e.get('SI_UPDATE_TS', ''))[:16],
                        'folder':  f"ParentID: {e.get('SI_PARENTID','')}",
                    })
        except Exception:
            # Fallback: objects in trash-like state
            try:
                d = bo_session.run_cms_query(
                    "SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER, SI_UPDATE_TS "
                    "FROM CI_INFOOBJECTS "
                    "WHERE SI_INSTANCE=0 AND SI_KIND IN ('Webi','CrystalReport','Folder') "
                    "AND SI_PARENTID=5 "   # ParentID 5 = Recycle Bin in many BO installs
                    "ORDER BY SI_UPDATE_TS DESC"
                )
                if d and d.get('entries'):
                    for e in d['entries']:
                        rows.append({'id': e.get('SI_ID',0), 'name': e.get('SI_NAME',''),
                                     'kind': e.get('SI_KIND',''), 'owner': e.get('SI_OWNER',''),
                                     'deleted': str(e.get('SI_UPDATE_TS',''))[:16], 'folder': 'Recycle Bin'})
            except Exception:
                pass
        self.after(0, lambda r=rows: self._render(r))

    def _render(self, rows):
        for w in self.scroll.winfo_children():
            w.destroy()
        self._checkboxes.clear()

        if not rows:
            ctk.CTkLabel(self.scroll,
                         text='✅  Recycle Bin is empty.',
                         font=('Segoe UI', 13), text_color=C['success']).pack(pady=40)
            self._status.configure(text='Empty')
            return

        self._status.configure(text=f'{len(rows)} object(s) in Recycle Bin')
        self._restore_btn.configure(state='normal')
        self._del_btn.configure(state='normal')

        for i, r in enumerate(rows):
            row = ctk.CTkFrame(self.scroll,
                               fg_color=C['bg_tertiary'] if i % 2 == 0 else C['bg_secondary'],
                               corner_radius=4)
            row.pack(fill='x', padx=6, pady=1)

            var = ctk.BooleanVar(value=False)
            self._checkboxes[r['id']] = var
            ctk.CTkCheckBox(row, text='', variable=var, width=20).pack(side='left', padx=8, pady=6)

            for val, width in [(r['name'],320),(r['kind'],160),(r['owner'],130),
                               (r['deleted'],150),(r['folder'],200)]:
                ctk.CTkLabel(row, text=str(val)[:55], width=width, anchor='w',
                             font=('Segoe UI', 10), text_color=C['text_primary']
                             ).pack(side='left', padx=4, pady=6)

    def _restore_selected(self):
        # SAP BO doesn't have a direct REST restore — show info
        selected = [oid for oid, var in self._checkboxes.items() if var.get()]
        self._status.configure(
            text=f'ℹ  Restore {len(selected)} object(s) via CMC → Recycle Bin → Restore'
        )

    def _purge_selected(self):
        ids = [oid for oid, var in self._checkboxes.items() if var.get()]
        if not ids:
            self._status.configure(text='⚠ Select items first'); return
        self._status.configure(text=f'Purging {len(ids)} object(s)…')
        threading.Thread(target=self._do_purge, args=(ids,), daemon=True).start()

    def _do_purge(self, ids):
        ok = err = 0
        for oid in ids:
            try:
                success, _ = bo_session.delete_object(oid)
                if success: ok += 1
                else: err += 1
            except Exception:
                err += 1
        self.after(0, lambda: self._status.configure(
            text=f'Purged {ok} ✅  |  Failed {err} ❌'))
        self.after(800, self._load)
