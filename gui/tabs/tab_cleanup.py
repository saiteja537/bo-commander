"""
gui/tabs/tab_cleanup.py  —  Housekeeping & Cleanup
Real automation cards with dry-run preview then execute.
All operations are real REST calls via bo_session.
"""
from gui.tabs._base import *


# ── Housekeeping task definition ─────────────────────────────────────────────
TASKS = [
    {
        "key":     "purge_old",
        "icon":    "🗓",
        "title":   "Purge Old Instances",
        "desc":    "Delete report instances older than N days to free CMS storage.",
        "color":   AMBER,
        "scan_fn": lambda d: ("purge_old_instances", {"days": d}, f"instances older than {d} days"),
        "has_days": True,
    },
    {
        "key":     "retry_failed",
        "icon":    "🔄",
        "title":   "Retry Failed Schedules",
        "desc":    "Automatically retry all failed report instances.",
        "color":   BLUE,
        "scan_fn": lambda d: ("reschedule_failed_instances", {}, "failed instances"),
        "has_days": False,
    },
    {
        "key":     "orphan_instances",
        "icon":    "👻",
        "title":   "Delete Orphan Instances",
        "desc":    "Remove instances with no parent report (broken links in CMS).",
        "color":   VIOLET,
        "scan_fn": lambda d: ("_cleanup_orphan_instances", {"days": d}, f"orphan instances older than {d} days"),
        "has_days": True,
    },
    {
        "key":     "empty_bin",
        "icon":    "🗑",
        "title":   "Empty Recycle Bin",
        "desc":    "Permanently delete all items currently in the recycle bin.",
        "color":   RED,
        "scan_fn": lambda d: ("empty_recycle_bin", {}, "recycle bin items"),
        "has_days": False,
    },
    {
        "key":     "broken_objects",
        "icon":    "💔",
        "title":   "Remove Broken Objects",
        "desc":    "Find and delete CMS objects with broken or missing references.",
        "color":   RED,
        "scan_fn": lambda d: ("_cleanup_broken_objects", {}, "broken objects"),
        "has_days": False,
    },
]


class CleanupTab(BaseTab):

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._log_lines: list[str] = []
        self._days_vars: dict = {}
        self._build()

    def _build(self):
        self._page_header("Housekeeping & Cleanup", "🧹",
                           "Automated CMS maintenance — dry-run first, then execute")

        body = self._body
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=0)
        body.grid_rowconfigure(1, weight=1)

        # ── Task cards grid ───────────────────────────────────────────────────
        cards_frame = ctk.CTkFrame(body, fg_color="transparent")
        cards_frame.grid(row=0, column=0, sticky="nsew", padx=(14, 4), pady=10)
        for col in range(2):
            cards_frame.grid_columnconfigure(col, weight=1)

        self._cards = {}
        for i, task in enumerate(TASKS):
            row, col = divmod(i, 2)
            card = self._make_task_card(cards_frame, task)
            card.grid(row=row, column=col, padx=4, pady=4, sticky="ew")
            self._cards[task["key"]] = card

        # ── Execution log ─────────────────────────────────────────────────────
        log_frame = ctk.CTkFrame(body, fg_color=BG1, corner_radius=10)
        log_frame.grid(row=0, column=1, rowspan=2, sticky="nsew",
                       padx=(4, 14), pady=10)
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(log_frame, fg_color=BG2, corner_radius=8)
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))
        ctk.CTkLabel(hdr, text="📋  Execution Log",
                     font=F_H3, text_color=CYAN).pack(side="left", padx=10, pady=6)
        ctk.CTkButton(hdr, text="🗑 Clear", width=70, height=24,
                      fg_color=BG1, text_color=TEXT2, font=F_XS,
                      command=self._clear_log).pack(side="right", padx=8)

        self._log = ctk.CTkTextbox(log_frame, fg_color=BG0,
                                    text_color=TEAL, font=F_MONO, wrap="word")
        self._log.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self._log.configure(state="disabled")

        self._log_write("🧹  BO Commander Housekeeping Ready")
        self._log_write("──────────────────────────────")
        self._log_write("Run a dry-scan first, then execute.")
        self._log_write("")

    def _make_task_card(self, parent, task):
        card = ctk.CTkFrame(parent, fg_color=BG1, corner_radius=10,
                             border_color=task["color"], border_width=1)
        strip = ctk.CTkFrame(card, fg_color=task["color"], height=3, corner_radius=0)
        strip.pack(fill="x")

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=8)

        ctk.CTkLabel(inner, text=f"{task['icon']}  {task['title']}",
                     font=F_H3, text_color=task["color"]).pack(anchor="w")
        ctk.CTkLabel(inner, text=task["desc"], font=F_XS,
                     text_color=TEXT2, wraplength=260, justify="left").pack(anchor="w", pady=(2, 6))

        if task.get("has_days"):
            days_row = ctk.CTkFrame(inner, fg_color="transparent")
            days_row.pack(fill="x", pady=(0, 4))
            ctk.CTkLabel(days_row, text="Older than:", font=F_XS,
                         text_color=TEXT2).pack(side="left")
            var = ctk.StringVar(value="30")
            self._days_vars[task["key"]] = var
            ctk.CTkOptionMenu(days_row, variable=var,
                               values=["7","14","30","60","90","180"],
                               width=80, height=26,
                               fg_color=BG2, button_color=BG2,
                               dropdown_fg_color=BG1, text_color=TEXT,
                               font=F_XS).pack(side="left", padx=6)
            ctk.CTkLabel(days_row, text="days", font=F_XS, text_color=TEXT2).pack(side="left")

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x")
        ctk.CTkButton(btn_row, text="🔍 Dry Scan", width=100, height=28,
                      corner_radius=6, font=F_XS,
                      fg_color=BG2, hover_color=task["color"],
                      text_color=TEXT,
                      command=lambda t=task: self._dry_scan(t)).pack(side="left", padx=(0, 4))
        ctk.CTkButton(btn_row, text="▶ Execute", width=90, height=28,
                      corner_radius=6, font=F_XS,
                      fg_color=task["color"], hover_color=BG2,
                      text_color="white" if task["color"] != AMBER else BG0,
                      command=lambda t=task: self._execute_task(t)).pack(side="left")

        return card

    # ── Dry scan ──────────────────────────────────────────────────────────────
    def _dry_scan(self, task):
        days = int(self._days_vars.get(task["key"], ctk.StringVar(value="30")).get())
        self._log_write(f"\n🔍 [{task['title']}] Dry scan (days={days})…")
        self.set_status(f"⏳ Scanning: {task['title']}…", AMBER)

        def _run():
            key = task["key"]
            try:
                if key == "purge_old":
                    items = bo_session.get_instances_deep(days_back=days)
                    old   = [i for i in items if i.get("status") != "Running"]
                    return f"Would delete {len(old)} instance(s) older than {days} days"
                elif key == "retry_failed":
                    fails = bo_session.get_instances(status="failed", limit=200) or []
                    return f"Would retry {len(fails)} failed instance(s)"
                elif key == "orphan_instances":
                    orphs = bo_session.find_orphan_instances(days=days) or []
                    return f"Would delete {len(orphs)} orphan instance(s)"
                elif key == "empty_bin":
                    items = bo_session.get_recycle_bin_items() or []
                    return f"Would permanently delete {len(items)} recycle bin item(s)"
                elif key == "broken_objects":
                    broken = bo_session.get_broken_objects() or []
                    return f"Would delete {len(broken)} broken object(s)"
            except Exception as e:
                return f"Scan error: {e}"
            return "No data"

        bg(_run, lambda r: (
            self._log_write(f"  📋 Result: {r}"),
            self.set_status(f"🔍 {task['title']}: {r}", BLUE)
        ), self)

    # ── Execute ───────────────────────────────────────────────────────────────
    def _execute_task(self, task):
        days = int(self._days_vars.get(task["key"], ctk.StringVar(value="30")).get())
        if not confirm(f"Execute: {task['title']}",
                       f"{task['desc']}\n\nThis CANNOT be undone. Proceed?",
                       parent=self):
            return

        self._log_write(f"\n▶ [{task['title']}] Executing (days={days})…")
        self.set_status(f"⏳ Executing: {task['title']}…", AMBER)

        key = task["key"]

        def _run():
            try:
                if key == "purge_old":
                    return bo_session.purge_old_instances(days)
                elif key == "retry_failed":
                    return bo_session.reschedule_failed_instances()
                elif key == "orphan_instances":
                    orphs = bo_session.find_orphan_instances(days=days, limit=200) or []
                    ids   = [str(o.get("id","")) for o in orphs if o.get("id")]
                    return bo_session.bulk_delete_instances(ids)
                elif key == "empty_bin":
                    return bo_session.empty_recycle_bin()
                elif key == "broken_objects":
                    broken = bo_session.get_broken_objects(limit=200) or []
                    ok = err = 0
                    for b in broken:
                        r, _ = bo_session.delete_object(str(b.get("id","")))
                        if r: ok += 1
                        else: err += 1
                    return (ok, err)
            except Exception as e:
                return (False, str(e))

        def _done(result):
            if isinstance(result, tuple) and len(result) == 2:
                a, b = result
                if isinstance(a, bool):
                    msg = f"✅ Done" if a else f"❌ Failed: {b}"
                    col = GREEN if a else RED
                else:
                    msg = f"✅ {a} succeeded  ❌ {b} errors"
                    col = GREEN if b == 0 else AMBER
            else:
                msg = f"✅ {result}"
                col = GREEN
            self._log_write(f"  {msg}")
            self.set_status(f"{task['icon']} {task['title']}: {msg}", col)

        bg(_run, _done, self)

    def _log_write(self, msg: str):
        import time
        ts  = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self._log.configure(state="normal")
        self._log.insert("end", line)
        self._log.configure(state="disabled")
        self._log.see("end")

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        self._log_write("🧹 Log cleared.")
