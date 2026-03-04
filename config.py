import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    APP_NAME = "BO Commander"
    VERSION  = "2.0"
    TAGLINE  = "Intelligent SAP BO Control Center"

    # =========================================================================
    # UI COLOR PALETTE — COMPLETE
    # All color keys used anywhere in the GUI pages are defined here.
    # =========================================================================
    COLORS = {
        # ── Primary palette ──────────────────────────────────────────────────
        'primary':          '#3B82F6',   # Blue
        'primary_hover':    '#2563EB',
        'secondary':        '#8B5CF6',   # Purple
        'accent':           '#10B981',   # Green

        # ── Accent colors (used by page headers) ─────────────────────────────
        'accent_blue':      '#3B82F6',   # Blue  — sentinel, security_analyzer, cleanup_hub
        'accent_green':     '#10B981',   # Green — users, promotion
        'accent_purple':    '#8B5CF6',   # Purple
        'accent_orange':    '#F59E0B',   # Orange / Amber
        'accent_red':       '#EF4444',   # Red
        'accent_teal':      '#14B8A6',   # Teal
        'accent_cyan':      '#06B6D4',   # Cyan
        'accent_pink':      '#EC4899',   # Pink
        'accent_indigo':    '#6366F1',   # Indigo
        'accent_yellow':    '#EAB308',   # Yellow

        # ── Background shades ─────────────────────────────────────────────────
        'bg_primary':       '#0F172A',   # Deep Navy
        'bg_secondary':     '#1E293B',   # Slate
        'bg_tertiary':      '#334155',   # Lighter Slate
        'bg_card':          '#1E293B',
        'bg_hover':         '#2D3F55',
        'bg_input':         '#0F172A',
        'bg_sidebar':       '#0F172A',
        'bg_header':        '#1E293B',

        # ── Text ──────────────────────────────────────────────────────────────
        'text_primary':     '#F1F5F9',
        'text_secondary':   '#94A3B8',
        'text_muted':       '#64748B',
        'text_accent':      '#3B82F6',

        # ── Status / semantic ─────────────────────────────────────────────────
        'success':          '#10B981',
        'success_hover':    '#059669',
        'warning':          '#F59E0B',
        'warning_hover':    '#D97706',
        'danger':           '#EF4444',
        'danger_hover':     '#DC2626',
        'info':             '#3B82F6',
        'info_hover':       '#2563EB',

        # ── Borders / separators ──────────────────────────────────────────────
        'border':           '#334155',
        'border_light':     '#475569',
        'divider':          '#1E293B',

        # ── Server status colors ──────────────────────────────────────────────
        'running':          '#10B981',
        'stopped':          '#EF4444',
        'unknown':          '#94A3B8',
        'degraded':         '#F59E0B',

        # ── Chart / graph colors ──────────────────────────────────────────────
        'chart_1':          '#3B82F6',
        'chart_2':          '#10B981',
        'chart_3':          '#8B5CF6',
        'chart_4':          '#F59E0B',
        'chart_5':          '#EF4444',
    }

    FONTS = {
        'header':       ('Segoe UI', 24, 'bold'),
        'sub_header':   ('Segoe UI', 18, 'bold'),
        'section':      ('Segoe UI', 14, 'bold'),
        'body':         ('Segoe UI', 12),
        'small':        ('Segoe UI', 11),
        'mono':         ('Consolas', 11),
        'mono_small':   ('Consolas', 10),
    }

    # =========================================================================
    # SAP BO CMS CONNECTION
    # =========================================================================
    BO_CMS_HOST   = os.getenv("BO_CMS_HOST",   "localhost")
    BO_CMS_PORT   = os.getenv("BO_CMS_PORT",   "6405")
    BO_AUTH_TYPE  = os.getenv("BO_AUTH_TYPE",  "secEnterprise")
    BO_ADMIN_USER = os.getenv("BO_ADMIN_USER", "Administrator")
    BO_ADMIN_PASS = os.getenv("BO_ADMIN_PASS", "")

    # =========================================================================
    # SAP BO INSTALL PATH
    # =========================================================================
    BOE_INSTALL_DIR    = os.getenv("BOE_INSTALL_DIR",   r"D:\SAP BO\SAP BO")
    BOE_LOG_SUBDIR     = os.getenv("BOE_LOG_SUBDIR",    r"SAP BusinessObjects Enterprise XI 4.0\logging")
    BOE_TOMCAT_SUBDIR  = os.getenv("BOE_TOMCAT_SUBDIR", r"tomcat\logs")

    # ── Derived paths ─────────────────────────────────────────────────────────
    BOE_LOG_DIR     = os.path.join(BOE_INSTALL_DIR, BOE_LOG_SUBDIR)
    BOE_TOMCAT_DIR  = os.path.join(BOE_INSTALL_DIR, BOE_TOMCAT_SUBDIR)
    BOE_TOMCAT_CONF = os.path.join(BOE_INSTALL_DIR, r"tomcat\conf")
    BOE_TOMCAT_BIN  = os.path.join(BOE_INSTALL_DIR, r"tomcat\bin")
    BOE_TOMCAT_LOG  = os.path.join(BOE_INSTALL_DIR, BOE_TOMCAT_SUBDIR, "catalina.out")
    BOE_SETENV_BAT  = os.path.join(BOE_INSTALL_DIR, r"tomcat\bin\setenv.bat")
    BOE_SERVER_XML  = os.path.join(BOE_INSTALL_DIR, r"tomcat\conf\server.xml")

    BOE_ENTERPRISE_DIR = os.path.join(
        BOE_INSTALL_DIR,
        r"SAP BusinessObjects Enterprise XI 4.0\win64_x64\sap_bobj\enterprise_xi40"
    )
    BOE_SERVERS_XML  = os.path.join(BOE_ENTERPRISE_DIR, "servers.xml")
    BOE_NODES_XML    = os.path.join(BOE_ENTERPRISE_DIR, "nodes.xml")
    BOE_INSTALL_LOGS = os.path.join(BOE_INSTALL_DIR, r"InstallData\logs")
    BOE_WDEPLOY_LOGS = os.path.join(
        BOE_INSTALL_DIR,
        r"SAP BusinessObjects Enterprise XI 4.0\wdeploy"
    )
    BOE_SERVERJAVA   = os.path.join(BOE_INSTALL_DIR, "serverjava.ini")

    _extra_raw     = os.getenv("EXTRA_LOG_DIRS", "")
    EXTRA_LOG_DIRS = [p.strip() for p in _extra_raw.split(";") if p.strip()]

    # =========================================================================
    # DATABASE LOG PATHS
    # =========================================================================
    DB_LOGS = {
        "SQL Server":   os.getenv("MSSQL_LOG_PATH",
                            r"C:\Program Files\Microsoft SQL Server\MSSQL15.MSSQLSERVER\MSSQL\Log\ERRORLOG"),
        "Oracle":       os.getenv("ORACLE_LOG_PATH",      r"C:\oracle\diag\rdbms"),
        "HANA":         os.getenv("HANA_LOG_PATH",        ""),
        "SQL Anywhere": os.getenv("SQLANYWHERE_LOG_PATH", r"C:\ProgramData\SAP\SQLAnywhere"),
    }

    AUDIT_DB = {
        "server":   os.getenv("AUDIT_DB_SERVER", "localhost"),
        "name":     os.getenv("AUDIT_DB_NAME",   "BOE43_Audit"),
        "user":     os.getenv("AUDIT_DB_USER",   "dba"),
        "password": os.getenv("AUDIT_DB_PASS",   ""),
    }

    # =========================================================================
    # WINDOWS OS PATHS
    # =========================================================================
    WINDOWS_TEMP_DIR = os.getenv("WINDOWS_TEMP_DIR", r"C:\Windows\Temp")
    _crash_raw       = os.getenv("JAVA_CRASH_SEARCH_DIRS", "C:\\;D:\\")
    JAVA_CRASH_DIRS  = [p.strip() for p in _crash_raw.split(";") if p.strip()]

    # =========================================================================
    # SAP BO WINDOWS SERVICES
    # =========================================================================
    BO_SERVICES = {
        "BOEXI40":                   "CMS — Central Management Server",
        "BOEXI40Tomcat":             "Tomcat — Web Application Server (CMC / BI Launch Pad)",
        "BOEXI40SIA":                "SIA — Server Intelligence Agent",
        "BOEXI40CMS":                "CMS — alternate service name",
        "BOEXI40APS":                "APS — Adaptive Processing Server",
        "BOEXI40WebIntelligence":    "WebI Processing Server",
        "BOEXI40CrystalReports":     "Crystal Reports Processing Server",
        "BOEXI40ConnectionServer":   "Connection Server",
        "BOEXI40EventServer":        "Event Server",
        "BOEXI40CacheServer":        "Cache Server",
        "BOEXI40OutputFRS":          "Output File Repository Server",
        "BOEXI40InputFRS":           "Input File Repository Server",
        "BOEXI40DestinationJob":     "Destination Job Server",
        "BOEXI40ProgramJob":         "Program Job Server",
        "BOEXI40ListOfValues":       "List of Values Job Server",
        "BOEXI40Auditing":           "Auditing Server",
    }

    # =========================================================================
    # SAP BO PROCESSES
    # =========================================================================
    BO_PROCESSES = [
        "java.exe", "javaw.exe",
        "tomcat9.exe", "tomcat8.exe", "tomcat.exe", "wacs.exe",
        "cms.exe", "sia.exe", "ccm.exe",
        "JobServer.exe", "JobServerChild.exe",
        "AdaptiveProcessingServer.exe", "WIReportServer.exe",
        "ConnectionServer.exe", "ConnectionServer32.exe",
        "EventServer.exe", "fileserver.exe",
        "crproc.exe", "crcache.exe", "crystalras.exe", "crpe32.exe",
        "dbsrv17.exe", "dbsrv16.exe", "dbeng17.exe", "dbeng16.exe",
        "wdeploy.exe", "cmsdbsetup.exe", "ImportWizard.exe", "lcmcli.exe",
    ]

    # =========================================================================
    # SAP BO LOG FILE PATTERNS
    # =========================================================================
    BO_LOG_PATTERNS = {
        "CMS":           "*.cms.*.glf",
        "SIA":           "*_SIA_*.log",
        "APS":           "*AdaptiveProcessingServer*.log",
        "WebI":          "*WebIntelligenceProcessingServer*.log",
        "Crystal":       "*CrystalReportsProcessingServer*.log",
        "ConnectionSvr": "*ConnectionServer*.log",
        "EventServer":   "*EventServer*.log",
        "CacheServer":   "*CacheServer*.log",
        "Auditing":      "*AuditingServer*.log",
        "FRS_Output":    "*OutputFileRepositoryServer*.log",
        "FRS_Input":     "*InputFileRepositoryServer*.log",
        "DestJob":       "*DestinationJobServer*.log",
        "ProgramJob":    "*ProgramJobServer*.log",
        "ListOfValues":  "*ListOfValuesJobServer*.log",
        "WirePort":      "*WirePortServer*.glf",
        "GLF_All":       "*.glf",
        "LOG_All":       "*.log",
    }

    @classmethod
    def get_critical_log_files(cls):
        return {
            "Tomcat_Catalina":   os.path.join(cls.BOE_TOMCAT_DIR, "catalina.out"),
            "Tomcat_Stdout":     os.path.join(cls.BOE_TOMCAT_DIR, "stdout.log"),
            "Tomcat_Stderr":     os.path.join(cls.BOE_TOMCAT_DIR, "stderr.log"),
            "Servers_XML":       cls.BOE_SERVERS_XML,
            "Nodes_XML":         cls.BOE_NODES_XML,
            "Tomcat_Server_XML": cls.BOE_SERVER_XML,
            "Setenv_BAT":        cls.BOE_SETENV_BAT,
        }

    # =========================================================================
    # PORTS
    # =========================================================================
    BO_PORTS = {
        6405: "WACS HTTP / REST API / LCM",
        6406: "WACS HTTPS",
        8080: "Tomcat HTTP (CMC / BI Launch Pad)",
        8443: "Tomcat HTTPS",
        6400: "CMS",
        6401: "Name Server / Input FRS",
        6402: "Event Server",
        6403: "Output FRS",
        6410: "SIA",
        8005: "Tomcat Shutdown",
        8009: "Tomcat AJP",
        1433: "SQL Server",
        1521: "Oracle",
        30015: "SAP HANA",
        2638: "SQL Anywhere",
    }

    # =========================================================================
    # MONITORING
    # =========================================================================
    MONITOR_CONFIG = {
        'interval':       int(os.getenv("MONITOR_INTERVAL_SECONDS", "60")),
        'mem_threshold':  float(os.getenv("MONITOR_MEM_THRESHOLD",  "85")),
        'cpu_threshold':  float(os.getenv("MONITOR_CPU_THRESHOLD",  "90")),
        'disk_threshold': float(os.getenv("MONITOR_DISK_THRESHOLD", "90")),
        'urls': {
            'CMC': os.getenv("MONITOR_URL_CMC", "http://localhost:8080/BOE/CMC"),
            'BI':  os.getenv("MONITOR_URL_BI",  "http://localhost:8080/BOE/BI"),
        },
        'processes': BO_PROCESSES,
    }

    # =========================================================================
    # AI
    # =========================================================================
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    AI_PROVIDER    = os.getenv("AI_PROVIDER", "GEMINI").upper()

    # =========================================================================
    # AI SENTINEL
    # =========================================================================
    SENTINEL_CONFIG = {
        'log_tail_lines':    int(os.getenv("SENTINEL_LOG_TAIL_LINES",  "500")),
        'cmd_timeout':       int(os.getenv("SENTINEL_CMD_TIMEOUT",      "20")),
        'scan_event_viewer': os.getenv("SENTINEL_SCAN_EVENT_VIEWER",   "true").lower() == "true",
        'scan_db_logs':      os.getenv("SENTINEL_SCAN_DB_LOGS",        "true").lower() == "true",
        'scan_java_crashes': os.getenv("SENTINEL_SCAN_JAVA_CRASHES",   "true").lower() == "true",
    }

    # =========================================================================
    # EVIDENCE PRIORITY MAP
    # =========================================================================
    EVIDENCE_PRIORITY = {
        'cms_down':       ['servers.xml', 'cms*.glf', 'SQL Server ERRORLOG', 'Event Viewer Application'],
        'tomcat_down':    ['catalina.out', 'server.xml', 'setenv.bat', 'Event Viewer Application'],
        'authentication': ['cms*.glf', 'Event Viewer Security', 'sia*.log'],
        'memory':         ['java_processes', 'setenv.bat', 'hs_err_pid*.log', 'cms*.glf'],
        'database':       ['SQL Server ERRORLOG', 'connectionserver*.log', 'servers.xml'],
        'report_failure': ['WebI*.log', 'Crystal*.log', 'cms*.glf', 'FRS*.log'],
        'disk_full':      ['disk_space', 'catalina.out'],
        'network':        ['port_checks', 'netstat', 'ConnectionServer*.log'],
    }
