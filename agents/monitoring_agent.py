"""
agents/monitoring_agent.py  —  Monitoring + Self-Healing Agent  v2.0
=====================================================================
Runs continuously in background:
  • Every 60s: check all BO servers, ports, disk, RAM
  • Self-healing: restart stopped servers, alert on high disk
  • Event log: records every incident to memory/knowledge_base
  • On-demand: system health snapshot
"""

import logging
import os
import platform
import socket
import threading
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional

from agents.base_agent import BaseAgent, AgentResult
from config import Config

logger = logging.getLogger("MonitoringAgent")
IS_WIN = platform.system() == "Windows"

MONITOR_INTENTS = {"health", "monitor_status", "full_health", "analyse_slow",
                   "self_heal", "watch"}


class MonitoringAgent(BaseAgent):
    name        = "MonitoringAgent"
    description = "Continuous health monitoring + self-healing for SAP BO + OS"

    def __init__(self, emit_callback=None):
        super().__init__(emit_callback)
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event     = threading.Event()
        self._alerts: List[Dict] = []
        self._last_health: Dict  = {}
        self._interval = Config.MONITOR_CONFIG.get("interval", 60)
        self._auto_heal = False  # set True to enable self-healing

    # ── Public control ────────────────────────────────────────────────────────

    def start_monitoring(self, ui_emit: Callable[[str], None] = None,
                         auto_heal: bool = False):
        """Start the background monitoring loop."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._auto_heal = auto_heal
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, args=(ui_emit,), daemon=True
        )
        self._monitor_thread.start()
        logger.info(f"MonitoringAgent started (interval={self._interval}s, heal={auto_heal})")

    def stop_monitoring(self):
        self._stop_event.set()

    def can_handle(self, intent: dict) -> bool:
        return intent.get("action") in MONITOR_INTENTS

    def execute(self, intent: dict, emit: Callable[[str], None]) -> AgentResult:
        action = intent.get("action", "health")
        if action in ("health", "full_health", "monitor_status"):
            return self._full_health(intent, emit)
        if action == "analyse_slow":
            return self._analyse_slow(intent, emit)
        if action == "self_heal":
            return self._trigger_heal(intent, emit)
        return self._full_health(intent, emit)

    # ── Background monitor loop ───────────────────────────────────────────────

    def _monitor_loop(self, ui_emit: Optional[Callable]):
        while not self._stop_event.is_set():
            try:
                health = self._collect_health()
                self._last_health = health
                alerts = self._evaluate_health(health)

                for alert in alerts:
                    logger.warning(f"ALERT: {alert['message']}")
                    self._alerts.append(alert)
                    if len(self._alerts) > 200:
                        self._alerts.pop(0)

                    # Store in knowledge base
                    try:
                        from memory.knowledge_base import kb
                        kb.record_incident(alert["category"], alert["message"],
                                           severity=alert["severity"])
                    except Exception:
                        pass

                    # Self-healing actions
                    if self._auto_heal:
                        self._heal(alert, ui_emit)

            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

            self._stop_event.wait(self._interval)

    def _collect_health(self) -> Dict:
        h = {"ts": datetime.now().isoformat()}

        # CPU / RAM
        try:
            import psutil
            h["cpu"]  = psutil.cpu_percent(interval=1)
            vm        = psutil.virtual_memory()
            h["ram"]  = vm.percent
            h["ram_total_gb"] = vm.total // (1024**3)
            h["ram_used_gb"]  = vm.used  // (1024**3)
            disks = {}
            for dp in psutil.disk_partitions():
                try:
                    du = psutil.disk_usage(dp.mountpoint)
                    disks[dp.mountpoint] = {"pct": du.percent, "free_gb": du.free//(1024**3)}
                except Exception:
                    pass
            h["disks"] = disks
        except Exception:
            h["cpu"] = h["ram"] = 0

        # BO ports
        from core.sapbo_connection import bo_session
        host = bo_session.cms_details.get("host","localhost")
        h["host"] = host
        port_status = {}
        for port in [6405, 8080, 6400]:
            try:
                s = socket.create_connection((host, port), timeout=2)
                s.close()
                port_status[port] = True
            except Exception:
                port_status[port] = False
        h["ports"] = port_status

        # BO servers
        try:
            from core.sapbo_connection import bo_session
            if bo_session.connected:
                servers = bo_session.get_all_servers() or []
                h["servers_total"]   = len(servers)
                h["servers_running"] = sum(1 for s in servers if s.get("status") == "Running")
                h["servers_stopped"] = [s for s in servers if s.get("status") != "Running"]
            else:
                h["servers_total"] = h["servers_running"] = 0
                h["servers_stopped"] = []
        except Exception:
            h["servers_total"] = h["servers_running"] = 0

        # BO session validity
        try:
            from core.sapbo_connection import bo_session
            h["bo_connected"] = bo_session.connected
        except Exception:
            h["bo_connected"] = False

        return h

    def _evaluate_health(self, h: Dict) -> List[Dict]:
        alerts = []
        cfg    = Config.MONITOR_CONFIG

        def alert(cat, sev, msg):
            alerts.append({"category": cat, "severity": sev, "message": msg,
                            "ts": datetime.now().isoformat()})

        # CPU
        if h.get("cpu", 0) > cfg.get("cpu_threshold", 90):
            alert("cpu", "warning", f"High CPU: {h['cpu']}%")

        # RAM
        if h.get("ram", 0) > cfg.get("mem_threshold", 85):
            alert("memory", "warning", f"High RAM: {h['ram']}%")

        # Disk
        for mount, usage in h.get("disks", {}).items():
            if usage.get("pct", 0) > cfg.get("disk_threshold", 90):
                alert("disk", "critical", f"Disk {mount} at {usage['pct']}% ({usage['free_gb']} GB free)")

        # Ports
        for port, open_state in h.get("ports", {}).items():
            if not open_state:
                label = Config.BO_PORTS.get(port, str(port))
                alert("network", "critical", f"Port {port} CLOSED — {label}")

        # Servers
        for srv in h.get("servers_stopped", []):
            alert("server", "critical", f"BO Server stopped: {srv.get('name','?')}")

        return alerts

    def _heal(self, alert: Dict, ui_emit: Optional[Callable]):
        """Self-healing actions based on alert category."""
        cat = alert["category"]
        msg = alert["message"]
        healed = False

        try:
            if cat == "server" and IS_WIN:
                # Try to restart stopped BO server via Java SDK
                name = re.search(r"stopped: (.+)", msg)
                if name:
                    from bridges.java_admin_sdk import java_sdk
                    if java_sdk.is_available():
                        # Find server ID from name
                        ok, servers = java_sdk.list_servers()
                        if ok:
                            for s in servers:
                                if s.get("name","") in name.group(1):
                                    ok2, m2 = java_sdk.start_server(str(s["id"]))
                                    healed = ok2
                                    if ui_emit and ok2:
                                        ui_emit(f"🔧  Self-healed: {m2}")
            elif cat == "disk" and alert["severity"] == "critical":
                # Auto-purge if disk > 95%
                pct_m = re.search(r"(\d+)%", msg)
                if pct_m and int(pct_m.group(1)) > 95:
                    from core.sapbo_connection import bo_session
                    if bo_session.connected:
                        count, result = bo_session.purge_old_instances(days=7)
                        healed = count > 0
                        if ui_emit:
                            ui_emit(f"🔧  Self-healed disk: purged {count} instances")
        except Exception as e:
            logger.error(f"Self-heal error: {e}")

        if healed:
            try:
                from memory.knowledge_base import kb
                kb.record_remediation(cat, f"Auto-healed: {msg}")
            except Exception:
                pass

    # ── On-demand health check ────────────────────────────────────────────────

    def _full_health(self, intent, emit):
        emit("🏥  Full System Health Check…\n")
        h = self._collect_health()
        self._last_health = h

        from core.sapbo_connection import bo_session
        host = h.get("host","localhost")
        conn = "🟢 Connected" if h.get("bo_connected") else "🔴 Disconnected"
        emit(f"SAP BO:        {conn}  ({bo_session.cms_details.get('user','')}@{host})")

        for port, label in [(6405,"WACS/REST"), (8080,"Tomcat/CMC"), (6400,"CMS")]:
            icon = "🟢" if h.get("ports",{}).get(port) else "🔴"
            emit(f"Port {port}:    {icon}  {label}")

        cpu = h.get("cpu", "?")
        ram = h.get("ram", "?")
        ci  = "🟢" if isinstance(cpu,(int,float)) and cpu < 80 else "🟡" if cpu != "?" else "⚪"
        ri  = "🟢" if isinstance(ram,(int,float)) and ram < 80 else "🟡" if ram != "?" else "⚪"
        emit(f"CPU:           {ci} {cpu}%")
        emit(f"RAM:           {ri} {ram}%  "
             f"({h.get('ram_used_gb','?')}/{h.get('ram_total_gb','?')} GB)")

        for mount, usage in list(h.get("disks",{}).items())[:3]:
            pct  = usage.get("pct",0)
            icon = "🟢" if pct < 75 else "🟡" if pct < 90 else "🔴"
            emit(f"Disk {mount}:".ljust(15) + f"{icon} {pct}%  ({usage.get('free_gb','?')} GB free)")

        total   = h.get("servers_total",0)
        running = h.get("servers_running",0)
        s_icon  = "🟢" if running == total and total > 0 else "🟡" if running > 0 else "🔴"
        emit(f"BO Servers:    {s_icon} {running}/{total} running")

        stopped = h.get("servers_stopped",[])
        if stopped:
            emit(f"\n⚠  Stopped servers:")
            for s in stopped[:5]:
                emit(f"    🔴  {s.get('name','')}")

        # Recent alerts
        if self._alerts:
            emit(f"\n🚨  Recent alerts ({len(self._alerts)}):")
            for a in self._alerts[-5:]:
                emit(f"  [{a['severity'].upper()}] {a['message']}")

        # Monitor status
        running_bg = self._monitor_thread and self._monitor_thread.is_alive()
        emit(f"\n📡  Background monitor: {'🟢 Running' if running_bg else '🔴 Stopped'}"
             f"  (interval: {self._interval}s)")

        return AgentResult(True, "Health checked", data=h, action="health")

    def _analyse_slow(self, intent, emit):
        report_name = intent.get("param") or "report"
        emit(f"🔍  Performance analysis for: '{report_name}'\n")
        h = self._last_health or self._collect_health()

        cpu = h.get("cpu","?")
        ram = h.get("ram","?")
        emit(f"Server:  CPU {cpu}%  RAM {ram}%")

        issues = []
        if isinstance(cpu,(int,float)) and cpu > 75:
            issues.append(f"🔴 High CPU ({cpu}%) — BO processing may be throttled")
        if isinstance(ram,(int,float)) and ram > 80:
            issues.append(f"🔴 High RAM ({ram}%) — may be causing paging/swapping")
        if not h.get("ports",{}).get(6405):
            issues.append("🔴 WACS port 6405 closed — REST API calls will fail")

        if issues:
            emit("\n⚠  Detected issues:\n" + "\n".join(issues))
        else:
            emit("✅  Server resources look healthy.")

        emit("\n💡  Common slow report causes:\n"
             "  1. Heavy SQL in universe — add aggregate tables / filters\n"
             "  2. Too many rows — add report prompts to limit data\n"
             "  3. BO server overloaded — check Adaptive Processing Server in CMC\n"
             "  4. DB query plan — check SQL Server / Oracle execution plan\n"
             "  5. Old instances filling repository — run 'delete old instances'")

        return AgentResult(True, "Analysed", action="analyse_slow")

    def _trigger_heal(self, intent, emit):
        if not self._last_health:
            emit("⚠  No health data yet. Run 'system health' first.")
            return AgentResult(False, "No data", action="self_heal")
        alerts = self._evaluate_health(self._last_health)
        if not alerts:
            emit("✅  No issues detected. Nothing to heal.")
            return AgentResult(True, "No issues", action="self_heal")
        for alert in alerts:
            emit(f"🔧  Healing: [{alert['severity']}] {alert['message']}")
            self._heal(alert, emit)
        return AgentResult(True, f"{len(alerts)} issues processed", action="self_heal")

    def get_recent_alerts(self, n: int = 10) -> List[Dict]:
        return self._alerts[-n:]


import re  # needed by _heal
