"""
=============================================================================
INTEGRATION INSTRUCTIONS — BO Commander Power Tools
=============================================================================

FILE PLACEMENT:
  gui/pages/sentinel.py          → REPLACE existing file
  gui/pages/instance_cleanup.py  → NEW file
  gui/pages/failed_schedules.py  → NEW file
  gui/pages/user_activity.py     → NEW file
  gui/pages/server_health.py     → NEW file
  gui/pages/broken_reports.py    → NEW file

=============================================================================
FIX 1 — sentinel.py: Pass agent from main_window.py
=============================================================================

In your main_window.py (or wherever pages are created), find where SentinelPage
is instantiated and add the agent= parameter:

  BEFORE (broken):
    page = SentinelPage(self.content_frame)

  AFTER (fixed):
    page = SentinelPage(self.content_frame, agent=self.sentinel_agent)

The sentinel_agent must be created ONCE in main_window.__init__:
    from ai.sentinel_agent import SentinelAgent
    self.sentinel_agent = SentinelAgent(ui_callback=None)

Then pass it to SentinelPage as shown above.

=============================================================================
FIX 2 — sapbo_connection.py: Replace scan_security_hotspots stub
=============================================================================

Find scan_security_hotspots() in core/sapbo_connection.py and REPLACE with:
"""

# ── Paste this into the SAPBOConnection class ─────────────────────────────────

SCAN_SECURITY_HOTSPOTS_IMPL = '''
    def scan_security_hotspots(self):
        """
        Scan for folders and reports where the Everyone group has excessive rights.
        Returns list of hotspot dicts: {id, name, path, type, risk, issue, group}
        """
        hotspots = []
        try:
            # Get all folders
            folders = self._query(
                "SELECT SI_ID, SI_NAME, SI_PATH "
                "FROM CI_INFOOBJECTS WHERE SI_KIND=\'Folder\' "
                "AND SI_ANCESTOR=23 ORDER BY SI_NAME"
            )
            for f in folders:
                fid = f.get(\'SI_ID\', 0)
                try:
                    acls = self._query(
                        f"SELECT SI_NAME, SI_PRINCIPALNAME FROM CI_APPOBJECTS "
                        f"WHERE SI_KIND=\'SecurityEntry\' AND SI_PARENTID={fid}"
                    )
                    for acl in acls:
                        pname = str(acl.get(\'SI_PRINCIPALNAME\', acl.get(\'SI_NAME\', \'\'))).lower()
                        if \'everyone\' in pname:
                            hotspots.append({
                                \'id\':    fid,
                                \'name\':  f.get(\'SI_NAME\', \'Unknown\'),
                                \'path\':  f.get(\'SI_PATH\', \'/\'),
                                \'type\':  \'Folder\',
                                \'risk\':  \'HIGH\',
                                \'issue\': "Everyone group has access",
                                \'group\': acl.get(\'SI_PRINCIPALNAME\', \'Everyone\'),
                            })
                except Exception:
                    pass

            # Get WebI reports (sample top 500)
            reports = self._query(
                "SELECT SI_ID, SI_NAME, SI_PATH "
                "FROM CI_INFOOBJECTS WHERE SI_KIND=\'Webi\' "
                "ORDER BY SI_ID DESC",
                limit=500
            )
            for r in reports:
                rid = r.get(\'SI_ID\', 0)
                try:
                    acls = self._query(
                        f"SELECT SI_NAME, SI_PRINCIPALNAME FROM CI_APPOBJECTS "
                        f"WHERE SI_KIND=\'SecurityEntry\' AND SI_PARENTID={rid}"
                    )
                    for acl in acls:
                        pname = str(acl.get(\'SI_PRINCIPALNAME\', acl.get(\'SI_NAME\', \'\'))).lower()
                        if \'everyone\' in pname:
                            hotspots.append({
                                \'id\':    rid,
                                \'name\':  r.get(\'SI_NAME\', \'Unknown\'),
                                \'path\':  r.get(\'SI_PATH\', \'/\'),
                                \'type\':  \'Report\',
                                \'risk\':  \'MEDIUM\',
                                \'issue\': "Everyone group has access",
                                \'group\': acl.get(\'SI_PRINCIPALNAME\', \'Everyone\'),
                            })
                except Exception:
                    pass

        except Exception as e:
            import logging
            logging.getLogger("SAPBOConnection").warning(f"scan_security_hotspots: {e}")

        return hotspots
'''

# =============================================================================
# FIX 3 — main_window.py: Register new Power Tool pages in sidebar
# =============================================================================

MAIN_WINDOW_ADDITIONS = """
In your main_window.py sidebar/navigation setup, add these entries
under the "POWER TOOLS" section:

  from gui.pages.instance_cleanup  import InstanceCleanupPage
  from gui.pages.failed_schedules  import FailedSchedulesPage
  from gui.pages.user_activity     import UserActivityPage
  from gui.pages.server_health     import ServerHealthPage
  from gui.pages.broken_reports    import BrokenReportsPage

  # In the page routing dict or page factory:
  "Instance Cleanup":   InstanceCleanupPage,
  "Failed Schedules":   FailedSchedulesPage,
  "User Activity":      UserActivityPage,
  "Server Health":      ServerHealthPage,
  "Broken Reports":     BrokenReportsPage,

  # In the sidebar items list (--- POWER TOOLS --- section):
  ("🗃️ Instance Cleanup",   "Instance Cleanup"),
  ("❌ Failed Schedules",   "Failed Schedules"),
  ("👤 User Activity",      "User Activity"),
  ("🖥️ Server Health",     "Server Health"),
  ("🔍 Broken Reports",    "Broken Reports"),
"""

# =============================================================================
# WHAT EACH TOOL DOES (Summary for README/docs)
# =============================================================================

FEATURE_SUMMARY = """
NEW POWER TOOLS:

1. 🗃️ Instance Cleanup Manager
   - Scan instances by age (7d / 30d / 90d / 1yr), status, owner
   - Preview before delete — see count + reclaimable disk space
   - Select individual or all, confirm before delete
   - Re-scans automatically after deletion
   - Prevents CMS DB bloat and FileStore fill

2. ❌ Failed Schedule Analyzer  
   - Shows all failed BO scheduled jobs instantly
   - Auto-detects root cause: DB error, auth fail, universe missing, timeout, etc.
   - Shows fix suggestion per failure
   - Pattern view: which reports fail most, which causes are most common
   - 1-click Retry + error log popup
   - Counters: total, today's failures, unique reports, repeat offenders

3. 👤 User Activity Tracker
   - Load all users with last login time
   - Configurable inactivity threshold (default 90 days)
   - Tabs: Inactive / Never Logged In / Most Active / All / License Report
   - License optimization report: shows how many licenses can be freed
   - Days-since-login color coding (red = >365, yellow = >90, green = <30)

4. 🖥️ Server Health Dashboard
   - All BO servers with status, failure count, connections, last start time
   - Color-coded: green=running, red=stopped, orange=zombie (>10 failures)
   - Per-server actions: Start / Stop / Restart / Detail popup
   - Start All / Restart All buttons
   - Auto-refresh every 30 seconds (toggle)
   - Zombie and overload detection badges

5. 🔍 Broken Report Detector
   - Scans all WebI and Crystal reports
   - Detects: missing universe, invalid connection, orphaned path, broken marker
   - Shows cause + fix suggestion per broken report
   - Filter tabs: All / Missing Universe / Bad Connection / Access / Other
   - Stat cards: total scanned, broken count, by category
"""

if __name__ == "__main__":
    print(FEATURE_SUMMARY)
