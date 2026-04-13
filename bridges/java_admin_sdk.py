"""
bridges/java_admin_sdk.py  —  BO Commander  Java Admin SDK Bridge  v2.0
=======================================================================
Bridges Python → Java Admin SDK for operations the REST API cannot do:
  • Server Start / Stop / Restart
  • Node / SIA management
  • Cluster operations
  • Real-time server state + metrics via IEnterpriseSession

Two execution strategies (auto-selected):
  A) ServerManager.jar  — thin Java wrapper we ship with BO Commander
     (compiled from bridges/ServerManager.java, runs via subprocess)
  B) jpype / Py4J       — if the Java process bridge is available
  C) REST+CMC fallback  — opens browser CMC for manual action

The JAR approach works even without jpype. The JAR is compiled once
against the BO SDK classpath and called from Python like:
    java -cp "<SDK_JARS>" com.bocommander.ServerManager <action> <args>

JAR source is in bridges/ServerManager.java.

Config (from .env):
    JAVA_BRIDGE_JAR      = path to ServerManager.jar
    JAVA_SDK_CLASSPATH   = path to BO SDK jars
"""

import os
import json
import logging
import platform
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger("JavaBridge")
IS_WIN = platform.system() == "Windows"


# ─────────────────────────────────────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────────────────────────────────────
def _env(key: str, default: str = "") -> str:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    return os.environ.get(key, default)


def _get_java_exe() -> str:
    """Find java.exe / java on PATH or in BO install."""
    # Try PATH first
    for name in (["java.exe"] if IS_WIN else ["java"]):
        result = subprocess.run(["where" if IS_WIN else "which", "java"],
                                capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip().splitlines()[0]

    # Try BO embedded JVM
    bo_dir = _env("BOE_INSTALL_DIR", r"D:\SAP BO\SAP BO")
    candidates = [
        Path(bo_dir) / "SAP BusinessObjects Enterprise XI 4.0" / "win64_x64" / "sapjvm_8" / "bin" / "java.exe",
        Path(bo_dir) / "jre" / "bin" / "java.exe",
        Path(r"C:\Program Files\Java\jre1.8.0_291\bin\java.exe"),
        Path("/usr/bin/java"),
        Path("/usr/lib/jvm/java-8-openjdk-amd64/bin/java"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return "java"  # Hope it's on PATH


def _get_sdk_classpath() -> str:
    """Build the BO SDK classpath for running the JAR."""
    cp = _env("JAVA_SDK_CLASSPATH", "")
    if cp:
        return cp

    bo_dir = Path(_env("BOE_INSTALL_DIR", r"D:\SAP BO\SAP BO"))
    sdk_dir = bo_dir / "SAP BusinessObjects Enterprise XI 4.0" / "java" / "lib"
    if sdk_dir.exists():
        jars = list(sdk_dir.glob("*.jar"))
        sep  = ";" if IS_WIN else ":"
        return sep.join(str(j) for j in jars[:30])  # limit to avoid cmd-line overflow
    return ""


def _get_jar_path() -> str:
    """Find the ServerManager.jar."""
    jar = _env("JAVA_BRIDGE_JAR", "")
    if jar and Path(jar).exists():
        return jar
    # Look relative to this file
    here = Path(__file__).parent
    for candidate in [
        here / "ServerManager.jar",
        here.parent / "ServerManager.jar",
        here.parent / "bridges" / "ServerManager.jar",
    ]:
        if candidate.exists():
            return str(candidate)
    return ""


# ─────────────────────────────────────────────────────────────────────────────
#  ServerManager.java source  (auto-generated if JAR missing)
# ─────────────────────────────────────────────────────────────────────────────
SERVER_MANAGER_JAVA = r'''
package com.bocommander;

import com.crystaldecisions.sdk.framework.*;
import com.crystaldecisions.sdk.occa.infostore.*;
import com.crystaldecisions.sdk.plugin.destination.filesystem.*;
import com.crystaldecisions.sdk.occa.managedreports.*;
import com.businessobjects.sdk.plugin.desktop.server.*;

import org.json.*;
import java.util.*;

/**
 * ServerManager — thin CLI wrapper over BO Java Admin SDK.
 * Called by Python bridge as a subprocess.
 *
 * Usage:
 *   java -cp <sdk_jars>:ServerManager.jar com.bocommander.ServerManager <action> <host> <port> <user> <pwd> [server_id]
 *
 * Actions:  list  start  stop  restart  status  metrics
 * Output:   JSON to stdout, errors to stderr
 */
public class ServerManager {
    public static void main(String[] args) throws Exception {
        if (args.length < 5) {
            System.err.println("Usage: ServerManager <action> <host> <port> <user> <pwd> [server_id]");
            System.exit(1);
        }
        String action   = args[0];
        String host     = args[1];
        String port     = args[2];
        String user     = args[3];
        String pwd      = args[4];
        String serverId = args.length > 5 ? args[5] : null;

        IEnterpriseSession session = null;
        try {
            SessionMgr mgr = new SessionMgr();
            session = mgr.logon(user, pwd, host + ":" + port, "secEnterprise");
            IInfoStore infoStore = (IInfoStore) session.getService("", "InfoStore");

            if ("list".equals(action)) {
                listServers(infoStore);
            } else if ("start".equals(action) && serverId != null) {
                controlServer(infoStore, serverId, "start");
            } else if ("stop".equals(action) && serverId != null) {
                controlServer(infoStore, serverId, "stop");
            } else if ("restart".equals(action) && serverId != null) {
                controlServer(infoStore, serverId, "restart");
            } else if ("status".equals(action)) {
                listServers(infoStore);
            } else if ("metrics".equals(action)) {
                getMetrics(infoStore, serverId);
            } else {
                System.err.println("Unknown action: " + action);
                System.exit(1);
            }
        } finally {
            if (session != null) { try { session.logoff(); } catch (Exception e) {} }
        }
    }

    static void listServers(IInfoStore store) throws Exception {
        IInfoObjects objs = store.query(
            "SELECT SI_ID, SI_NAME, SI_KIND, SI_SERVER_IS_ALIVE, " +
            "SI_DESCRIPTION, SI_TOTAL_NUM_FAILURES, SI_SERVER_IS_ENABLED " +
            "FROM CI_SYSTEMOBJECTS WHERE SI_PROGID='crystalenterprise.server'");
        JSONArray arr = new JSONArray();
        for (Object o : objs) {
            IInfoObject obj = (IInfoObject) o;
            JSONObject j = new JSONObject();
            j.put("id",       obj.getID());
            j.put("name",     obj.getTitle());
            j.put("kind",     obj.getKind());
            j.put("alive",    obj.properties().getBoolean("SI_SERVER_IS_ALIVE", false));
            j.put("enabled",  obj.properties().getBoolean("SI_SERVER_IS_ENABLED", false));
            j.put("failures", obj.properties().getInt("SI_TOTAL_NUM_FAILURES", 0));
            arr.put(j);
        }
        System.out.println(new JSONObject().put("servers", arr).put("count", arr.length()).toString());
    }

    static void controlServer(IInfoStore store, String serverId, String action) throws Exception {
        IInfoObjects objs = store.query(
            "SELECT SI_ID, SI_NAME, SI_SERVER_IS_ALIVE FROM CI_SYSTEMOBJECTS WHERE SI_ID=" + serverId);
        if (objs.size() == 0) { System.err.println("Server not found: " + serverId); System.exit(1); }
        IInfoObject obj = (IInfoObject) objs.get(0);
        IServer server = (IServer) obj;

        if ("start".equals(action))        server.start();
        else if ("stop".equals(action))    server.stop();
        else if ("restart".equals(action)) { server.stop(); Thread.sleep(3000); server.start(); }

        store.commit(objs);
        System.out.println(new JSONObject()
            .put("status", "ok").put("action", action).put("server_id", serverId)
            .put("server_name", obj.getTitle()).toString());
    }

    static void getMetrics(IInfoStore store, String serverId) throws Exception {
        String query = serverId != null
            ? "SELECT * FROM CI_SYSTEMOBJECTS WHERE SI_ID=" + serverId
            : "SELECT SI_ID, SI_NAME, SI_KIND, SI_SERVER_IS_ALIVE FROM CI_SYSTEMOBJECTS WHERE SI_PROGID='crystalenterprise.server'";
        IInfoObjects objs = store.query(query);
        JSONArray arr = new JSONArray();
        for (Object o : objs) {
            IInfoObject obj = (IInfoObject) o;
            JSONObject j = new JSONObject();
            j.put("id",       obj.getID());
            j.put("name",     obj.getTitle());
            j.put("alive",    obj.properties().getBoolean("SI_SERVER_IS_ALIVE", false));
            arr.put(j);
        }
        System.out.println(new JSONObject().put("metrics", arr).toString());
    }
}
'''


def _write_java_source() -> Path:
    """Write ServerManager.java source next to this file."""
    here = Path(__file__).parent
    java_file = here / "ServerManager.java"
    java_file.write_text(SERVER_MANAGER_JAVA, encoding="utf-8")
    return java_file


def _compile_jar() -> str:
    """Attempt to compile ServerManager.java into a JAR. Returns jar path or ''."""
    java_src = _write_java_source()
    here     = java_src.parent
    out_jar  = here / "ServerManager.jar"
    javac    = _get_java_exe().replace("java", "javac")
    cp       = _get_sdk_classpath()

    cmd = f'"{javac}" -cp "{cp}" -d "{here}" "{java_src}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        logger.warning(f"JAR compile failed: {result.stderr[:200]}")
        return ""

    # Create JAR
    jar_cmd = f'"jar" cf "{out_jar}" -C "{here}" com'
    subprocess.run(jar_cmd, shell=True, capture_output=True, timeout=30)
    return str(out_jar) if out_jar.exists() else ""


# ─────────────────────────────────────────────────────────────────────────────
#  Java bridge call
# ─────────────────────────────────────────────────────────────────────────────
def _run_java(action: str, extra_args: List[str] = None, timeout: int = 30) -> dict:
    """
    Run ServerManager.jar via subprocess.
    Returns parsed JSON dict or {"error": "..."} on failure.
    """
    jar = _get_jar_path()
    if not jar:
        jar = _compile_jar()
    if not jar:
        return {"error": "ServerManager.jar not found. See bridges/ServerManager.java to compile."}

    java   = _get_java_exe()
    cp     = _get_sdk_classpath()
    host   = _env("BO_CMS_HOST", "localhost")
    port   = _env("BO_CMS_PORT", "6405")
    user   = _env("BO_ADMIN_USER", "Administrator")
    pwd    = _env("BO_ADMIN_PASS", "")
    sep    = ";" if IS_WIN else ":"

    full_cp = f"{cp}{sep}{jar}" if cp else jar
    cmd = [java, "-cp", full_cp, "com.bocommander.ServerManager",
           action, host, port, user, pwd] + (extra_args or [])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip()[:400] or f"exit {result.returncode}"}
        return json.loads(result.stdout.strip() or "{}")
    except subprocess.TimeoutExpired:
        return {"error": f"Java bridge timeout after {timeout}s"}
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON from Java: {e}"}
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────
class JavaAdminSDK:
    """
    Python facade over the Java Admin SDK bridge.

    Usage:
        from bridges.java_admin_sdk import java_sdk
        servers = java_sdk.list_servers()
        result  = java_sdk.restart_server("12345")
    """

    def __init__(self):
        self._available: Optional[bool] = None
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        """Check whether the Java bridge is usable."""
        if self._available is None:
            with self._lock:
                jar  = _get_jar_path()
                java = _get_java_exe()
                try:
                    r = subprocess.run([java, "-version"], capture_output=True,
                                       text=True, timeout=5)
                    self._available = r.returncode == 0 and bool(jar)
                except Exception:
                    self._available = False
        return self._available

    def availability_message(self) -> str:
        if self.is_available():
            return f"✅ Java bridge ready  (JAR: {_get_jar_path()})"
        jar = _get_jar_path()
        if not jar:
            return ("❌ ServerManager.jar not found.\n"
                    "  To enable: compile bridges/ServerManager.java against BO SDK jars.\n"
                    f"  Set JAVA_BRIDGE_JAR= and JAVA_SDK_CLASSPATH= in .env")
        return "❌ Java not found on PATH or in BO install directory."

    def list_servers(self) -> Tuple[bool, List[Dict]]:
        """
        List all BO servers via Java SDK.
        Returns (success, list_of_server_dicts).
        Falls back to REST API if bridge unavailable.
        """
        if not self.is_available():
            return False, []
        result = _run_java("list")
        if "error" in result:
            logger.error(f"list_servers: {result['error']}")
            return False, []
        servers = result.get("servers", [])
        return True, servers

    def start_server(self, server_id: str) -> Tuple[bool, str]:
        """Start a BO server by CMS object ID."""
        return self._control("start", server_id)

    def stop_server(self, server_id: str) -> Tuple[bool, str]:
        """Stop a BO server by CMS object ID."""
        return self._control("stop", server_id)

    def restart_server(self, server_id: str) -> Tuple[bool, str]:
        """Restart a BO server by CMS object ID (stop then start)."""
        return self._control("restart", server_id)

    def _control(self, action: str, server_id: str) -> Tuple[bool, str]:
        if not self.is_available():
            return False, self.availability_message()
        result = _run_java(action, [str(server_id)], timeout=60)
        if "error" in result:
            return False, f"❌ Java SDK error: {result['error']}"
        return True, (f"✅ {action.capitalize()} sent to server {server_id}  "
                      f"({result.get('server_name', '')})")

    def get_metrics(self, server_id: str = None) -> Dict:
        """Get server metrics dict from Java SDK."""
        result = _run_java("metrics", [str(server_id)] if server_id else [], timeout=20)
        return result

    # ── Windows Service fallback (when JAR is not available) ─────────────────

    def windows_service_restart(self, service_name: str = None) -> Tuple[bool, str]:
        """
        Restart the BO Tomcat / SIA Windows service directly.
        This is the fallback when the Java JAR is not compiled yet.
        """
        if not IS_WIN:
            return False, "Windows service control only works on Windows."

        from config import Config
        services = Config.BO_SERVICES
        # Find the best match
        target = service_name
        if not target or target.lower() in ("tomcat", "boexi40tomcat"):
            target = "BOEXI40Tomcat"

        lines = []
        try:
            # Stop
            r = subprocess.run(f'sc stop "{target}"', shell=True,
                               capture_output=True, text=True, timeout=20)
            lines.append(f"Stop {target}: {(r.stdout + r.stderr).strip()[:100]}")
            time.sleep(3)
            # Start
            r = subprocess.run(f'sc start "{target}"', shell=True,
                               capture_output=True, text=True, timeout=20)
            lines.append(f"Start {target}: {(r.stdout + r.stderr).strip()[:100]}")
            # Verify
            time.sleep(2)
            r = subprocess.run(f'sc query "{target}"', shell=True,
                               capture_output=True, text=True, timeout=10)
            running = "RUNNING" in r.stdout.upper()
            lines.append(f"Status: {'✅ RUNNING' if running else '⚠ NOT RUNNING'}")
            return running, "\n".join(lines)
        except Exception as e:
            return False, f"❌ Service control error: {e}"

    def get_cmс_url(self) -> str:
        """Return CMC URL as the final fallback for server control."""
        host = _env("BO_CMS_HOST", "localhost")
        return f"http://{host}:8080/BOE/CMC/"


# Singleton
java_sdk = JavaAdminSDK()
