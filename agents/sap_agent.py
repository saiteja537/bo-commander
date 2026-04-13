"""
agents/sap_agent.py  —  SAP BO REST API Agent  v2.0
=====================================================
Handles all SAP BusinessObjects operations via REST API + Java SDK bridge:
  • Users  (list, create, disable, reset password, delete)
  • Reports (list, schedule, delete, open in browser)
  • Instances (list failed, retry, purge)
  • Servers (list status, start/stop/restart via Java SDK)
  • Universes / Connections
  • Folders / Repository
"""

import logging
import re
import webbrowser
from typing import Callable
from urllib.parse import urlparse

from agents.base_agent import BaseAgent, AgentResult
from core.sapbo_connection import bo_session

logger = logging.getLogger("SAPAgent")

SAP_INTENTS = {
    "list_reports", "open_report", "schedule_report", "delete_report",
    "list_users", "create_user", "disable_user", "reset_password",
    "list_servers", "start_server", "stop_server", "restart_server",
    "failed_instances", "retry_failed", "purge_instances",
    "list_universes", "check_db", "list_folders",
    "bo_health", "health",
}


class SAPAgent(BaseAgent):
    name = "SAPAgent"
    description = "Manages SAP BusinessObjects via REST API + Java Admin SDK"

    def can_handle(self, intent: dict) -> bool:
        return intent.get("action") in SAP_INTENTS

    def execute(self, intent: dict, emit: Callable[[str], None]) -> AgentResult:
        action = intent.get("action", "")
        param  = intent.get("param") or ""
        raw    = intent.get("raw", "")

        if not bo_session.connected:
            emit("❌  Not connected to SAP BO. Please login first.")
            return AgentResult(False, "Not connected", action=action)

        handlers = {
            "list_reports":     self._list_reports,
            "open_report":      self._open_report,
            "schedule_report":  self._schedule_report,
            "delete_report":    self._delete_report,
            "list_users":       self._list_users,
            "create_user":      self._create_user,
            "disable_user":     self._disable_user,
            "reset_password":   self._reset_password,
            "list_servers":     self._list_servers,
            "start_server":     self._server_control,
            "stop_server":      self._server_control,
            "restart_server":   self._server_control,
            "failed_instances": self._failed_instances,
            "retry_failed":     self._retry_failed,
            "purge_instances":  self._purge_instances,
            "list_universes":   self._list_universes,
            "check_db":         self._check_db,
            "list_folders":     self._list_folders,
            "health":           self._bo_health,
            "bo_health":        self._bo_health,
        }

        handler = handlers.get(action)
        if not handler:
            return AgentResult(False, f"No handler for {action}", action=action)
        return handler(intent, emit)

    # ── Reports ───────────────────────────────────────────────────────────────

    def _list_reports(self, intent, emit):
        emit("📊  Fetching reports from SAP BO…")
        try:
            reports = bo_session.get_all_reports_typed(limit=500) or []
            webi  = sum(1 for r in reports if r.get("kind") == "Webi")
            cryst = sum(1 for r in reports if r.get("kind") == "CrystalReport")
            emit(f"📊  {len(reports)} reports found  (WebI: {webi}  Crystal: {cryst})\n")
            for r in reports[:30]:
                icon = {"Webi": "📊", "CrystalReport": "💎", "Excel": "📗"}.get(r.get("kind",""), "📄")
                emit(f"  {icon}  ID:{str(r.get('id','?')):<8}  {r.get('name','')[:50]:<52}"
                     f"  Owner: {r.get('owner','')}")
            if len(reports) > 30:
                emit(f"\n  … {len(reports)-30} more. Open Reports tab for full list.")
            return AgentResult(True, f"{len(reports)} reports", data=reports, action="list_reports")
        except Exception as e:
            emit(f"❌  {e}")
            return AgentResult(False, str(e), action="list_reports")

    def _open_report(self, intent, emit):
        report_name = intent.get("param") or ""
        emit(f"🔍  Searching for report: '{report_name}'…")
        try:
            reports = bo_session.get_all_reports_typed(limit=500) or []
            name_lower = report_name.lower().strip()
            matches = [r for r in reports if name_lower in r.get("name","").lower()]
            if not matches:
                names = [r.get("name","") for r in reports[:15]]
                emit(f"❌  No report matching '{report_name}'.\nAvailable:\n" +
                     "\n".join(f"  • {n}" for n in names))
                return AgentResult(False, "Not found", action="open_report")

            best = next((r for r in matches if r.get("name","").lower() == name_lower), matches[0])
            rid  = best.get("id","")
            host = bo_session.cms_details.get("host","localhost")
            url  = f"http://{host}:8080/BOE/BI?startDocument={rid}&sType=rpt&sDocName="
            webbrowser.open(url)
            emit(f"✅  Opening '{best.get('name','')}' (ID: {rid})\n🌐  {url}")
            return AgentResult(True, f"Opened {best.get('name','')}", action="open_report",
                               data={"url": url, "id": rid})
        except Exception as e:
            emit(f"❌  {e}")
            return AgentResult(False, str(e), action="open_report")

    def _schedule_report(self, intent, emit):
        rid = intent.get("param") or ""
        emit(f"📅  Scheduling report ID {rid}…")
        try:
            ok = bo_session.refresh_report(rid)
            if ok:
                emit(f"✅  Report {rid} scheduled successfully.")
                return AgentResult(True, "Scheduled", action="schedule_report")
            emit("⚠  Schedule request sent (check BO for status).")
            return AgentResult(True, "Scheduled (unverified)", action="schedule_report")
        except Exception as e:
            emit(f"❌  {e}")
            return AgentResult(False, str(e), action="schedule_report")

    def _delete_report(self, intent, emit):
        rid = intent.get("param") or ""
        emit(f"🗑  Deleting report ID {rid}…")
        try:
            ok, msg = bo_session.delete_report(rid)
            emit(f"{'✅' if ok else '❌'}  {msg}")
            return AgentResult(ok, msg, action="delete_report")
        except Exception as e:
            emit(f"❌  {e}")
            return AgentResult(False, str(e), action="delete_report")

    # ── Users ─────────────────────────────────────────────────────────────────

    def _list_users(self, intent, emit):
        emit("👥  Fetching users…")
        try:
            users = bo_session.get_users_detailed() or []
            active   = sum(1 for u in users if not u.get("disabled"))
            disabled = len(users) - active
            emit(f"👥  {len(users)} users  (🟢 {active} active  🔴 {disabled} disabled)\n")
            for u in users[:25]:
                s = "🔴" if u.get("disabled") else "🟢"
                emit(f"  {s}  {u.get('name',''):<30}  Last login: {str(u.get('last_login',''))[:16]}")
            if len(users) > 25:
                emit(f"\n  … {len(users)-25} more. Open Users tab for full list.")
            return AgentResult(True, f"{len(users)} users", data=users, action="list_users")
        except Exception as e:
            emit(f"❌  {e}")
            return AgentResult(False, str(e), action="list_users")

    def _create_user(self, intent, emit):
        emit("⚠  User creation requires username and password. Use the Users tab → New User.")
        return AgentResult(False, "Redirect to UI", action="create_user")

    def _disable_user(self, intent, emit):
        uid = intent.get("param") or ""
        emit(f"🔒  Disabling user {uid}…")
        try:
            ok, msg = bo_session.disable_user(uid, disabled=True)
            emit(f"{'✅' if ok else '❌'}  {msg}")
            return AgentResult(ok, msg, action="disable_user")
        except Exception as e:
            emit(f"❌  {e}")
            return AgentResult(False, str(e), action="disable_user")

    def _reset_password(self, intent, emit):
        emit("⚠  Password reset requires the Users tab → right-click user → Reset Password.")
        return AgentResult(False, "Redirect to UI", action="reset_password")

    # ── Servers ───────────────────────────────────────────────────────────────

    def _list_servers(self, intent, emit):
        emit("🖥  Fetching BO server list…")
        try:
            # Try Java SDK first for richer data
            from bridges.java_admin_sdk import java_sdk
            if java_sdk.is_available():
                ok, servers = java_sdk.list_servers()
                if ok and servers:
                    running = sum(1 for s in servers if s.get("alive"))
                    emit(f"🖥  {len(servers)} servers  (Java SDK)  🟢 {running} running\n")
                    for s in servers:
                        icon = "🟢" if s.get("alive") else "🔴"
                        emit(f"  {icon}  ID:{str(s.get('id','')):<8}  {s.get('name',''):<55}"
                             f"  Failures: {s.get('failures',0)}")
                    return AgentResult(True, f"{len(servers)} servers (Java)", data=servers,
                                       action="list_servers")

            # Fallback: REST API
            servers = bo_session.get_all_servers() or []
            running = sum(1 for s in servers if s.get("status") == "Running")
            emit(f"🖥  {len(servers)} servers  (REST API)  🟢 {running} running\n")
            for s in servers:
                icon = "🟢" if s.get("status") == "Running" else "🔴"
                fail = s.get("failures", 0) or 0
                emit(f"  {icon}  {s.get('name',''):<55}  Failures: {fail}")
            return AgentResult(True, f"{len(servers)} servers", data=servers,
                               action="list_servers")
        except Exception as e:
            emit(f"❌  {e}")
            return AgentResult(False, str(e), action="list_servers")

    def _server_control(self, intent, emit):
        action    = intent.get("action", "restart_server")
        server_id = intent.get("param") or intent.get("server_id") or ""
        op        = action.split("_")[0]  # start / stop / restart

        if not server_id:
            emit(f"⚠  Server ID required. Use 'list servers' to find IDs, then:\n"
                 f"   '{op} server <ID>'")
            return AgentResult(False, "No server ID", action=action)

        emit(f"🔄  {op.capitalize()} server {server_id} via Java Admin SDK…")
        try:
            from bridges.java_admin_sdk import java_sdk
            if java_sdk.is_available():
                fn = {"start": java_sdk.start_server,
                      "stop":  java_sdk.stop_server,
                      "restart": java_sdk.restart_server}[op]
                ok, msg = fn(server_id)
                emit(msg)
                return AgentResult(ok, msg, action=action)
            else:
                # Windows service fallback
                emit(java_sdk.availability_message())
                emit(f"\n🔄  Trying Windows service fallback…")
                ok, msg = java_sdk.windows_service_restart()
                emit(msg)
                cmc = java_sdk.get_cmс_url()
                emit(f"\n💡  For full server control, open CMC:\n  {cmc}")
                return AgentResult(ok, msg, action=action)
        except Exception as e:
            emit(f"❌  {e}")
            return AgentResult(False, str(e), action=action)

    # ── Instances ─────────────────────────────────────────────────────────────

    def _failed_instances(self, intent, emit):
        emit("🔍  Checking for failed report instances…")
        instances = []
        try:
            instances = bo_session.get_instances(status="failed", limit=100) or []
        except Exception as e1:
            emit(f"⚠  Primary query failed: {str(e1)[:60]}  — trying fallback…")
            try:
                q = ("SELECT TOP 100 SI_ID, SI_NAME, SI_KIND, SI_OWNER, "
                     "SI_STATUS, SI_STARTTIME "
                     "FROM CI_INFOOBJECTS WHERE SI_INSTANCE = 1 "
                     "ORDER BY SI_STARTTIME DESC")
                d = bo_session.run_cms_query(q)
                if d and d.get("entries"):
                    instances = [
                        {"id": e.get("SI_ID"), "name": e.get("SI_NAME",""),
                         "owner": e.get("SI_OWNER",""), "status": "Failed",
                         "start_time": e.get("SI_STARTTIME","")}
                        for e in d["entries"] if str(e.get("SI_STATUS","")) == "1"
                    ]
            except Exception as e2:
                emit(f"❌  Both queries failed: {e2}")
                return AgentResult(False, str(e2), action="failed_instances")

        if not instances:
            emit("✅  No failed instances found. All schedules healthy! 🎉")
            return AgentResult(True, "No failures", action="failed_instances")

        emit(f"\n⚠  {len(instances)} failed instance(s):\n")
        for inst in instances[:25]:
            emit(f"  ❌  {inst.get('name','')[:50]:<52}  Owner: {inst.get('owner',''):<20}"
                 f"  {str(inst.get('start_time',''))[:16]}")
        if len(instances) > 25:
            emit(f"\n  … {len(instances)-25} more.")
        emit("\n💡  Type 'retry failed' to reschedule all.")
        return AgentResult(True, f"{len(instances)} failed", data=instances,
                           action="failed_instances")

    def _retry_failed(self, intent, emit):
        emit("🔁  Retrying all failed report schedules…")
        try:
            count, msg = bo_session.reschedule_failed_instances()
            emit(f"✅  {msg}")
            return AgentResult(True, msg, action="retry_failed")
        except Exception as e:
            emit(f"❌  {e}")
            return AgentResult(False, str(e), action="retry_failed")

    def _purge_instances(self, intent, emit):
        days = 30
        m = re.search(r"\b(\d+)\s*days?\b", intent.get("raw",""), re.I)
        if m:
            days = int(m.group(1))
        emit(f"🗑  Purging instances older than {days} days…")
        try:
            count, msg = bo_session.purge_old_instances(days=days)
            emit(f"✅  {msg}")
            return AgentResult(True, msg, action="purge_instances")
        except Exception as e:
            emit(f"❌  {e}")
            return AgentResult(False, str(e), action="purge_instances")

    # ── Misc ──────────────────────────────────────────────────────────────────

    def _list_universes(self, intent, emit):
        emit("🌐  Fetching universes…")
        try:
            univs = bo_session.get_all_universes(limit=100) or []
            emit(f"🌐  {len(univs)} universes\n")
            for u in univs[:20]:
                emit(f"  🌐  {u.get('name',''):<50}  Type: {u.get('type','')}")
            return AgentResult(True, f"{len(univs)} universes", data=univs,
                               action="list_universes")
        except Exception as e:
            emit(f"❌  {e}")
            return AgentResult(False, str(e), action="list_universes")

    def _check_db(self, intent, emit):
        emit("🗄  Fetching BO connections…")
        try:
            conns = bo_session.get_all_connections(limit=30) or []
            emit(f"🗄  {len(conns)} connection(s) in repository:\n")
            for c in conns:
                emit(f"  📡  {c.get('name',''):<40}  Server: {c.get('server','')}")
            emit("\n💡  Test a connection in CMC → Connections → Test Connection.")
            return AgentResult(True, f"{len(conns)} connections", data=conns, action="check_db")
        except Exception as e:
            emit(f"❌  {e}")
            return AgentResult(False, str(e), action="check_db")

    def _list_folders(self, intent, emit):
        emit("📁  Fetching root folders…")
        try:
            folders = bo_session.get_root_folders() or []
            emit(f"📁  {len(folders)} root folders:\n")
            for f in folders[:20]:
                emit(f"  📁  ID:{str(f.get('id','')):<8}  {f.get('name','')}")
            return AgentResult(True, f"{len(folders)} folders", data=folders, action="list_folders")
        except Exception as e:
            emit(f"❌  {e}")
            return AgentResult(False, str(e), action="list_folders")

    def _bo_health(self, intent, emit):
        emit("🏥  SAP BO Health Check…\n")
        host = bo_session.cms_details.get("host","localhost")
        import socket

        def port_check(p):
            try:
                s = socket.create_connection((host, p), timeout=3)
                s.close()
                return "🟢 Open"
            except Exception:
                return "🔴 Closed"

        emit(f"Connection:  {'🟢 Connected' if bo_session.connected else '🔴 Disconnected'}"
             f"  ({bo_session.cms_details.get('user','')}@{host})")
        emit(f"Port 6405:   {port_check(6405)}  (WACS/REST)")
        emit(f"Port 8080:   {port_check(8080)}  (Tomcat/CMC)")

        try:
            servers = bo_session.get_all_servers() or []
            running = sum(1 for s in servers if s.get("status") == "Running")
            s_icon  = "🟢" if running == len(servers) and servers else "🟡" if running > 0 else "🔴"
            emit(f"Servers:     {s_icon} {running}/{len(servers)} running")
        except Exception as e:
            emit(f"Servers:     ⚠  {e}")

        try:
            users = bo_session.get_users_detailed() or []
            emit(f"Users:       👥 {len(users)}")
        except Exception:
            pass

        return AgentResult(True, "BO health checked", action="bo_health")
