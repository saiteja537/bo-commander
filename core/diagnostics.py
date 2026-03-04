import subprocess
import os
import pyodbc
import shutil
import platform

class DiagnosticEngine:
    def run_command(self, command):
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
            if result.returncode == 0: return result.stdout.strip()
            return f"Error: {result.stderr.strip()}"
        except Exception as e: return f"Execution failed: {str(e)}"

    def check_port(self, port):
        """Checks if a TCP port is listening."""
        cmd = f"netstat -ano | findstr LISTENING | findstr :{port}"
        out = self.run_command(cmd)
        return f"OPEN (Port {port})" if out and f":{port}" in out else f"CLOSED (Port {port})"

    def test_db_connection(self):
        """Tests SQL connection via ODBC DSN."""
        try:
            u, p = os.getenv("AUDIT_DB_USER"), os.getenv("AUDIT_DB_PASS")
            conn = pyodbc.connect(f'DSN=BI4_Audit_DSN;UID={u};PWD={p}', timeout=3); conn.close()
            return "SUCCESS: DB Reachable"
        except Exception as e: return f"FAILED: DB Unreachable ({str(e)})"

    def test_url(self, url):
        """Checks HTTP status of Web URL."""
        cmd = f"powershell -Command \"try {{ (Invoke-WebRequest -Uri '{url}' -UseBasicParsing -TimeoutSec 5).StatusCode }} catch {{ $_.Exception.Response.StatusCode.value__ }}\""
        out = self.run_command(cmd).strip()
        return f"SUCCESS (HTTP {out})" if "200" in out else f"FAILED (HTTP {out})"

    # --- NEW: ENVIRONMENTAL CHECKS ---
    def check_disk_space(self):
        """Checks C: and Installation Drive space."""
        try:
            # Check BO Install Dir Drive
            bo_dir = os.getenv("BOE_INSTALL_DIR", "C:\\")
            drive = os.path.splitdrive(bo_dir)[0]
            total, used, free = shutil.disk_usage(drive)
            percent_free = (free / total) * 100
            status = "CRITICAL" if percent_free < 5 else "OK"
            return f"{status}: Drive {drive} has {free // (2**30)}GB free ({percent_free:.1f}%)"
        except: return "Disk check failed"

    def check_network_ping(self, target="8.8.8.8"):
        """Checks basic network connectivity."""
        param = "-n" if platform.system().lower() == "windows" else "-c"
        out = self.run_command(f"ping {param} 1 {target}")
        return "Network OK" if "TTL=" in out else "Network Unreachable"

    def get_windows_event_logs(self):
        """Reads last 10 Critical/Error events from Windows Application Log."""
        # Using PowerShell to get clean event logs without needing extra Python libs
        cmd = "powershell -Command \"Get-EventLog -LogName Application -EntryType Error,Warning -Newest 10 | Select-Object -Property TimeGenerated, Source, Message | Format-List\""
        return self.run_command(cmd)