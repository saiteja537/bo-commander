import os
import glob
import json
import threading
import re
import subprocess
import socket
from datetime import datetime
import logging

from config import Config
from core.sapbo_connection import bo_session
from ai.gemini_client import ai_client

logger = logging.getLogger("SentinelAgent")


class SentinelAgent:
    """
    AI SENTINEL AGENT — Cross-Layer Diagnostic Engine

    All paths, log patterns, services, and thresholds are read from
    Config (which reads from .env). To change any path or add logs,
    edit .env — no code changes needed.

    Layers:
      1. OS diagnostics   — all BO services, memory, disk, Java processes
      2. Network          — port checks, ping, DNS, netstat
      3. Event Viewer     — Windows System + Application critical events
      4. BO logs          — reads every log file defined in Config.BO_LOG_PATTERNS
      5. Database logs    — reads DB logs defined in Config.DB_LOGS
      6. BO server API    — server/session/failed report data (when connected)
      7. Correlation      — cross-layer failure chain analysis
      8. AI analysis      — Gemini root cause + fix generation
    """

    def __init__(self, ui_callback):
        self.ui_callback   = ui_callback
        self.incidents     = []
        self.performance_history = []
        self.error_patterns = self._load_error_patterns()

        # All paths come from Config / .env
        self.bo_dir        = Config.BOE_INSTALL_DIR
        self.bo_log_dir    = Config.BOE_LOG_DIR
        self.log_tail      = Config.SENTINEL_CONFIG['log_tail_lines']
        self.cmd_timeout   = Config.SENTINEL_CONFIG['cmd_timeout']

        # Validate install dir
        if os.path.exists(self.bo_dir):
            logger.info(f"✅ Sentinel Agent Initialized | BO Dir: {self.bo_dir}")
        else:
            logger.warning(
                f"⚠️ Sentinel Agent Initialized | BO Dir NOT FOUND: {self.bo_dir}\n"
                f"   → Set BOE_INSTALL_DIR in your .env file to enable log reading.\n"
                f"   → OS + Network diagnostics will still run fully."
            )

    # =========================================================================
    # ERROR PATTERNS
    # =========================================================================

    def _load_error_patterns(self):
        return {
            'memory': [
                r'OutOfMemoryError', r'Java heap space', r'GC overhead limit exceeded',
                r'Native memory allocation.*failed', r'Cannot allocate memory',
                r'java\.lang\.OutOfMemoryError', r'Allocation.*failed',
            ],
            'connection': [
                r'Connection refused', r'Connection timed out', r'No route to host',
                r'Connection reset', r'Unable to connect to CMS',
                r'Database connection failed', r'CORBA.*exception', r'CMS.*unavailable',
                r'failed to connect',
            ],
            'authentication': [
                r'Authentication failed', r'Invalid credentials', r'Access denied',
                r'User not found', r'Cannot validate credentials',
                r'logon.*failed', r'session.*expired', r'token.*invalid',
            ],
            'server_crash': [
                r'Server stopped unexpectedly', r'Fatal error detected',
                r'Segmentation fault', r'Server is shutting down',
                r'Unrecoverable error', r'JVM crash', r'hs_err_pid',
                r'EXCEPTION_ACCESS_VIOLATION',
            ],
            'report_error': [
                r'Report failed to refresh', r'Query execution failed',
                r'Universe not found', r'Data source connection failed',
                r'Syntax error in query', r'report.*timeout',
                r'maximum.*rows.*exceeded',
            ],
            'database': [
                r'SQLException', r'Database not available', r'Table.*not found',
                r'Deadlock detected', r'Query timeout', r'ORA-\d+',
                r'MSSQL.*error', r'connection pool.*exhausted',
                r'Lock wait timeout', r'too many connections',
            ],
            'disk': [
                r'No space left on device', r'disk.*full', r'Insufficient disk',
                r'Cannot write.*file', r'I/O error',
            ],
            'network': [
                r'DNS.*failed', r'Name resolution.*failed', r'Network.*unreachable',
                r'socket.*timeout', r'host.*unreachable',
            ],
        }

    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================

    def investigate(self, trigger, details=None):
        """Launch full 8-layer RCA in background thread. Non-blocking."""
        threading.Thread(
            target=self._run_rca, args=(trigger, details), daemon=True
        ).start()

    def _run_rca(self, trigger, details):
        """Execute the full diagnostic pipeline."""
        try:
            logger.info(f"🔍 RCA started | Trigger: {trigger}")
            ctx = {
                'trigger':             trigger,
                'details':             details or {},
                'bo_connected':        bo_session.connected,
                'bo_attempted_host':   (details or {}).get('host', Config.BO_CMS_HOST),
                'bo_error':            (details or {}).get('error', 'Connection refused'),
                'timestamp':           datetime.now().isoformat(),
            }

            logger.info("Layer 1/7: OS diagnostics...")
            ctx['os'] = self._run_os_diagnostics()

            logger.info("Layer 2/7: Network diagnostics...")
            ctx['network'] = self._run_network_diagnostics(ctx['bo_attempted_host'])

            if Config.SENTINEL_CONFIG['scan_event_viewer']:
                logger.info("Layer 3/7: Windows Event Viewer...")
                ctx['events'] = self._collect_windows_events()
            else:
                ctx['events'] = {'note': 'Event Viewer scanning disabled in .env'}

            logger.info("Layer 4/7: BO log analysis...")
            ctx['bo_logs'] = self._analyze_bo_logs()

            if Config.SENTINEL_CONFIG['scan_db_logs']:
                logger.info("Layer 5/7: Database log analysis...")
                ctx['db_logs'] = self._analyze_db_logs()
            else:
                ctx['db_logs'] = {'note': 'DB log scanning disabled in .env'}

            if bo_session.connected:
                logger.info("Layer 6/7: BO server API status...")
                ctx['bo_server'] = self._check_bo_server_status()
            else:
                ctx['bo_server'] = {'connected': False, 'note': 'Skipped — not connected'}

            logger.info("Layer 7/7: Cross-layer correlation...")
            ctx['correlation'] = self._correlate(ctx)

            logger.info("🤖 Sending to Gemini for AI analysis...")
            report = self._ai_analyze(ctx)

            if not report:
                logger.warning("AI failed — using rule-based fallback")
                report = self._fallback_report(ctx)

            if report:
                report['timestamp'] = datetime.now().strftime("%H:%M:%S")
                report['trigger']   = trigger
                self.incidents.insert(0, report)
                logger.info(f"✅ RCA Complete: {report.get('title','?')} [{report.get('severity','?')}]")

                if self.ui_callback:
                    try:
                        self.ui_callback()
                    except Exception as e:
                        # TclError "bad window path" = page navigated away — harmless
                        logger.debug(f"UI callback skipped (widget gone): {e}")

        except Exception as e:
            logger.error(f"❌ RCA pipeline crashed: {e}", exc_info=True)

    # =========================================================================
    # LAYER 1 — OS DIAGNOSTICS
    # Uses Config.BO_SERVICES and Config.BO_PROCESSES
    # =========================================================================

    def _run_os_diagnostics(self):
        result = {}

        result['hostname']   = self._cmd('hostname')
        result['os_version'] = self._cmd('ver')
        result['uptime']     = self._cmd('systeminfo | findstr /C:"System Boot Time"')

        # Memory
        result['total_memory_mb'] = self._cmd(
            'powershell -NoProfile -Command '
            '"[math]::Round((Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize/1KB)"'
        )
        result['free_memory_mb'] = self._cmd(
            'powershell -NoProfile -Command '
            '"[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1KB)"'
        )

        # Disk — all drives
        result['disk_space'] = self._cmd(
            'powershell -NoProfile -Command "'
            'Get-PSDrive -PSProvider FileSystem | '
            'Select-Object Name,'
            '@{N=\\"Used_GB\\";E={[math]::Round($_.Used/1GB,1)}},'
            '@{N=\\"Free_GB\\";E={[math]::Round($_.Free/1GB,1)}} | '
            'Format-Table | Out-String"'
        )

        # ── All SAP BO Windows services (from Config) ─────────────────────
        result['bo_services'] = {}
        for svc, desc in Config.BO_SERVICES.items():
            raw     = self._cmd(f'sc query "{svc}"')
            running = 'RUNNING' in raw
            exists  = 'does not exist' not in raw.lower() and 'OpenService FAILED' not in raw
            status  = 'RUNNING' if running else ('STOPPED' if exists else 'NOT_FOUND')
            result['bo_services'][svc] = {
                'description': desc,
                'running':     running,
                'status':      status,
            }
            if running or status == 'STOPPED':
                logger.info(f"  Service {svc}: {status}")

        # ── All SAP BO processes (from Config) ────────────────────────────
        running_procs = []
        for proc in Config.BO_PROCESSES:
            raw = self._cmd(f'tasklist /FI "IMAGENAME eq {proc}" /FO csv /NH')
            if proc.lower() in raw.lower() and 'INFO:' not in raw:
                # Extract memory usage
                mem_match = re.search(r'"(\d[\d,]+) K"', raw)
                mem_mb = round(int(mem_match.group(1).replace(',','')) / 1024) if mem_match else 0
                running_procs.append({'name': proc, 'memory_mb': mem_mb, 'raw': raw[:200]})

        result['bo_processes_running'] = running_procs
        logger.info(f"  BO processes found: {[p['name'] for p in running_procs]}")

        # Top memory consumers overall
        result['top_processes'] = self._cmd(
            'powershell -NoProfile -Command "'
            'Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 10 '
            'Name,Id,@{N=\\"RAM_MB\\";E={[math]::Round($_.WorkingSet64/1MB,0)}} | '
            'Format-Table | Out-String"'
        )

        # Java processes specifically
        result['java_processes'] = self._cmd(
            'powershell -NoProfile -Command "'
            'Get-Process java,javaw -ErrorAction SilentlyContinue | '
            'Select-Object Id,@{N=\\"RAM_MB\\";E={[math]::Round($_.WorkingSet64/1MB,0)}} | '
            'Format-Table | Out-String"'
        )

        return result

    # =========================================================================
    # LAYER 2 — NETWORK DIAGNOSTICS
    # =========================================================================

    def _run_network_diagnostics(self, target_host):
        result = {}
        host   = target_host if target_host and target_host not in ('', 'unknown') else 'localhost'

        # Port checks using Python socket — faster and more reliable than commands
        for port, name in [(6405, 'cms'), (8080, 'tomcat_http'), (8443, 'tomcat_https')]:
            open_ = self._check_port(host, port)
            result[f'port_{port}_{name}'] = 'OPEN' if open_ else 'CLOSED'
            logger.info(f"  Port {port} ({name}) on {host}: {'OPEN' if open_ else 'CLOSED'}")

        # What is actually listening on BO ports?
        result['netstat_6405'] = self._cmd('netstat -ano | findstr :6405')
        result['netstat_8080'] = self._cmd('netstat -ano | findstr :8080')
        result['established_count'] = self._cmd(
            'powershell -NoProfile -Command "(netstat -ano | Select-String ESTABLISHED).Count"'
        )

        if host != 'localhost':
            result['ping']        = self._cmd(f'ping -n 4 -w 2000 {host}')
            result['dns_lookup']  = self._cmd(f'nslookup {host}')
            result['traceroute']  = self._cmd(f'tracert -h 8 -w 1000 {host}')
            reachable = 'TTL' in result['ping']
            logger.info(f"  Ping {host}: {'OK' if reachable else 'FAILED'}")

        # Also check monitoring URLs from Config
        for name, url in Config.MONITOR_CONFIG['urls'].items():
            result[f'url_{name}'] = self._cmd(
                f'powershell -NoProfile -Command '
                f'"try{{(Invoke-WebRequest -Uri \'{url}\' -TimeoutSec 5 -UseBasicParsing).StatusCode}}'
                f'catch{{$_.Exception.Message}}"'
            )

        return result

    def _check_port(self, host, port, timeout=3):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            return False

    # =========================================================================
    # LAYER 3 — WINDOWS EVENT VIEWER
    # =========================================================================

    def _collect_windows_events(self):
        result = {}

        ps_template = (
            'powershell -NoProfile -Command "'
            "Get-WinEvent -LogName '{log}' -MaxEvents 20 "
            "-FilterXPath '*[System[(Level=1 or Level=2)]]' "
            "2>\\$null | Select-Object TimeCreated,Id,LevelDisplayName,"
            "@{{N='Msg';E={{\\$_.Message.Substring(0,[math]::Min(200,\\$_.Message.Length))}}}} "
            '| Format-List | Out-String -Width 300"'
        )

        for log_name in ['System', 'Application']:
            output = self._cmd(ps_template.format(log=log_name))
            result[log_name] = output[:4000] if output else 'No critical events found'
            count = output.count('Error') + output.count('Critical')
            logger.info(f"  Event Viewer [{log_name}]: {count} critical/error entries")

        # Security events — failed logons (relevant for auth issues)
        result['Security_FailedLogons'] = self._cmd(
            'powershell -NoProfile -Command "'
            "Get-WinEvent -LogName Security -MaxEvents 10 "
            "-FilterXPath '*[System[(EventID=4625)]]' "
            "2>\\$null | Select-Object TimeCreated,Message | Format-List | Out-String -Width 200\""
        )

        # Java crash dumps — search all dirs from Config
        crash_files = []
        if Config.SENTINEL_CONFIG['scan_java_crashes']:
            search_dirs = list(Config.JAVA_CRASH_DIRS) + [os.getcwd()]
            if os.path.exists(self.bo_dir):
                search_dirs.append(self.bo_dir)

            for d in search_dirs:
                try:
                    for f in glob.glob(os.path.join(d, 'hs_err_pid*.log')):
                        crash_files.append({
                            'path':     f,
                            'modified': datetime.fromtimestamp(os.path.getmtime(f)).strftime('%Y-%m-%d %H:%M'),
                            'preview':  self._read_tail(f, 15)
                        })
                except Exception:
                    pass

        result['java_crash_dumps'] = crash_files if crash_files else 'None found'
        logger.info(f"  Java crash dumps: {len(crash_files)}")
        return result

    # =========================================================================
    # LAYER 4 — BO LOG ANALYSIS
    # Uses Config.BOE_LOG_DIR, Config.BOE_TOMCAT_LOG, Config.BO_LOG_PATTERNS
    # =========================================================================

    def _analyze_bo_logs(self):
        result = {
            'bo_installed_here': os.path.exists(self.bo_dir),
            'bo_dir_checked':    self.bo_dir,
            'logs_scanned':      [],
            'errors_found':      [],
            'categories':        {},
            'note':              '',
        }

        if not os.path.exists(self.bo_dir):
            result['note'] = (
                f"SAP BO directory not found at: {self.bo_dir}\n"
                f"Set BOE_INSTALL_DIR in your .env file to enable log reading.\n"
                f"Example: BOE_INSTALL_DIR=D:\\SAP BO\\SAP BO"
            )
            logger.warning(f"  BO dir not found: {self.bo_dir} — log scan skipped")
            return result

        # Build log file map from Config
        log_files = {}

        # Tomcat catalina — check multiple name variants
        for cname in ['catalina.out', 'catalina.log']:
            cp = os.path.join(Config.BOE_TOMCAT_DIR, cname)
            if os.path.exists(cp):
                log_files['Tomcat_Catalina'] = cp
                break

        # Dated catalina files (e.g. catalina.2024-01-15.log)
        dated = self._find_log_in(Config.BOE_TOMCAT_DIR, 'catalina.*.log')
        if dated:
            log_files['Tomcat_Catalina_Latest'] = dated

        # stdout / stderr
        for tname in ['stdout.log', 'stderr.log']:
            tp = os.path.join(Config.BOE_TOMCAT_DIR, tname)
            if os.path.exists(tp):
                log_files[f'Tomcat_{tname}'] = tp

        # Direct path from Config
        if Config.BOE_TOMCAT_LOG and os.path.exists(Config.BOE_TOMCAT_LOG):
            log_files['Tomcat'] = Config.BOE_TOMCAT_LOG

        # Pattern-based log discovery using Config.BO_LOG_PATTERNS
        for log_name, pattern in Config.BO_LOG_PATTERNS.items():
            found = self._find_log(pattern)
            if found:
                log_files[log_name] = found

        # Also scan EXTRA_LOG_DIRS from .env
        for extra_dir in Config.EXTRA_LOG_DIRS:
            if os.path.isdir(extra_dir):
                for f in glob.glob(os.path.join(extra_dir, '*.log')) + glob.glob(os.path.join(extra_dir, '*.glf')):
                    log_files[f'Extra:{os.path.basename(f)}'] = f

        severity_order = ['server_crash', 'memory', 'disk', 'database', 'connection', 'network', 'authentication', 'report_error']

        for log_name, log_path in log_files.items():
            if not log_path or not os.path.exists(log_path):
                continue

            size_mb = round(os.path.getsize(log_path) / (1024 * 1024), 2)
            result['logs_scanned'].append({
                'name':    log_name,
                'path':    log_path,
                'size_mb': size_mb,
            })
            content = self._read_tail(log_path, self.log_tail)
            logger.info(f"  Scanning {log_name} ({size_mb}MB): {log_path}")

            for category, patterns in self.error_patterns.items():
                for pattern in patterns:
                    for match in re.finditer(pattern, content, re.IGNORECASE):
                        s   = max(0, match.start() - 80)
                        e   = min(len(content), match.end() + 150)
                        snip = content[s:e].replace('\n', ' ').strip()
                        ts   = re.search(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', content[s:e])
                        result['errors_found'].append({
                            'category':        category,
                            'pattern':         pattern,
                            'log_file':        log_name,
                            'log_path':        log_path,
                            'match':           match.group(0),
                            'context':         snip,
                            'error_timestamp': ts.group(0) if ts else 'unknown',
                        })
                        result['categories'][category] = result['categories'].get(category, 0) + 1

        result['errors_found'].sort(
            key=lambda x: severity_order.index(x['category'])
            if x['category'] in severity_order else 999
        )
        logger.info(
            f"  BO log scan: {len(result['logs_scanned'])} files, "
            f"{len(result['errors_found'])} errors in categories: {result['categories']}"
        )
        return result

    # =========================================================================
    # LAYER 5 — DATABASE LOG ANALYSIS
    # Uses Config.DB_LOGS — paths from .env
    # =========================================================================

    def _analyze_db_logs(self):
        result = {'logs_scanned': [], 'errors_found': [], 'note': ''}

        for db_name, log_path in Config.DB_LOGS.items():
            if not log_path:
                continue

            # Handle both file and directory paths
            if os.path.isfile(log_path):
                files_to_scan = [log_path]
            elif os.path.isdir(log_path):
                # Grab the most recent .log or .trc file in the directory
                candidates = (
                    glob.glob(os.path.join(log_path, '**', '*.log'), recursive=True) +
                    glob.glob(os.path.join(log_path, '**', 'alert_*.log'), recursive=True) +
                    glob.glob(os.path.join(log_path, '**', '*.trc'), recursive=True)
                )
                files_to_scan = sorted(candidates, key=os.path.getmtime, reverse=True)[:3]
            else:
                continue

            for fpath in files_to_scan:
                try:
                    size_mb = round(os.path.getsize(fpath) / (1024 * 1024), 2)
                    content = self._read_tail(fpath, self.log_tail)
                    result['logs_scanned'].append({'db': db_name, 'path': fpath, 'size_mb': size_mb})
                    logger.info(f"  Scanning DB log [{db_name}] ({size_mb}MB): {fpath}")

                    for category, patterns in self.error_patterns.items():
                        for pattern in patterns:
                            for match in re.finditer(pattern, content, re.IGNORECASE):
                                s    = max(0, match.start() - 80)
                                e    = min(len(content), match.end() + 150)
                                snip = content[s:e].replace('\n', ' ').strip()
                                result['errors_found'].append({
                                    'category':  category,
                                    'db_source': db_name,
                                    'log_path':  fpath,
                                    'match':     match.group(0),
                                    'context':   snip,
                                })
                except Exception as ex:
                    logger.warning(f"  Could not read DB log {fpath}: {ex}")

        logger.info(f"  DB log scan: {len(result['logs_scanned'])} files, {len(result['errors_found'])} errors")
        return result

    # =========================================================================
    # LAYER 6 — BO SERVER API STATUS
    # =========================================================================

    def _check_bo_server_status(self):
        result = {'connected': bo_session.connected}
        try:
            if bo_session.connected:
                servers = bo_session.get_all_servers()
                result['servers'] = [
                    {'name': s['name'], 'status': s['status'], 'failures': s.get('failures', 0)}
                    for s in servers[:15]
                ]
                result['active_sessions']  = len(bo_session.get_active_sessions(limit=100))
                result['failed_reports']   = len(bo_session.get_instances(status='failed', limit=50))
            else:
                result['error'] = 'Not connected — cannot retrieve server data'
        except Exception as e:
            result['error'] = str(e)
        return result

    # =========================================================================
    # LAYER 7 — CROSS-LAYER CORRELATION
    # =========================================================================

    def _correlate(self, ctx):
        chain          = []
        primary_layer  = None
        confidence     = 'LOW'

        os_data   = ctx.get('os', {})
        net_data  = ctx.get('network', {})
        evt_data  = ctx.get('events', {})
        log_data  = ctx.get('bo_logs', {})
        db_data   = ctx.get('db_logs', {})
        connected = ctx.get('bo_connected', False)
        bo_errors = log_data.get('categories', {})
        host      = ctx.get('bo_attempted_host', '?')

        # ── BO Connectivity ──────────────────────────────────────────────────
        if not connected:
            chain.append(f"❌ BO App Layer: Cannot connect to CMS at {host}:{Config.BO_CMS_PORT}")

            cms = os_data.get('bo_services', {}).get('BOEXI40', {})
            cms_status = cms.get('status', 'UNKNOWN')
            if cms_status == 'RUNNING':
                chain.append("✅ OS Service (BOEXI40/CMS): RUNNING — service is up, issue is elsewhere")
            elif cms_status == 'STOPPED':
                chain.append("❌ OS Service (BOEXI40/CMS): STOPPED — this is the root cause")
                primary_layer, confidence = 'cms_service_stopped', 'HIGH'
            elif cms_status == 'NOT_FOUND':
                chain.append(
                    f"⚠️ OS Service (BOEXI40): NOT FOUND on this machine — "
                    f"BO may be on a remote server at '{host}'"
                )
                primary_layer, confidence = 'bo_on_remote_server', 'HIGH'

            port = net_data.get('port_6405_cms', 'UNKNOWN')
            if port == 'OPEN':
                chain.append("✅ Network: Port 6405 OPEN — CMS is listening, possible auth/SSL issue")
                if not primary_layer:
                    primary_layer, confidence = 'cms_auth_or_app_error', 'MEDIUM'
            elif port == 'CLOSED':
                chain.append(f"❌ Network: Port 6405 CLOSED on {host} — nothing listening")
                if not primary_layer:
                    primary_layer, confidence = 'port_closed', 'HIGH'

            ping = net_data.get('ping', '')
            if ping and 'TTL' in ping:
                chain.append(f"✅ Network: Ping to {host} SUCCEEDED — host is reachable at IP level")
            elif ping and ('timed out' in ping.lower() or 'could not find' in ping.lower()):
                chain.append(f"❌ Network: Ping to {host} FAILED — host unreachable or DNS failure")
                if not primary_layer:
                    primary_layer, confidence = 'network_unreachable', 'HIGH'

        # ── BO Installed Locally? ────────────────────────────────────────────
        if not log_data.get('bo_installed_here'):
            chain.append(
                f"ℹ️ BO Logs: SAP BO NOT installed at {self.bo_dir} — "
                f"BO Commander is connecting to a remote BO server"
            )
        else:
            chain.append(
                f"✅ BO Logs: SAP BO found at {self.bo_dir} — "
                f"{len(log_data.get('logs_scanned',[]))} log files scanned"
            )

        # ── BO Log Errors ────────────────────────────────────────────────────
        for cat in ['server_crash', 'memory', 'disk', 'database', 'connection', 'report_error']:
            count = bo_errors.get(cat, 0)
            if count > 0:
                chain.append(f"❌ BO Logs [{cat}]: {count} error(s) detected")
                if not primary_layer:
                    primary_layer  = cat
                    confidence     = 'HIGH' if cat in ('server_crash', 'memory', 'disk') else 'MEDIUM'

        # ── Database Log Errors ──────────────────────────────────────────────
        db_errors = len(db_data.get('errors_found', []))
        if db_errors > 0:
            chain.append(f"❌ DB Logs: {db_errors} error(s) detected in database logs")
            if not primary_layer:
                primary_layer, confidence = 'database', 'MEDIUM'

        # ── Windows Event Viewer ─────────────────────────────────────────────
        sys_txt = str(evt_data.get('System', ''))
        app_txt = str(evt_data.get('Application', ''))
        sys_errors = sys_txt.count('Error') + sys_txt.count('Critical')
        app_errors = app_txt.count('Error') + app_txt.count('Critical')
        if sys_errors > 0:
            chain.append(f"❌ Windows Events (System): {sys_errors} critical/error events")
        if app_errors > 0:
            chain.append(f"⚠️ Windows Events (Application): {app_errors} error events")

        # ── Java Crashes ─────────────────────────────────────────────────────
        crashes = evt_data.get('java_crash_dumps', [])
        if isinstance(crashes, list) and crashes:
            chain.append(f"❌ JVM: {len(crashes)} Java crash dump file(s) found")
            if not primary_layer:
                primary_layer, confidence = 'jvm_crash', 'HIGH'

        # ── Running BO Processes ─────────────────────────────────────────────
        running = [p['name'] for p in os_data.get('bo_processes_running', [])]
        if running:
            chain.append(f"✅ BO Processes running: {', '.join(running)}")
        else:
            chain.append("⚠️ BO Processes: No BO-related processes found on this machine")

        if not chain:
            chain.append("✅ No issues detected across all diagnostic layers")

        summary = (
            f"Checked {len(os_data.get('bo_services',{}))} Windows services, "
            f"scanned {len(log_data.get('logs_scanned',[]))} BO logs + "
            f"{len(db_data.get('logs_scanned',[]))} DB logs, "
            f"tested {sum(1 for k in net_data if k.startswith('port_'))} network ports. "
            f"Primary fault: {primary_layer or 'undetermined'} | Confidence: {confidence}"
        )
        logger.info(f"Correlation done: {summary}")

        return {
            'chain':         chain,
            'primary_layer': primary_layer,
            'confidence':    confidence,
            'summary':       summary,
        }

    # =========================================================================
    # LAYER 8 — AI ANALYSIS
    # =========================================================================

    def _ai_analyze(self, ctx):
        try:
            summary    = self._build_ai_summary(ctx)
            chain_text = '\n'.join(ctx.get('correlation', {}).get('chain', ['No chain data']))

            prompt = f"""You are the SAP BusinessObjects AI Sentinel.
Perform a cross-layer root cause analysis using the diagnostic data below.

DIAGNOSTIC DATA:
{json.dumps(summary, indent=2, default=str)}

FAILURE CHAIN:
{chain_text}

Identify: which layer failed first, what cascaded, and the exact fix.

Respond with ONLY a JSON object — no markdown, no text outside the JSON:
{{
  "title": "Short incident title (e.g. 'CMS Service Stopped — Connection Refused')",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "error_message": "Exact error text from the most relevant diagnostic source",
  "log_file": "Which log file or diagnostic source has the main evidence",
  "log_path": "Full path or N/A",
  "error_timestamp": "Timestamp from evidence or N/A",
  "category": "memory|connection|authentication|server_crash|report_error|database|disk|network",
  "root_cause": "Which layer failed first and the exact technical reason — be specific",
  "failure_chain": "E.g. CMS service stopped → port 6405 closed → BO Commander refused → users locked out",
  "evidence": "List the specific facts: service status, port status, log lines, event IDs",
  "impact": "What users and features are unavailable right now",
  "prediction": "Will this escalate, and how quickly without action",
  "solution_steps": [
    "Step 1: Most urgent — exact command to run",
    "Step 2: Verification command",
    "Step 3: Fix/restart command",
    "Step 4: Prevention measure",
    "Step 5: Monitoring recommendation"
  ],
  "os_commands": [
    "sc query BOEXI40",
    "sc start BOEXI40"
  ],
  "owner": "BO Admin|Database Team|Network Team|OS Team",
  "priority": "P1|P2|P3|P4",
  "estimated_resolution_time": "e.g. 15 minutes"
}}"""

            report = ai_client.get_json_response(prompt)

            REQUIRED = ['title', 'severity', 'root_cause', 'solution_steps', 'category']
            if report and all(f in report for f in REQUIRED):
                # Fill optional fields with safe defaults
                report.setdefault('error_message',  'See root_cause')
                report.setdefault('log_file',        'System Diagnostic')
                report.setdefault('log_path',        'N/A')
                report.setdefault('error_timestamp', datetime.now().strftime("%H:%M:%S"))
                report.setdefault('failure_chain',   chain_text[:300])
                report.setdefault('evidence',        'See diagnostic data')
                report.setdefault('impact',          'BO Commander functionality affected')
                report.setdefault('prediction',      'Investigate promptly')
                report.setdefault('os_commands',     ['sc query BOEXI40', 'sc start BOEXI40'])
                report.setdefault('owner',           'BO Admin')
                report.setdefault('priority',        'P2')
                report.setdefault('estimated_resolution_time', '30 minutes')
                logger.info(f"✅ AI analysis OK: {report.get('title')}")
                return report

            logger.error(f"AI JSON missing required fields. Got: {list(report.keys()) if report else 'None'}")
            return None

        except Exception as e:
            logger.error(f"AI analysis exception: {e}", exc_info=True)
            return None

    def _build_ai_summary(self, ctx):
        """Condense context to stay within Gemini token limits."""
        os_data  = ctx.get('os', {})
        net_data = ctx.get('network', {})
        evt_data = ctx.get('events', {})
        log_data = ctx.get('bo_logs', {})
        db_data  = ctx.get('db_logs', {})

        return {
            'trigger':                ctx.get('trigger'),
            'connection_details':     ctx.get('details', {}),
            'bo_connected':           ctx.get('bo_connected', False),
            'bo_attempted_host':      ctx.get('bo_attempted_host'),
            'bo_error':               ctx.get('bo_error'),
            'bo_cms_port':            Config.BO_CMS_PORT,

            # OS Layer
            'hostname':               os_data.get('hostname'),
            'free_memory_mb':         os_data.get('free_memory_mb'),
            'total_memory_mb':        os_data.get('total_memory_mb'),
            'disk_space':             str(os_data.get('disk_space', ''))[:500],
            'bo_services':            {k: v['status'] for k, v in os_data.get('bo_services', {}).items()},
            'bo_processes_running':   [p['name'] for p in os_data.get('bo_processes_running', [])],
            'java_processes':         str(os_data.get('java_processes', ''))[:300],

            # Network Layer
            'port_6405_cms':          net_data.get('port_6405_cms'),
            'port_8080_tomcat':       net_data.get('port_8080_tomcat'),
            'netstat_6405':           str(net_data.get('netstat_6405', ''))[:300],
            'ping_result':            str(net_data.get('ping', ''))[:300],
            'dns_result':             str(net_data.get('dns_lookup', ''))[:200],

            # Event Viewer Layer
            'windows_system_events':  str(evt_data.get('System', ''))[:600],
            'windows_app_events':     str(evt_data.get('Application', ''))[:600],
            'java_crash_dumps':       evt_data.get('java_crash_dumps', 'None found'),

            # BO Log Layer
            'bo_installed_locally':   log_data.get('bo_installed_here', False),
            'bo_dir_checked':         log_data.get('bo_dir_checked'),
            'bo_log_note':            log_data.get('note', ''),
            'logs_scanned_count':     len(log_data.get('logs_scanned', [])),
            'bo_error_categories':    log_data.get('categories', {}),
            'top_bo_errors':          log_data.get('errors_found', [])[:4],

            # DB Log Layer
            'db_logs_scanned':        len(db_data.get('logs_scanned', [])),
            'db_errors':              db_data.get('errors_found', [])[:3],

            # Correlation
            'correlation_chain':      ctx.get('correlation', {}).get('chain', []),
            'primary_fault_layer':    ctx.get('correlation', {}).get('primary_layer'),
            'confidence':             ctx.get('correlation', {}).get('confidence'),
        }

    # =========================================================================
    # FALLBACK — rule-based when AI is unavailable
    # =========================================================================

    def _fallback_report(self, ctx):
        log_data  = ctx.get('bo_logs', {})
        net_data  = ctx.get('network', {})
        os_data   = ctx.get('os', {})
        corr      = ctx.get('correlation', {})
        errors    = log_data.get('errors_found', [])
        connected = ctx.get('bo_connected', False)
        chain_str = ' → '.join(corr.get('chain', [])) or 'Unknown'
        host      = ctx.get('bo_attempted_host', Config.BO_CMS_HOST)

        if errors:
            top = errors[0]
            return {
                'title':        f"{top['category'].replace('_',' ').title()} in {top['log_file']}",
                'severity':     self._severity(top['category']),
                'error_message': top['match'],
                'log_file':     top['log_file'],
                'log_path':     top['log_path'],
                'error_timestamp': top.get('error_timestamp', 'unknown'),
                'category':     top['category'],
                'root_cause':   f"Pattern '{top['pattern']}' matched in {top['log_file']}. Context: {top['context'][:200]}",
                'failure_chain': chain_str,
                'evidence':     top['context'],
                'solution_steps': self._solutions(top['category']),
                'os_commands':  self._commands(top['category']),
                'owner':        self._owner(top['category']),
                'priority':     'P1' if top['category'] in ('server_crash','memory','disk') else 'P2',
                'estimated_resolution_time': '30 minutes',
            }

        # Connection refused
        port_status = net_data.get('port_6405_cms', 'UNKNOWN')
        cms         = os_data.get('bo_services', {}).get('BOEXI40', {})
        cms_status  = cms.get('status', 'UNKNOWN')

        if cms_status == 'STOPPED':
            cause    = f"BOEXI40 (CMS) service is STOPPED. Start it: sc start BOEXI40"
            priority = 'P1'
        elif cms_status == 'NOT_FOUND':
            cause    = (f"SAP BO services NOT FOUND on this machine. "
                        f"BO Commander is connecting to a REMOTE server at '{host}'. "
                        f"Log on to {host} and check the CMS service there.")
            priority = 'P1'
        elif port_status == 'CLOSED':
            cause    = f"Port {Config.BO_CMS_PORT} is CLOSED at '{host}'. CMS is not accepting connections."
            priority = 'P1'
        elif port_status == 'OPEN':
            cause    = f"Port {Config.BO_CMS_PORT} is OPEN at '{host}' but connection still refused — possible auth, SSL, or application-level error."
            priority = 'P2'
        else:
            cause    = f"Cannot connect to CMS at {host}:{Config.BO_CMS_PORT}. Investigate the BO server directly."
            priority = 'P1'

        return {
            'title':          'SAP BO Server Unreachable — Connection Refused',
            'severity':       'HIGH',
            'error_message':  'Connection refused — check host and port',
            'log_file':       'BO Commander / SAPBOConnection',
            'log_path':       'N/A',
            'error_timestamp': datetime.now().strftime("%H:%M:%S"),
            'category':       'connection',
            'root_cause':     cause,
            'failure_chain':  chain_str,
            'evidence':       (
                f"bo_session.connected=False | "
                f"Port {Config.BO_CMS_PORT}: {port_status} | "
                f"BOEXI40 service: {cms_status} | "
                f"BO installed locally: {log_data.get('bo_installed_here', False)}"
            ),
            'impact':         'All BO Commander features unavailable.',
            'prediction':     'Persistent until the CMS service is started and port is accessible.',
            'solution_steps': self._solutions('connection'),
            'os_commands': [
                f'ping {host}',
                'sc query BOEXI40',
                'sc query BOEXI40Tomcat',
                'sc start BOEXI40',
                f'netstat -ano | findstr :{Config.BO_CMS_PORT}',
                f'Test-NetConnection -ComputerName {host} -Port {Config.BO_CMS_PORT}',
            ],
            'owner':          'BO Admin / Network Team',
            'priority':       priority,
            'estimated_resolution_time': '15–30 minutes',
        }

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _cmd(self, command, timeout=None):
        """Execute OS command, return output string. Uses config timeout."""
        t = timeout or self.cmd_timeout
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=t
            )
            out = result.stdout.strip() or result.stderr.strip() or '(no output)'
            logger.debug(f"CMD [{command[:70]}] → {out[:80]}")
            return out
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout ({t}s): {command[:60]}")
            return f'timeout after {t}s'
        except Exception as e:
            return f'error: {e}'

    def _find_log(self, pattern):
        """Find most recent log file matching pattern in BOE_LOG_DIR."""
        try:
            files = glob.glob(os.path.join(self.bo_log_dir, pattern))
            return max(files, key=os.path.getmtime) if files else None
        except Exception:
            return None

    def _find_log_in(self, directory, pattern):
        """Find most recent log file matching pattern in a specific directory."""
        try:
            files = glob.glob(os.path.join(directory, pattern))
            return max(files, key=os.path.getmtime) if files else None
        except Exception:
            return None

    def _read_tail(self, path, lines=None):
        """Read last N lines of a file."""
        n = lines or self.log_tail
        try:
            with open(path, 'r', errors='ignore') as f:
                return ''.join(f.readlines()[-n:])
        except Exception:
            return 'Unable to read file'

    def _severity(self, cat):
        return {'server_crash':'CRITICAL','memory':'HIGH','disk':'HIGH',
                'database':'HIGH','connection':'HIGH','network':'MEDIUM',
                'authentication':'MEDIUM','report_error':'LOW'}.get(cat, 'MEDIUM')

    def _owner(self, cat):
        return {'server_crash':'BO Admin','memory':'OS Team','disk':'OS Team',
                'database':'Database Team','connection':'Network Team',
                'authentication':'Security Team','report_error':'BI Team',
                'network':'Network Team'}.get(cat, 'BO Admin')

    def _commands(self, cat):
        return {
            'connection': ['sc query BOEXI40', 'netstat -ano | findstr :6405', 'sc start BOEXI40'],
            'memory':     ['tasklist /FI "IMAGENAME eq java.exe"', 'sc stop BOEXI40Tomcat', 'sc start BOEXI40Tomcat'],
            'disk':       ['wmic logicaldisk get DeviceID,FreeSpace,Size', 'del /q /s %TEMP%\\*'],
            'database':   ['ping <db-server>', 'odbcad32.exe'],
            'server_crash': ['sc query BOEXI40', 'eventvwr.msc', 'sc start BOEXI40'],
        }.get(cat, ['sc query BOEXI40', 'eventvwr.msc'])

    def _solutions(self, cat):
        return {
            'connection': [
                f'On BO server: sc query BOEXI40 — check if CMS service is running',
                f'On BO server: netstat -ano | findstr :{Config.BO_CMS_PORT} — verify port is listening',
                f'If stopped: sc start BOEXI40 — start the CMS service',
                'Check Windows Firewall: ensure ports 6405 and 8080 are allowed',
                f'Verify BOE_INSTALL_DIR={Config.BOE_INSTALL_DIR} is correct in your .env file',
                f'Test connectivity: Test-NetConnection -ComputerName {Config.BO_CMS_HOST} -Port {Config.BO_CMS_PORT}',
            ],
            'memory': [
                'Check Java heap: find -Xmx value in tomcat/bin/setenv.bat',
                'View Java processes: tasklist /FI "IMAGENAME eq java.exe"',
                'Increase heap in setenv.bat: add -Xmx4096m to JAVA_OPTS',
                'Restart Tomcat: sc stop BOEXI40Tomcat && sc start BOEXI40Tomcat',
                'Set heap monitoring alert in CMC > Servers > [server] > Metrics',
            ],
            'disk': [
                'Check disk: wmic logicaldisk get DeviceID,FreeSpace,Size',
                f'Clean BO logs in: {Config.BOE_LOG_DIR}',
                'Delete old .glf files (> 30 days) from BO logging directory',
                'Set log rotation in CMC > Servers > [server] > Logging',
                'Add disk space or move logging dir to larger volume',
            ],
            'server_crash': [
                'Open Event Viewer: eventvwr.msc → Windows Logs → Application',
                f'Search for Java crash dumps: dir /s hs_err_pid*.log in {Config.BOE_INSTALL_DIR}',
                'Check disk space — full disk is a common crash cause',
                'Restart crashed service: sc start BOEXI40',
                'If recurring, collect logs and open SAP support ticket',
            ],
            'database': [
                'Test ODBC: odbcad32.exe → System DSN → Test Connection',
                'Verify DB server is online: ping <db-server>',
                'Check connection strings in CMC → Connections',
                'Review DB server error log',
                'Check for deadlocks or long-running queries',
            ],
        }.get(cat, ['Check BO logs', 'Check Windows Event Viewer', 'Contact SAP support'])

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def add_performance_datapoint(self, cpu, memory, disk):
        self.performance_history.append({
            'timestamp': datetime.now().isoformat(),
            'cpu': cpu, 'memory': memory, 'disk': disk,
        })
        if len(self.performance_history) > 100:
            self.performance_history.pop(0)

    def get_incidents(self, limit=50):
        return self.incidents[:limit]

    def clear_incidents(self):
        self.incidents = []
        logger.info("Incident history cleared")
