"""
agents/coordinator_agent.py  —  Multi-Agent Coordinator  v2.0
==============================================================
The Coordinator is the brain of the multi-agent system.
It receives a raw user message, parses it into a structured intent,
routes it to the correct specialist agent, and optionally plans
multi-step tasks.

Architecture:
    User Text
      → parse_intent() [regex + keyword heuristics + AI fallback]
      → route_intent() [picks SAPAgent / SystemAgent / MonitoringAgent]
      → agent.execute(intent, emit)
      → (optional) plan multi-step goal
      → stream results to UI

Multi-step task planning example:
    "fix failed reports"
      1. MonitoringAgent: health check
      2. SAPAgent: list failed instances
      3. SystemAgent: read error logs
      4. SAPAgent: retry failed schedules
      5. SAPAgent: verify no more failures
"""

import logging
import re
import time
import threading
from typing import Callable, Dict, List, Optional

from agents.base_agent import AgentResult
from agents.sap_agent import SAPAgent
from agents.system_agent import SystemAgent
from agents.monitoring_agent import MonitoringAgent

logger = logging.getLogger("Coordinator")

# ─────────────────────────────────────────────────────────────────────────────
#  Intent pattern table — 3-stage parsing
#  (pattern, action, param_group)
# ─────────────────────────────────────────────────────────────────────────────
_PATTERNS = [
    # Port checks — all natural language variants
    (r"\b(\d{2,5})\s+port\b",                           "check_port",       1),
    (r"\bport\s+(\d{2,5})\b",                           "check_port",       1),
    (r"\b(\d{2,5})\b.*\b(?:open|closed|blocked|listen)", "check_port",      1),
    (r"\bcheck\b.*\b(\d{2,5})\b.*\bport\b",             "check_port",       1),

    # Open report
    (r"\bopen\s+(?:the\s+)?(.+?)\s+(?:webi|report|wbi)\b", "open_report",  1),
    (r"\bopen\s+report\s+(.+)",                           "open_report",    1),
    (r"\b(?:launch|view|show)\s+(?:the\s+)?(.+?)\s+(?:report|webi)\b", "open_report", 1),

    # Disk space
    (r"\b(?:check\s+)?disk\s+(?:space|usage|check|full)\b", "disk_space",  None),
    (r"\bcheck\s+disk\b|\bhow\s+much\s+(?:disk|space)\b",   "disk_space",  None),
    (r"\bstorage\s+(?:space|usage|check)\b",                "disk_space",  None),

    # Logs
    (r"\b(?:show|read|tail|view|fetch)\s+(?:last\s+)?(\d+)?\s*lines?\s+(?:of\s+)?(?:the\s+)?(.+?)\s+log", "read_log", 2),
    (r"\b(?:show|read|view|tail)\s+(?:the\s+)?(.+?)\s+log\b", "read_log",  1),
    (r"\btomcat\s+log\b|\bcatalina\b",                      "read_log_tomcat", None),
    (r"\bbo\s+log\b|\bboe\s+log\b|\bbo\s+server\s+log\b",  "read_log_bo",  None),

    # Cache
    (r"\b(?:clear|clean|purge|delete)\s+(?:tomcat\s+)?(?:the\s+)?cache\b", "clear_cache", None),

    # Restart/service — tomcat first, then generic
    (r"\b(?:restart|reboot|reload)\s+(?:the\s+)?tomcat\b", "restart_tomcat", None),
    (r"\btomcat\s+(?:restart|reboot|reload)\b",            "restart_tomcat", None),
    (r"\b(?:restart|reboot)\s+(?:the\s+)?(.+?)\s+(?:service|server|process)\b", "restart_service", 1),
    (r"\bstop\s+and\s+start\s+(.+)",                       "restart_service", 1),

    # Server control (requires server ID)
    (r"\bstart\s+server\s+(\d+)\b",                        "start_server",  1),
    (r"\bstop\s+server\s+(\d+)\b",                         "stop_server",   1),
    (r"\brestart\s+server\s+(\d+)\b",                      "restart_server", 1),

    # BO lists
    (r"\b(?:list|show|get|display)\s+(?:all\s+)?users?\b", "list_users",   None),
    (r"\b(?:list|show|get|display)\s+(?:all\s+)?reports?\b", "list_reports", None),
    (r"\b(?:list|show|get|display)\s+(?:all\s+)?servers?\b", "list_servers", None),
    (r"\b(?:list|show|get|display)\s+(?:all\s+)?universes?\b", "list_universes", None),
    (r"\b(?:list|show|get|display)\s+(?:all\s+)?folders?\b", "list_folders", None),
    (r"\b(?:list|show|get|display)\s+(?:all\s+)?connections?\b", "check_db", None),

    # Failed / retry
    (r"\b(?:show|list|get|display)\s+failed\b",            "failed_instances", None),
    (r"\b(?:failed|broken)\s+(?:reports?|schedules?|jobs?|instances?)\b", "failed_instances", None),
    (r"\bwhat\s+(?:reports?|schedules?|jobs?)\s+(?:have\s+)?failed\b", "failed_instances", None),
    (r"\bretry\s+failed\b|\breschedule\s+failed\b|\brerun\s+failed\b", "retry_failed", None),

    # Purge instances
    (r"\b(?:delete|purge|clean)\s+(?:old\s+)?instances?\b", "purge_instances", None),
    (r"\bcleanup\s+instances?\b|\bpurge\s+history\b",       "purge_instances", None),

    # Health
    (r"\b(?:system\s+)?health\s*(?:check)?\b|\bfull\s+health\b", "health", None),
    (r"\boverall\s+status\b|\bhow\s+is\s+(?:the\s+)?(?:system|server|bo)\b", "health", None),
    (r"^status$|^health$|^check$",                          "health",       None),

    # Process check
    (r"\bcheck\s+(?:if\s+)?(?:the\s+)?(.+?)\s+(?:is\s+)?(?:running|alive|up)\b", "check_process", 1),
    (r"\bis\s+(?:the\s+)?(.+?)\s+(?:running|alive|up)\b",  "check_process", 1),

    # DB / connections
    (r"\b(?:check|test|verify)\s+(?:the\s+)?(?:db|database|connection)\b", "check_db", None),
    (r"\bdatabase\s+(?:connection|connectivity|status)\b",  "check_db",    None),

    # SSL
    (r"\b(?:configure|setup|enable)\s+(?:tomcat\s+)?ssl\b", "configure_ssl", None),
    (r"\bssl\s+(?:config|setup|cert)\b|\benable\s+https\b", "configure_ssl", None),

    # Slow report
    (r"\bwhy\s+(?:is\s+)?(?:my\s+)?(?:the\s+)?(.+?)\s+(?:report\s+)?slow\b", "analyse_slow", 1),
    (r"\bperformance\s+(?:issue|problem|check|analysis)\b", "analyse_slow", None),

    # Self-healing
    (r"\b(?:self.heal|auto.heal|fix\s+issues|fix\s+problems)\b", "self_heal", None),

    # Network check
    (r"\bcheck\s+(?:all\s+)?(?:network|ports|connectivity)\b", "check_network", None),

    # System info
    (r"\bsystem\s+info\b|\benv(?:ironment)?\s+info\b",     "system_info",  None),
    (r"\blist\s+(?:bo\s+)?services?\b",                    "list_services", None),

    # Help / intro
    (r"^(?:hi|hello|hey|help)\b",                          "help",         None),
    (r"\bwhat\s+can\s+you\s+do\b|\bcommands?\b",           "help",         None),
    (r"\bwho\s+are\s+you\b|\byour\s+name\b",               "intro",        None),
]

# ── Multi-step task plans ─────────────────────────────────────────────────────
_TASK_PLANS: Dict[str, List[str]] = {
    "fix_failed": ["health", "failed_instances", "retry_failed", "failed_instances"],
    "full_diagnosis": ["health", "check_network", "list_servers", "failed_instances",
                       "read_log_tomcat", "disk_space"],
    "morning_check": ["health", "list_servers", "failed_instances", "disk_space"],
    "server_restart": ["list_servers", "restart_tomcat", "health"],
}


def parse_intent(text: str) -> dict:
    """
    3-stage intent parser:
      1. Regex patterns (fast, handles 95%)
      2. Keyword heuristics (catches edge cases)
      3. Returns ai_freeform for the AI to handle
    """
    tl = text.lower().strip()

    # Stage 1: regex table
    for pattern, action, group in _PATTERNS:
        m = re.search(pattern, tl, re.IGNORECASE)
        if m:
            param = None
            if group:
                try:
                    param = m.group(group)
                    if param: param = param.strip()
                except IndexError:
                    pass
            return {"action": action, "param": param, "raw": text}

    # Stage 2: keyword heuristics
    port_m = re.search(r"\b(\d{2,5})\b", tl)
    if port_m and any(w in tl for w in ["port","open","closed","listen","8080","6405","443"]):
        return {"action": "check_port", "param": port_m.group(1), "raw": text}

    if re.search(r"\brestart\b|\breboot\b|\breload\b", tl):
        return {"action": "restart_tomcat" if "tomcat" in tl else "restart_service",
                "param": _extract_service_name(tl), "raw": text}

    if "failed" in tl or "failure" in tl:
        return {"action": "retry_failed" if "retry" in tl else "failed_instances",
                "param": None, "raw": text}

    if "log" in tl:
        return {"action": "read_log_tomcat" if "tomcat" in tl else
                          "read_log_bo"     if "bo" in tl else "read_log",
                "param": re.search(r"(\w+)\s+log", tl).group(1) if re.search(r"(\w+)\s+log", tl) else "boe",
                "raw": text}

    if any(w in tl for w in ["disk","space","storage","drive","full","gb"]):
        return {"action": "disk_space", "param": None, "raw": text}

    if any(w in tl for w in ["health","status","overview","all good","summary"]):
        return {"action": "health", "param": None, "raw": text}

    # Keyword routing for BO objects
    if re.search(r"\busers?\b", tl) and any(w in tl for w in ["list","show","all","get"]):
        return {"action": "list_users", "param": None, "raw": text}
    if re.search(r"\breports?\b", tl) and any(w in tl for w in ["list","show","all","get"]):
        return {"action": "list_reports", "param": None, "raw": text}
    if re.search(r"\bservers?\b", tl) and any(w in tl for w in ["list","show","all","get","running","status"]):
        return {"action": "list_servers", "param": None, "raw": text}

    # Check for multi-step task keywords
    if "fix" in tl and "failed" in tl:
        return {"action": "multi_step", "plan": "fix_failed", "raw": text}
    if "diagnos" in tl or "full check" in tl:
        return {"action": "multi_step", "plan": "full_diagnosis", "raw": text}
    if "morning" in tl and "check" in tl:
        return {"action": "multi_step", "plan": "morning_check", "raw": text}

    return {"action": "ai_freeform", "param": text, "raw": text}


def _extract_service_name(text: str) -> Optional[str]:
    m = re.search(r"(?:restart|reboot)\s+(?:the\s+)?([\w\s]+?)(?:\s+service|\s+server|$)", text)
    return m.group(1).strip() if m else None


class CoordinatorAgent:
    """
    Routes intents to the right specialist agent.
    Supports single-shot and multi-step planning.
    """

    def __init__(self):
        self._sap     = SAPAgent()
        self._system  = SystemAgent()
        self._monitor = MonitoringAgent()
        self._agents  = [self._sap, self._system, self._monitor]
        self._ai      = None
        self._lock    = threading.Lock()
        self._history: List[dict] = []

        # Try to load AI
        try:
            from ai.gemini_client import GeminiClient
            self._ai = GeminiClient()
        except Exception:
            pass

    # ── Start background monitoring ───────────────────────────────────────────

    def start_monitoring(self, ui_emit: Callable = None, auto_heal: bool = False):
        self._monitor.start_monitoring(ui_emit=ui_emit, auto_heal=auto_heal)

    def stop_monitoring(self):
        self._monitor.stop_monitoring()

    def get_alerts(self):
        return self._monitor.get_recent_alerts()

    # ── Route a single intent ─────────────────────────────────────────────────

    def route(self, text: str, emit: Callable[[str], None],
              done: Callable[[AgentResult], None] = None) -> None:
        """Parse text, route to right agent, execute async."""
        intent = parse_intent(text)
        self._history.append({"text": text, "intent": intent})

        # ── Multi-step plan ───────────────────────────────────────────────────
        if intent.get("action") == "multi_step":
            plan_name = intent.get("plan","")
            steps = _TASK_PLANS.get(plan_name, [])
            if steps:
                def _run_plan():
                    emit(f"📋  Executing multi-step plan: {plan_name}\n"
                         f"   Steps: {' → '.join(steps)}\n")
                    results = []
                    for i, step in enumerate(steps, 1):
                        emit(f"\n{'─'*40}\n  Step {i}/{len(steps)}: {step}\n")
                        sub_intent = {"action": step, "param": None, "raw": text}
                        agent = self._find_agent(sub_intent)
                        if agent:
                            r = agent.execute(sub_intent, emit)
                            results.append(r)
                            if not r.success and step in ("health", "failed_instances"):
                                pass  # Continue even on non-critical failures
                    emit(f"\n✅  Plan complete. {sum(1 for r in results if r.success)}/{len(results)} steps succeeded.")
                    if done:
                        done(AgentResult(True, f"Plan {plan_name} complete", action="multi_step"))

                threading.Thread(target=_run_plan, daemon=True).start()
                return

        # ── Help / Intro ──────────────────────────────────────────────────────
        if intent["action"] == "help":
            self._show_help(emit)
            if done: done(AgentResult(True, "Help shown", action="help"))
            return

        if intent["action"] == "intro":
            self._show_intro(emit)
            if done: done(AgentResult(True, "Intro shown", action="intro"))
            return

        # ── Route to specialist agent ─────────────────────────────────────────
        agent = self._find_agent(intent)
        if agent:
            agent.run_async(intent, emit, done_callback=done)
            return

        # ── AI freeform fallback ──────────────────────────────────────────────
        self._ai_freeform(intent, emit, done)

    def _find_agent(self, intent: dict) -> Optional[BaseAgent]:
        for agent in self._agents:
            if agent.can_handle(intent):
                return agent
        return None

    # ── AI freeform ───────────────────────────────────────────────────────────

    def _ai_freeform(self, intent: dict, emit: Callable,
                     done: Callable = None):
        raw = intent.get("raw","")

        def _run():
            emit("🤖  Analysing your request…")
            ai_response = ""

            if self._ai:
                try:
                    from core.sapbo_connection import bo_session
                    ctx = (f"SAP BO: {'connected' if bo_session.connected else 'disconnected'} "
                           f"to {bo_session.cms_details.get('host','?')}")
                    ai_response = self._ai.ask(
                        f"You are MultiBOT — autonomous SAP BO admin AI agent.\n"
                        f"Context: {ctx}\n\nUser: '{raw}'\n\n"
                        f"Give specific, actionable SAP BO admin guidance. Max 200 words."
                    )
                    if ai_response and ai_response.startswith("[RATE_LIMIT"):
                        emit("⚠  AI rate limit — using local intelligence.\n")
                        ai_response = ""
                except Exception as e:
                    logger.debug(f"AI call failed: {e}")

            if ai_response and len(ai_response.strip()) > 10:
                emit(ai_response)
            else:
                # Smart keyword fallback
                tl = raw.lower()
                port_m = re.search(r"\b(\d{2,5})\b", tl)
                if port_m and any(w in tl for w in ["port","open","closed","network"]):
                    sub = {"action":"check_port","param":port_m.group(1),"raw":raw}
                    self._system.execute(sub, emit)
                elif any(w in tl for w in ["tomcat","service","restart"]):
                    sub = {"action":"check_process","param":"tomcat","raw":raw}
                    self._system.execute(sub, emit)
                else:
                    emit(f"⚠  I didn't recognise: '{raw}'\n\n"
                         "Try:\n  • check port 8080\n  • open <report name>\n"
                         "  • disk space\n  • list servers\n  • system health\n"
                         "  • show failed reports\n  • retry failed\n"
                         "  • restart tomcat\n  • show tomcat log\n"
                         "  • fix failed reports  (multi-step)\n"
                         "  • full diagnosis  (multi-step)")

            if done:
                done(AgentResult(True, "Responded", action="ai_freeform"))

        threading.Thread(target=_run, daemon=True).start()

    # ── Help text ─────────────────────────────────────────────────────────────

    def _show_help(self, emit: Callable):
        emit(
            "👋  MultiBOT v3.0 — Autonomous SAP BO + OS Agent\n\n"
            "━━━  SAP BO Operations  ━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "  📊  list reports              — all BO reports\n"
            "  🌐  open <name> report        — open in browser\n"
            "  👥  list users                — all BO users\n"
            "  🖥  list servers              — server status + failures\n"
            "  🌐  list universes            — BO universe list\n"
            "  🔴  show failed reports       — failed schedules\n"
            "  🔁  retry failed              — reschedule all failed\n"
            "  🗑  delete old instances      — purge run history\n"
            "  🔄  restart server <ID>       — via Java Admin SDK\n"
            "  🔄  start server <ID>         — via Java Admin SDK\n"
            "\n━━━  OS & System  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "  🔌  check port 8080           — is port open?\n"
            "  💽  disk space                — disk usage\n"
            "  📋  show tomcat log           — catalina.out\n"
            "  📋  show bo log               — BO server log\n"
            "  🧹  clear cache               — Tomcat work/temp\n"
            "  🔄  restart tomcat            — service restart\n"
            "  🔍  is tomcat running?        — process check\n"
            "  🌐  check network             — all BO ports\n"
            "  🔐  configure ssl             — Tomcat SSL guide\n"
            "\n━━━  Health & Monitoring  ━━━━━━━━━━━━━━━━━━━━━━\n"
            "  🏥  system health             — full snapshot\n"
            "  🐛  why is <report> slow?     — perf analysis\n"
            "  🔧  self heal                 — fix detected issues\n"
            "\n━━━  Multi-Step Plans  ━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "  🎯  fix failed reports        — diagnose + retry\n"
            "  🎯  full diagnosis            — complete system scan\n"
            "  🎯  morning check             — daily health report\n"
        )

    def _show_intro(self, emit: Callable):
        from core.sapbo_connection import bo_session
        import platform
        emit(
            f"🤖  MultiBOT v3.0 — Autonomous SAP BO Administration Agent\n\n"
            f"Architecture:\n"
            f"  CoordinatorAgent  — routes your commands\n"
            f"  SAPAgent          — SAP BO REST API + Java SDK\n"
            f"  SystemAgent       — OS, services, logs, ports\n"
            f"  MonitoringAgent   — continuous health + self-healing\n\n"
            f"Connected: {bo_session.cms_details.get('user','')}@"
            f"{bo_session.cms_details.get('host','')}\n"
            f"OS: {platform.system()} {platform.release()}\n"
            f"Java SDK: available  (bridges/java_admin_sdk.py)\n"
            f"Memory: persistent  (memory/knowledge_base.py)\n\n"
            f"Type 'help' for all commands."
        )
