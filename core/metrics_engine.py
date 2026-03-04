import time
from collections import defaultdict, deque
from core.sapbo_connection import bo_session
from utils.notifications import send_alert


class MetricsEngine:
    """
    Stores metrics history, performs trend analysis,
    auto-remediation, and root-cause triggers.
    """

    def __init__(self, agent=None):
        self.agent = agent

        # Store last 60 minutes per server
        self.history = defaultdict(lambda: {
            "cpu": deque(maxlen=60),
            "ram": deque(maxlen=60),
            "timestamps": deque(maxlen=60)
        })

    # ================= STORE METRICS =================

    def record(self, server_id, cpu, ram):
        data = self.history[server_id]

        data["cpu"].append(cpu)
        data["ram"].append(ram)
        data["timestamps"].append(time.time())

        self.analyze(server_id)

    # ================= TREND ANALYSIS =================

    def analyze(self, server_id):
        data = self.history[server_id]

        if len(data["cpu"]) < 10:
            return  # need baseline

        avg_cpu = sum(data["cpu"]) / len(data["cpu"])
        avg_ram = sum(data["ram"]) / len(data["ram"])

        # 🔴 Sustained high CPU
        if avg_cpu > 85:
            send_alert("🔥 CPU Trend", f"Server {server_id} sustained high CPU")

            if self.agent:
                self.agent.investigate(
                    "SUSTAINED_HIGH_CPU",
                    {"server_id": server_id, "avg": avg_cpu}
                )

        # 🔴 Memory leak detection (increasing trend)
        if data["ram"][-1] - data["ram"][0] > 25:
            send_alert("🧠 Memory Leak Suspected",
                       f"Server {server_id} memory rising continuously")

            if self.agent:
                self.agent.investigate(
                    "MEMORY_LEAK",
                    {"server_id": server_id}
                )

        # 🔴 Critical RAM auto-remediation
        if data["ram"][-1] > 95:
            self.auto_remediate(server_id)

    # ================= AUTO REMEDIATION =================

    def auto_remediate(self, server_id):
        send_alert("⚙ Auto Remediation",
                   f"Restarting server {server_id} due to critical RAM")

        try:
            bo_session.restart_server(server_id)
        except Exception:
            pass