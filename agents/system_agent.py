"""
agents/system_agent.py  —  OS System Agent  v2.0
==================================================
Executes real OS-level operations:
  • Port probing (socket + netstat)
  • Disk usage (shutil + psutil)
  • Process / service checks
  • Service restart (sc stop/start on Windows, systemctl on Linux)
  • Log file reading (Tomcat + BO logs)
  • Cache clearing
  • Tomcat SSL configuration
  • Environment info
"""

import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Callable

from agents.base_agent import BaseAgent, AgentResult
from config import Config

logger = logging.getLogger("SystemAgent")
IS_WIN = platform.system() == "Windows"

SYSTEM_INTENTS = {
    "check_port", "disk_space", "read_log", "read_log_tomcat", "read_log_bo",
    "clear_cache", "restart_tomcat", "restart_service",
    "check_process", "system_info", "configure_ssl", "list_services",
    "check_network", "env_info",
}


class SystemAgent(BaseAgent):
    name = "SystemAgent"
    description = "Executes OS-level commands: ports, disk, logs, services, cache"

    def can_handle(self, intent: dict) -> bool:
        return intent.get("action") in SYSTEM_INTENTS

    def execute(self, intent: dict, emit: Callable[[str], None]) -> AgentResult:
        action = intent.get("action", "")
        param  = intent.get("param") or ""
        raw    = intent.get("raw", "")

        handlers = {
            "check_port":       self._check_port,
            "disk_space":       self._disk_space,
            "read_log":         self._read_log,
            "read_log_tomcat":  self._read_log_tomcat,
            "read_log_bo":      self._read_log_bo,
            "clear_cache":      self._clear_cache,
            "restart_tomcat":   self._restart_tomcat,
            "restart_service":  self._restart_service,
            "check_process":    self._check_process,
            "system_info":      self._system_info,
            "configure_ssl":    self._configure_ssl,
            "list_services":    self._list_services,
            "check_network":    self._check_network,
            "env_info":         self._env_info,
        }
        handler = handlers.get(action)
        if not handler:
            return AgentResult(False, f"No handler for {action}", action=action)
        return handler(intent, emit)

    # ── Port check ────────────────────────────────────────────────────────────

    def _check_port(self, intent, emit):
        try:
            port = int(intent.get("param") or re.search(r"\b(\d{2,5})\b",
                        intent.get("raw","")).group(1))
        except Exception:
            emit("⚠  Could not parse port number.")
            return AgentResult(False, "Bad port", action="check_port")

        from core.sapbo_connection import bo_session
        host = bo_session.cms_details.get("host","localhost")
        emit(f"🔌  Checking port {port} on {host}…")

        try:
            s = socket.create_connection((host, port), timeout=3)
            s.close()
            open_state = True
        except Exception as e:
            open_state = False
            reason = str(e)

        known = Config.BO_PORTS
        label = known.get(port, "")

        if open_state:
            emit(f"✅  Port {port} is OPEN  {('— ' + label) if label else ''}")
            if IS_WIN:
                out = _run_cmd(f"netstat -ano | findstr :{port}", timeout=6)
                if out and "[timeout" not in out:
                    emit(f"\n📡  Active connections on :{port}:\n{out[:500]}")
            else:
                out = _run_cmd(f"ss -tlnp | grep :{port}", timeout=6)
                if out:
                    emit(f"\n📡  {out[:300]}")
            return AgentResult(True, f"Port {port} open", action="check_port",
                               data={"port": port, "open": True})
        else:
            emit(f"❌  Port {port} is CLOSED  {('— ' + label) if label else ''}")
            emit(f"   Reason: {reason}")
            if port in known:
                emit(f"\n💡  {port} is used for: {known[port]}")
            return AgentResult(False, f"Port {port} closed", action="check_port",
                               data={"port": port, "open": False})

    # ── Disk space ────────────────────────────────────────────────────────────

    def _disk_space(self, intent, emit):
        emit("💽  Checking disk space…")
        bo_dir = Config.BOE_INSTALL_DIR
        results = {}

        for label, path in [("BO Install", bo_dir), ("C:\\", "C:\\"), ("D:\\", "D:\\")]:
            try:
                usage = shutil.disk_usage(path)
                total = usage.total // (1024**3)
                used  = usage.used  // (1024**3)
                free  = usage.free  // (1024**3)
                pct   = round(usage.used / usage.total * 100) if usage.total else 0
                icon  = "🟢" if pct < 75 else "🟡" if pct < 90 else "🔴"
                emit(f"  {icon}  {label:<15} {pct:>3}% used  "
                     f"{used:>5} / {total:>5} GB  ({free} GB free)")
                results[label] = {"pct": pct, "total_gb": total, "free_gb": free}
                if pct > 90:
                    emit(f"      ⚠  CRITICAL: {label} is {pct}% full!")
                    emit("      Suggested: 'delete old instances' to free space.")
            except Exception:
                pass

        # psutil if available
        try:
            import psutil
            vm = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=1)
            emit(f"\n  🖥  CPU:  {cpu}%  |  RAM: {vm.percent}%  "
                 f"({vm.used//(1024**3)}/{vm.total//(1024**3)} GB)")
        except Exception:
            pass

        return AgentResult(True, "Disk checked", data=results, action="disk_space")

    # ── Log reading ───────────────────────────────────────────────────────────

    def _read_log(self, intent, emit):
        name = intent.get("param") or "catalina"
        lines = 50
        m = re.search(r"\b(\d+)\s*lines?\b", intent.get("raw",""), re.I)
        if m:
            lines = min(int(m.group(1)), 500)
        emit(f"📋  Reading last {lines} lines of '{name}' log…")
        content = _read_log_tail(name, lines)
        emit(content[:4000])
        return AgentResult(True, "Log read", action="read_log")

    def _read_log_tomcat(self, intent, emit):
        emit("📋  Reading Tomcat catalina log…")
        lines = 50
        m = re.search(r"\b(\d+)\b", intent.get("raw",""))
        if m:
            lines = min(int(m.group(1)), 500)

        # Try Config-specified path first
        for log_path in [
            Config.BOE_TOMCAT_LOG,
            os.path.join(Config.BOE_TOMCAT_DIR, "catalina.out"),
            os.path.join(Config.BOE_TOMCAT_DIR, "catalina.log"),
        ]:
            if log_path and Path(log_path).exists():
                content = _tail_file(Path(log_path), lines)
                emit(f"📄  {log_path}  (last {lines} lines)\n{'─'*60}\n{content[:4000]}")
                _ai_analyse_log(content, emit)
                return AgentResult(True, "Tomcat log read", action="read_log_tomcat")

        # Fallback: search
        content = _read_log_tail("catalina", lines)
        emit(content[:4000])
        _ai_analyse_log(content, emit)
        return AgentResult(True, "Tomcat log read", action="read_log_tomcat")

    def _read_log_bo(self, intent, emit):
        emit("📋  Reading SAP BO log…")
        lines = 100
        # Try Config log dir
        log_dir = Path(Config.BOE_LOG_DIR)
        if log_dir.exists():
            logs = sorted(log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
            if logs:
                content = _tail_file(logs[0], lines)
                emit(f"📄  {logs[0].name}  (last {lines} lines)\n{'─'*60}\n{content[:4000]}")
                _ai_analyse_log(content, emit)
                return AgentResult(True, "BO log read", action="read_log_bo")
        emit("⚠  BO log directory not found. Check BOE_INSTALL_DIR in .env")
        return AgentResult(False, "Log not found", action="read_log_bo")

    # ── Cache clear ───────────────────────────────────────────────────────────

    def _clear_cache(self, intent, emit):
        emit("🧹  Clearing Tomcat cache…")
        tomcat_bin = Config.BOE_TOMCAT_BIN
        cleared = 0
        results = []

        # Check work/ temp/ in tomcat dir
        tomcat_parent = Path(Config.BOE_TOMCAT_DIR).parent  # tomcat/
        for sub in ["work", "temp"]:
            d = tomcat_parent / sub
            if d.exists():
                try:
                    count = sum(1 for _ in d.rglob("*") if _.is_file())
                    shutil.rmtree(str(d), ignore_errors=True)
                    d.mkdir(exist_ok=True)
                    results.append(f"✅  Cleared {sub}/  ({count} files)")
                    cleared += count
                except Exception as e:
                    results.append(f"❌  {sub}/: {e}")

        if not results:
            emit("⚠  No Tomcat cache dirs found. Check BOE_INSTALL_DIR in .env")
            emit(f"   Tomcat expected at: {tomcat_parent}")
        else:
            emit("\n".join(results))
            emit(f"\n🗑  Total: {cleared} cached files cleared.")
            emit("⚠  Restart Tomcat for changes to take effect: type 'restart tomcat'")
        return AgentResult(bool(results), f"{cleared} files cleared", action="clear_cache")

    # ── Service restart ───────────────────────────────────────────────────────

    def _restart_tomcat(self, intent, emit):
        emit("🔄  Restarting Tomcat…")
        from core.sapbo_connection import bo_session
        host = bo_session.cms_details.get("host","localhost")

        if IS_WIN:
            # Try known BO Tomcat service names from Config
            for svc, desc in Config.BO_SERVICES.items():
                if "tomcat" in desc.lower() or "Tomcat" in svc:
                    emit(f"⏹  Stopping {svc}…")
                    r = _run_cmd(f'sc stop "{svc}"', timeout=20)
                    if "FAILED" not in r and "1060" not in r:  # 1060 = not found
                        emit(f"   {r[:80]}")
                        time.sleep(3)
                        emit(f"▶  Starting {svc}…")
                        r2 = _run_cmd(f'sc start "{svc}"', timeout=20)
                        emit(f"   {r2[:80]}")
                        # Verify
                        for _ in range(5):
                            time.sleep(2)
                            try:
                                s = socket.create_connection((host, 8080), timeout=2)
                                s.close()
                                emit(f"✅  Tomcat is back online on port 8080!")
                                return AgentResult(True, "Tomcat restarted", action="restart_tomcat")
                            except Exception:
                                pass
                        emit("⚠  Port 8080 not responding yet. Give it 30 more seconds.")
                        return AgentResult(True, "Restart sent", action="restart_tomcat")
            emit("⚠  Could not identify Tomcat service name.")
            emit(f"   Known services: {list(Config.BO_SERVICES.keys())[:5]}")
        else:
            r = _run_cmd("sudo systemctl restart tomcat || sudo service tomcat restart", timeout=25)
            emit(r)
        return AgentResult(True, "Restart sent", action="restart_tomcat")

    def _restart_service(self, intent, emit):
        svc = intent.get("param") or "tomcat"
        emit(f"🔄  Restarting service: '{svc}'…")
        if IS_WIN:
            # Look up in Config.BO_SERVICES
            matches = [k for k, v in Config.BO_SERVICES.items()
                       if svc.lower() in k.lower() or svc.lower() in v.lower()]
            names = matches or [svc]
            for name in names:
                r1 = _run_cmd(f'sc stop "{name}"', timeout=15)
                if "FAILED" not in r1 and "1060" not in r1:
                    emit(f"Stop: {r1[:80]}")
                    time.sleep(2)
                    r2 = _run_cmd(f'sc start "{name}"', timeout=15)
                    emit(f"Start: {r2[:80]}")
                    return AgentResult(True, f"Restarted {name}", action="restart_service")
            emit(f"⚠  Service '{svc}' not found.\n"
                 f"Available BO services:\n" +
                 "\n".join(f"  • {k}: {v}" for k,v in list(Config.BO_SERVICES.items())[:8]))
        else:
            r = _run_cmd(f"sudo systemctl restart {svc}", timeout=20)
            emit(r)
        return AgentResult(True, f"Restarted {svc}", action="restart_service")

    # ── Process check ─────────────────────────────────────────────────────────

    def _check_process(self, intent, emit):
        name = intent.get("param") or "java"
        emit(f"🔍  Checking process: '{name}'…")

        if IS_WIN:
            # Check process list
            out = _run_cmd(f'tasklist /fi "imagename eq {name}*" /fo table /nh', timeout=8)
            if name.lower() in out.lower() and "No tasks" not in out:
                emit(f"✅  {name} is RUNNING\n{out[:400]}")
            else:
                # Check service
                svc_out = _run_cmd(f'sc query type= all state= running | findstr /i "{name}"', timeout=8)
                if svc_out and "FAILED" not in svc_out:
                    emit(f"✅  Service {name} is running:\n{svc_out[:200]}")
                else:
                    emit(f"❌  {name} not found in running processes or services.")
        else:
            out = _run_cmd(f"pgrep -la {name}")
            if out and "[exit" not in out:
                emit(f"✅  {name} is RUNNING:\n{out[:300]}")
            else:
                emit(f"❌  {name} not running.")
        return AgentResult(True, "Process checked", action="check_process")

    # ── System info ───────────────────────────────────────────────────────────

    def _system_info(self, intent, emit):
        import platform as pf
        emit(f"🖥  System Info:")
        emit(f"  OS:       {pf.system()} {pf.release()} ({pf.machine()})")
        emit(f"  Host:     {socket.gethostname()}")
        emit(f"  Python:   {pf.python_version()}")
        try:
            import psutil
            emit(f"  CPUs:     {psutil.cpu_count()} logical")
            vm = psutil.virtual_memory()
            emit(f"  RAM:      {vm.total//(1024**3)} GB total, {vm.percent}% used")
        except Exception:
            pass
        emit(f"\n  BO Install: {Config.BOE_INSTALL_DIR}")
        emit(f"  BO Logs:    {Config.BOE_LOG_DIR}")
        emit(f"  Tomcat:     {Config.BOE_TOMCAT_DIR}")
        return AgentResult(True, "System info", action="system_info")

    # ── SSL config ────────────────────────────────────────────────────────────

    def _configure_ssl(self, intent, emit):
        emit("🔐  Tomcat SSL Configuration\n" + "─"*50)
        server_xml = Path(Config.BOE_SERVER_XML)
        emit(f"server.xml: {server_xml}  ({'✅ exists' if server_xml.exists() else '❌ not found'})\n")

        if server_xml.exists():
            content = server_xml.read_text(encoding="utf-8", errors="replace")
            if "SSLEnabled" in content:
                emit("ℹ  SSL connector already present in server.xml.")
                m = re.search(r'<Connector[^>]*SSLEnabled[^>]*/>', content, re.DOTALL)
                if m:
                    emit(m.group(0)[:600])
            else:
                emit("ℹ  No SSL connector found. Add the following inside <Service>:\n")
        emit(
            '2️⃣  Add this SSL Connector to server.xml:\n'
            '   <Connector port="8443" protocol="HTTP/1.1" SSLEnabled="true"\n'
            '              maxThreads="150" scheme="https" secure="true"\n'
            '              keystoreFile="<path>/bo_keystore.jks"\n'
            '              keystorePass="changeit" clientAuth="false"\n'
            '              sslProtocol="TLS" />\n\n'
            '1️⃣  Generate keystore first:\n'
            '   keytool -genkey -alias tomcat -keyalg RSA -keysize 2048 \\\n'
            '           -validity 365 -keystore bo_keystore.jks\n\n'
            '3️⃣  Restart Tomcat: type "restart tomcat"\n'
            '4️⃣  Verify: type "check port 8443"\n'
        )
        return AgentResult(True, "SSL guide", action="configure_ssl")

    # ── Network check ─────────────────────────────────────────────────────────

    def _check_network(self, intent, emit):
        from core.sapbo_connection import bo_session
        host = bo_session.cms_details.get("host","localhost")
        emit(f"🌐  Network check for {host}…\n")
        for port, label in Config.BO_PORTS.items():
            try:
                s = socket.create_connection((host, port), timeout=2)
                s.close()
                emit(f"  🟢  {port:>6}  {label}")
            except Exception:
                emit(f"  🔴  {port:>6}  {label}")
        return AgentResult(True, "Network checked", action="check_network")

    def _list_services(self, intent, emit):
        emit("🔧  BO Windows Services:\n")
        for svc, desc in Config.BO_SERVICES.items():
            r = _run_cmd(f'sc query "{svc}"', timeout=5)
            running = "RUNNING" in r.upper()
            icon = "🟢" if running else "🔴"
            emit(f"  {icon}  {svc:<35}  {desc}")
        return AgentResult(True, "Services listed", action="list_services")

    def _env_info(self, intent, emit):
        emit("⚙  Environment configuration:\n")
        emit(f"  BOE_INSTALL_DIR:  {Config.BOE_INSTALL_DIR}")
        emit(f"  BOE_LOG_DIR:      {Config.BOE_LOG_DIR}")
        emit(f"  BOE_TOMCAT_DIR:   {Config.BOE_TOMCAT_DIR}")
        emit(f"  JAVA_BRIDGE_JAR:  {os.environ.get('JAVA_BRIDGE_JAR','not set')}")
        return AgentResult(True, "Env info", action="env_info")


# ─────────────────────────────────────────────────────────────────────────────
#  Utility helpers (module-level, used by all agents)
# ─────────────────────────────────────────────────────────────────────────────

def _run_cmd(cmd: str, timeout: int = 20) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        return ((r.stdout or "") + ("\n" + r.stderr if r.stderr else "")).strip() or f"[exit {r.returncode}]"
    except subprocess.TimeoutExpired:
        return f"[timeout {timeout}s]"
    except Exception as e:
        return f"[error: {e}]"


def _tail_file(path: Path, lines: int = 50) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        return "".join(all_lines[-lines:])
    except Exception as e:
        return f"[could not read {path}: {e}]"


def _read_log_tail(log_name: str, lines: int = 50) -> str:
    log_dir = Path(Config.BOE_LOG_DIR)
    candidates = []
    if log_dir.exists():
        for f in log_dir.rglob("*.log"):
            if log_name.lower() in f.name.lower():
                candidates.append(f)
        if not candidates:
            # Also try tomcat logs dir
            tomcat_dir = Path(Config.BOE_TOMCAT_DIR)
            if tomcat_dir.exists():
                for f in tomcat_dir.glob("*.log"):
                    if log_name.lower() in f.name.lower():
                        candidates.append(f)

    if not candidates:
        avail = [f.name for f in log_dir.glob("*.log")][:8] if log_dir.exists() else []
        return (f"❌ Log '{log_name}' not found in {log_dir}\n"
                + (f"Available: {', '.join(avail)}" if avail else "Log dir not found."))

    target = sorted(candidates, key=lambda f: f.stat().st_mtime, reverse=True)[0]
    content = _tail_file(target, lines)
    return f"📄  {target.name}  (last {lines} lines)\n{'─'*60}\n{content}"


def _ai_analyse_log(content: str, emit: Callable):
    """If AI is available, briefly analyse the log for errors."""
    if not content or len(content) < 50:
        return
    has_err = any(w in content.lower() for w in ["error", "exception", "fatal", "severe", "warn"])
    if not has_err:
        return
    try:
        from ai.gemini_client import GeminiClient
        ai = GeminiClient()
        r = ai.ask(
            f"Analyse this SAP BO log. List only critical errors and recommended fix. "
            f"Max 150 words.\n\nLOG:\n{content[-1500:]}"
        )
        if r and len(r) > 10:
            emit(f"\n🤖  AI Log Analysis:\n{r}")
    except Exception:
        pass
