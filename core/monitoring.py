import threading
import time
import psutil
from config import Config
from core.sapbo_connection import bo_session
from utils.notifications import send_alert
from core.metrics_engine import MetricsEngine


class SystemMonitor:
    """
    Central monitoring engine:
    - Resource monitoring (CPU/RAM)
    - Server status monitoring
    - Historical metrics collection
    - Trend analysis
    - Auto remediation triggers
    - Root-cause diagnostics
    """

    def __init__(self, sentinel_agent):
        self.is_running = False
        self.agent = sentinel_agent
        self.alert_cache = {}

        # 🔥 Historical + Trend Engine
        self.metrics = MetricsEngine(sentinel_agent)

    # ================= CONTROL =================

    def start(self):
        self.is_running = True
        threading.Thread(target=self.run, daemon=True).start()
        print("✅ System Monitor Active.")

    def stop(self):
        self.is_running = False

    # ================= MAIN LOOP =================

    def run(self):
        time.sleep(15)  # Warmup delay

        while self.is_running:
            if bo_session.is_connected():
                self.check_resources()
                self.check_servers()
                self.collect_server_metrics()  # 🔥 NEW

            time.sleep(60)  # every minute

    # =====================================================
    # RESOURCE MONITOR (PROCESS LEVEL)
    # =====================================================

    def check_resources(self):
        """Monitor BO processes for CPU and Memory issues."""

        MEM_WARN = 85.0
        MEM_CRITICAL = 95.0
        CPU_LIMIT = 90.0

        for p in psutil.process_iter(['name', 'memory_percent', 'cpu_percent']):
            try:
                if p.info['name'] in ['tomcat9.exe', 'javaw.exe', 'cms.exe']:

                    mem = p.info['memory_percent']
                    cpu = p.info['cpu_percent']
                    name = p.info['name']

                    # 🔴 CRITICAL MEMORY
                    if mem > MEM_CRITICAL and self.can_alert(f"crit_mem_{name}"):

                        msg = f"{name} at {mem:.1f}% memory (CRITICAL)"
                        send_alert("🔴 CRITICAL MEMORY", msg)

                        if self.agent:
                            self.agent.investigate(
                                "CRITICAL_MEMORY",
                                {"process": name, "value": mem}
                            )

                    # 🟠 HIGH MEMORY
                    elif mem > MEM_WARN and self.can_alert(f"mem_{name}"):

                        msg = f"{name} at {mem:.1f}% memory"
                        send_alert("🟠 High Memory", msg)

                        if self.agent:
                            self.agent.investigate(
                                "HIGH_MEMORY",
                                {"process": name, "value": mem}
                            )

                    # 🔴 HIGH CPU
                    if cpu > CPU_LIMIT and self.can_alert(f"cpu_{name}"):

                        msg = f"{name} at {cpu:.1f}% CPU"
                        send_alert("🔴 High CPU", msg)

                        if self.agent:
                            self.agent.investigate(
                                "HIGH_CPU",
                                {"process": name, "value": cpu}
                            )

            except Exception:
                pass

    # =====================================================
    # SERVER STATUS MONITOR
    # =====================================================

    def check_servers(self):
        """Check if any BO server is stopped unexpectedly."""

        try:
            servers = bo_session.get_all_servers()

            for s in servers:
                if s['status'] == "Stopped":

                    key = f"srv_{s['id']}"

                    if self.can_alert(key):

                        send_alert(
                            "🔴 Server Down",
                            f"{s['name']} has stopped unexpectedly."
                        )

                        # 🔥 Root-cause investigation trigger
                        if self.agent:
                            self.agent.investigate(
                                "SERVER_STOPPED",
                                {"name": s['name']}
                            )

        except Exception:
            pass

    # =====================================================
    # HISTORICAL METRICS COLLECTION
    # =====================================================

    def collect_server_metrics(self):
        """
        Collect CPU/RAM metrics for each BO server
        for historical storage + trend analysis.
        """

        try:
            servers = bo_session.get_all_servers()

            for s in servers:
                m = bo_session.get_server_metrics(s['id'])

                # 🔥 Store metrics for trends
                self.metrics.record(
                    s['id'],
                    m['cpu'],
                    m['ram']
                )

        except Exception:
            pass

    # =====================================================
    # ALERT SPAM CONTROL
    # =====================================================

    def can_alert(self, key):
        """Prevent alert spam (10 min cooldown per issue)."""

        now = time.time()

        if now - self.alert_cache.get(key, 0) > 600:
            self.alert_cache[key] = now
            return True

        return False