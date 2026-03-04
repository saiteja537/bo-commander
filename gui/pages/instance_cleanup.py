"""
instance_cleanup.py — Instance Cleanup Manager
The #1 admin tool: deletes BO report instances by age/status/size/owner.
Prevents CMS database bloat, FileStore fill, and scheduling slowdowns.
"""
import threading
import customtkinter as ctk
from datetime import datetime, timedelta
from config import Config
from core.sapbo_connection import bo_session
import logging

logger = logging.getLogger("InstanceCleanup")

STATUS_OPTIONS = ['All', 'Success', 'Failed', 'Paused', 'Running', 'Recurring']
AGE_OPTIONS    = ['7 days', '30 days', '60 days', '90 days', '180 days', '1 year', 'Custom']
STATUS_COLORS  = {
    'success':   Config.COLORS['success'],
    'failed':    Config.COLORS['danger'],
    'running':   Config.COLORS['primary'],
    'paused':    Config.COLORS['warning'],
    'recurring': Config.COLORS['secondary'],
}


def _fmt_size(bytes_val):
    """Format bytes to human-readable string."""
    try:
        b = float(bytes_val or 0)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} PB"
    except Exception:
        return "N/A"


def _fmt_date(epoch_val):
    try:
        if not epoch_val or epoch_val == 0:
            return "N/A"
        return datetime.fromtimestamp(int(epoch_val)).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return str(epoch_val)


class InstanceCleanupPage(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=Config.COLORS['bg_primary'], **kwargs)
        self._destroyed = False
        self._instances  = []     # current scan results
        self._selected   = set()  # selected instance IDs
        self._build_ui()

    def _safe_after(self, ms, fn):
        if not self._destroyed:
            try:
                self.after(ms, fn)
            except Exception:
                pass

    def destroy(self):
        self._destroyed = True
        super().destroy()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=Config.COLORS['bg_secondary'])
        hdr.pack(fill='x', padx=15, pady=(15, 5))
        left = ctk.CTkFrame(hdr, fg_color='transparent')
        left.pack(side='left', padx=12, pady=8)
        ctk.CTkLabel(left, text="🗃️  Instance Cleanup Manager",
                     font=Config.FONTS['sub_header'],
                     text_color=Config.COLORS['text_primary']).pack(anchor='w')
        ctk.CTkLabel(left,
                     text="Delete old/failed report instances · Reclaim disk space · Prevent CMS bloat",
                     font=Config.FONTS['small'],
                     text_color=Config.COLORS['text_secondary']).pack(anchor='w')

        # ── Filters bar ───────────────────────────────────────────────────────
        filters = ctk.CTkFrame(self, fg_color=Config.COLORS['bg_secondary'])
        filters.pack(fill='x', padx=15, pady=(0, 5))

        # Age filter
        ctk.CTkLabel(filters, text="Older than:", font=Config.FONTS['small'],
                     text_color=Config.COLORS['text_secondary']).pack(side='left', padx=(12, 4), pady=8)
        self.age_var = ctk.StringVar(value='90 days')
        self.age_menu = ctk.CTkOptionMenu(filters, variable=self.age_var,
                                           values=AGE_OPTIONS, width=110,
                                           fg_color=Config.COLORS['bg_tertiary'],
                                           button_color=Config.COLORS['bg_tertiary'],
                                           dropdown_fg_color=Config.COLORS['bg_tertiary'])
        self.age_menu.pack(side='left', padx=4)

        # Status filter
        ctk.CTkLabel(filters, text="Status:", font=Config.FONTS['small'],
                     text_color=Config.COLORS['text_secondary']).pack(side='left', padx=(12, 4))
        self.status_var = ctk.StringVar(value='All')
        self.status_menu = ctk.CTkOptionMenu(filters, variable=self.status_var,
                                              values=STATUS_OPTIONS, width=100,
                                              fg_color=Config.COLORS['bg_tertiary'],
                                              button_color=Config.COLORS['bg_tertiary'],
                                              dropdown_fg_color=Config.COLORS['bg_tertiary'])
        self.status_menu.pack(side='left', padx=4)

        # Owner filter
        ctk.CTkLabel(filters, text="Owner:", font=Config.FONTS['small'],
                     text_color=Config.COLORS['text_secondary']).pack(side='left', padx=(12, 4))
        self.owner_entry = ctk.CTkEntry(filters, placeholder_text="Any", width=130)
        self.owner_entry.pack(side='left', padx=4)

        # Buttons
        ctk.CTkButton(filters, text="🔍 Scan", width=100,
                      fg_color=Config.COLORS['primary'],
                      command=self._scan).pack(side='left', padx=(16, 4), pady=6)
        ctk.CTkButton(filters, text="☑ Select All", width=100,
                      fg_color=Config.COLORS['bg_tertiary'],
                      command=self._select_all).pack(side='left', padx=4)
        ctk.CTkButton(filters, text="☐ Deselect All", width=110,
                      fg_color=Config.COLORS['bg_tertiary'],
                      command=self._deselect_all).pack(side='left', padx=4)

        # Delete button (right side)
        self.delete_btn = ctk.CTkButton(filters, text="🗑 Delete Selected", width=160,
                                         fg_color=Config.COLORS['danger'],
                                         state='disabled',
                                         command=self._confirm_delete)
        self.delete_btn.pack(side='right', padx=12)

        # ── Summary bar ───────────────────────────────────────────────────────
        self.summary_frame = ctk.CTkFrame(self, fg_color=Config.COLORS['bg_secondary'])
        self.summary_frame.pack(fill='x', padx=15, pady=(0, 5))

        self._stat_cards = {}
        for key, label in [('total', '📦 Total Found'), ('selected', '☑ Selected'),
                            ('size', '💾 Reclaimable'), ('failed', '❌ Failed')]:
            card = ctk.CTkFrame(self.summary_frame, fg_color=Config.COLORS['bg_tertiary'], width=170)
            card.pack(side='left', padx=6, pady=8, fill='y')
            card.pack_propagate(False)
            ctk.CTkLabel(card, text=label, font=Config.FONTS['small'],
                         text_color=Config.COLORS['text_secondary']).pack(pady=(6, 0))
            val_lbl = ctk.CTkLabel(card, text="—",
                                    font=('Segoe UI', 18, 'bold'),
                                    text_color=Config.COLORS['primary'])
            val_lbl.pack(pady=(0, 6))
            self._stat_cards[key] = val_lbl

        # ── Status label ─────────────────────────────────────────────────────
        self.status_lbl = ctk.CTkLabel(self, text="Configure filters and click Scan.",
                                        font=Config.FONTS['small'],
                                        text_color=Config.COLORS['text_secondary'])
        self.status_lbl.pack(anchor='w', padx=20, pady=(0, 4))

        # ── Column headers ────────────────────────────────────────────────────
        col_hdr = ctk.CTkFrame(self, fg_color=Config.COLORS['bg_tertiary'])
        col_hdr.pack(fill='x', padx=15, pady=(0, 1))
        ctk.CTkLabel(col_hdr, text="☐", width=30, anchor='center',
                     text_color=Config.COLORS['text_secondary']).pack(side='left', padx=5)
        for col, w in [("Report Name", 260), ("Status", 90), ("Owner", 120),
                        ("Created", 140), ("Size", 80), ("ID", 70)]:
            ctk.CTkLabel(col_hdr, text=col, width=w, anchor='w',
                         font=('Segoe UI', 11, 'bold'),
                         text_color=Config.COLORS['text_secondary']).pack(side='left', padx=3, pady=5)

        # ── Scrollable list ───────────────────────────────────────────────────
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=Config.COLORS['bg_secondary'])
        self.scroll.pack(fill='both', expand=True, padx=15, pady=(0, 15))

        ctk.CTkLabel(self.scroll, text="Configure filters above and click Scan to preview instances.",
                     text_color=Config.COLORS['text_secondary']).pack(pady=30)

    # ── Scan ──────────────────────────────────────────────────────────────────

    def _scan(self):
        if not bo_session.connected:
            self._set_status("⚠️  Not connected to BO server.")
            return
        self._set_status("⏳ Scanning instances...")
        self._selected.clear()
        self._update_delete_btn()
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        try:
            # Build query filters
            age_str = self.age_var.get()
            days_map = {'7 days': 7, '30 days': 30, '60 days': 60,
                        '90 days': 90, '180 days': 180, '1 year': 365}
            days = days_map.get(age_str, 90)
            cutoff_epoch = int((datetime.now() - timedelta(days=days)).timestamp())

            status_filter = self.status_var.get()
            owner_filter  = self.owner_entry.get().strip().lower()

            # SI_SCHEDULE_STATUS: 1=success, 3=failed, 8=paused, 0=running
            status_map = {'All': None, 'Success': 1, 'Failed': 3,
                          'Paused': 8, 'Running': 0, 'Recurring': None}

            # Query
            where_parts = ["SI_INSTANCE=1", f"SI_CREATION_TIME<{cutoff_epoch}"]
            st = status_map.get(status_filter)
            if st is not None:
                where_parts.append(f"SI_SCHEDULE_STATUS={st}")

            where_clause = " AND ".join(where_parts)
            query = (
                f"SELECT SI_ID, SI_NAME, SI_OWNERID, SI_OWNER, "
                f"SI_CREATION_TIME, SI_SCHEDULE_STATUS, "
                f"SI_FILES.SI_FILE_SIZE, SI_STATUSINFO "
                f"FROM CI_INFOOBJECTS WHERE {where_clause} "
                f"ORDER BY SI_CREATION_TIME"
            )

            rows = bo_session._query(query) if hasattr(bo_session, '_query') else []

            instances = []
            for r in rows:
                owner = str(r.get('SI_OWNER', r.get('SI_OWNERID', 'N/A'))).lower()
                if owner_filter and owner_filter not in owner:
                    continue
                st_code = r.get('SI_SCHEDULE_STATUS', -1)
                st_name = {1: 'Success', 3: 'Failed', 8: 'Paused',
                           0: 'Running'}.get(st_code, f'Status {st_code}')
                size = r.get('SI_FILES', {}).get('SI_FILE_SIZE', 0) if isinstance(r.get('SI_FILES'), dict) else 0
                instances.append({
                    'id':       r.get('SI_ID', 0),
                    'name':     r.get('SI_NAME', 'Unknown'),
                    'owner':    r.get('SI_OWNER', str(r.get('SI_OWNERID', 'N/A'))),
                    'created':  r.get('SI_CREATION_TIME', 0),
                    'status':   st_name,
                    'size':     int(size or 0),
                    'info':     r.get('SI_STATUSINFO', ''),
                })

            self._instances = instances
            self._safe_after(0, self._render_results)

        except Exception as e:
            logger.error(f"Instance scan error: {e}")
            self._instances = []
            self._safe_after(0, lambda: self._set_status(f"Scan error: {e}"))
            self._safe_after(0, self._render_results)

    # ── Render results ────────────────────────────────────────────────────────

    def _render_results(self):
        if self._destroyed:
            return
        try:
            if not self.scroll.winfo_exists():
                return
            for w in self.scroll.winfo_children():
                w.destroy()
        except Exception:
            return

        instances = self._instances
        total_size = sum(i['size'] for i in instances)
        failed_count = sum(1 for i in instances if 'failed' in i['status'].lower())

        # Update stat cards
        self._stat_cards['total'].configure(text=str(len(instances)))
        self._stat_cards['selected'].configure(text="0")
        self._stat_cards['size'].configure(text=_fmt_size(total_size))
        self._stat_cards['failed'].configure(text=str(failed_count),
                                              text_color=Config.COLORS['danger'] if failed_count else Config.COLORS['success'])

        self._set_status(
            f"✅ Found {len(instances)} instance(s). Reclaimable: {_fmt_size(total_size)}." if instances
            else "✅ No instances found matching filters. System is clean!"
        )

        if not instances:
            ctk.CTkLabel(self.scroll,
                         text="✅  No instances found matching the selected filters.\nSystem is clean!",
                         text_color=Config.COLORS['success'],
                         font=Config.FONTS['body']).pack(pady=40)
            return

        self._check_vars = {}
        for inst in instances:
            self._render_instance_row(inst)

    def _render_instance_row(self, inst):
        iid = inst['id']
        status_name = inst['status']
        sc = STATUS_COLORS.get(status_name.lower(), Config.COLORS['text_secondary'])

        row = ctk.CTkFrame(self.scroll, fg_color=Config.COLORS['bg_secondary'], height=38)
        row.pack(fill='x', pady=1)
        row.pack_propagate(False)

        var = ctk.BooleanVar(value=False)
        self._check_vars[iid] = var
        chk = ctk.CTkCheckBox(row, text="", variable=var, width=30,
                               checkbox_width=18, checkbox_height=18,
                               command=lambda i=iid, v=var: self._on_check(i, v))
        chk.pack(side='left', padx=5)

        ctk.CTkLabel(row, text=str(inst['name'])[:34], width=260, anchor='w',
                     text_color=Config.COLORS['text_primary']).pack(side='left', padx=3)
        ctk.CTkLabel(row, text=status_name, width=90, anchor='w',
                     text_color=sc, font=('Segoe UI', 11, 'bold')).pack(side='left', padx=3)
        ctk.CTkLabel(row, text=str(inst['owner'])[:16], width=120, anchor='w',
                     text_color=Config.COLORS['text_secondary']).pack(side='left', padx=3)
        ctk.CTkLabel(row, text=_fmt_date(inst['created']), width=140, anchor='w',
                     text_color=Config.COLORS['text_secondary']).pack(side='left', padx=3)
        ctk.CTkLabel(row, text=_fmt_size(inst['size']), width=80, anchor='w',
                     text_color=Config.COLORS['text_secondary']).pack(side='left', padx=3)
        ctk.CTkLabel(row, text=str(iid), width=70, anchor='w',
                     text_color=Config.COLORS['text_secondary']).pack(side='left', padx=3)

    def _on_check(self, iid, var):
        if var.get():
            self._selected.add(iid)
        else:
            self._selected.discard(iid)
        self._update_stats()
        self._update_delete_btn()

    def _update_stats(self):
        selected_instances = [i for i in self._instances if i['id'] in self._selected]
        selected_size = sum(i['size'] for i in selected_instances)
        try:
            self._stat_cards['selected'].configure(text=str(len(self._selected)))
            self._stat_cards['size'].configure(text=_fmt_size(
                sum(i['size'] for i in self._instances)
            ) + f" ({_fmt_size(selected_size)} selected)")
        except Exception:
            pass

    def _update_delete_btn(self):
        try:
            if self._selected:
                self.delete_btn.configure(
                    state='normal',
                    text=f"🗑 Delete {len(self._selected)} Selected"
                )
            else:
                self.delete_btn.configure(state='disabled', text="🗑 Delete Selected")
        except Exception:
            pass

    def _select_all(self):
        for iid, var in self._check_vars.items():
            var.set(True)
            self._selected.add(iid)
        self._update_stats()
        self._update_delete_btn()

    def _deselect_all(self):
        for iid, var in self._check_vars.items():
            var.set(False)
        self._selected.clear()
        self._update_stats()
        self._update_delete_btn()

    # ── Delete ────────────────────────────────────────────────────────────────

    def _confirm_delete(self):
        if not self._selected:
            return
        count = len(self._selected)
        selected_size = sum(i['size'] for i in self._instances if i['id'] in self._selected)

        # Confirm dialog
        dlg = ctk.CTkToplevel(self)
        dlg.title("Confirm Delete")
        dlg.geometry("480x220")
        dlg.grab_set()
        dlg.configure(fg_color=Config.COLORS['bg_primary'])

        ctk.CTkLabel(dlg, text="⚠️  Confirm Deletion",
                     font=('Segoe UI', 16, 'bold'),
                     text_color=Config.COLORS['danger']).pack(pady=(20, 6))
        ctk.CTkLabel(dlg,
                     text=f"You are about to permanently delete {count} instance(s).\n"
                          f"Reclaimable space: {_fmt_size(selected_size)}\n\n"
                          f"This CANNOT be undone. Proceed?",
                     font=Config.FONTS['body'],
                     text_color=Config.COLORS['text_primary'],
                     justify='center').pack(pady=6)

        btn_f = ctk.CTkFrame(dlg, fg_color='transparent')
        btn_f.pack(pady=16)
        ctk.CTkButton(btn_f, text="✅ Yes, Delete", width=150,
                      fg_color=Config.COLORS['danger'],
                      command=lambda: (dlg.destroy(), self._do_delete())).pack(side='left', padx=8)
        ctk.CTkButton(btn_f, text="Cancel", width=100,
                      fg_color=Config.COLORS['bg_tertiary'],
                      command=dlg.destroy).pack(side='left', padx=8)

    def _do_delete(self):
        ids_to_delete = list(self._selected)
        self._set_status(f"🗑 Deleting {len(ids_to_delete)} instances...")
        threading.Thread(target=self._delete_thread,
                          args=(ids_to_delete,), daemon=True).start()

    def _delete_thread(self, ids):
        deleted = 0
        errors  = 0
        for iid in ids:
            try:
                if hasattr(bo_session, 'delete_instance'):
                    bo_session.delete_instance(iid)
                elif hasattr(bo_session, '_delete_object'):
                    bo_session._delete_object(iid)
                else:
                    bo_session._query(
                        f"DELETE FROM CI_INFOOBJECTS WHERE SI_ID={iid} AND SI_INSTANCE=1"
                    )
                deleted += 1
            except Exception as e:
                logger.warning(f"Delete {iid} failed: {e}")
                errors += 1

        self._safe_after(0, lambda: self._set_status(
            f"✅ Deleted {deleted} instance(s). {f'⚠️ {errors} errors.' if errors else ''}"
        ))
        self._selected.clear()
        self._safe_after(200, self._scan)  # Re-scan after delete

    def _set_status(self, text):
        if not self._destroyed:
            try:
                self.status_lbl.configure(text=text)
            except Exception:
                pass
