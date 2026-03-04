"""
core/banner.py
Console startup banner for BO Commander.
Prints ASCII logo, developer credits, license status, system info.
"""
import platform, socket
from datetime import datetime

# ANSI colours
CY = "\033[96m"; BL = "\033[94m"; GR = "\033[92m"
YL = "\033[93m"; WH = "\033[97m"; GY = "\033[90m"
RD = "\033[91m"; BD = "\033[1m";  RS = "\033[0m"

LOGO = f"""{CY}{BD}
  ██████╗  ██████╗      ██████╗ ██████╗ ███╗   ███╗███╗   ███╗ █████╗ ███╗   ██╗██████╗ ███████╗██████╗
  ██╔══██╗██╔═══██╗    ██╔════╝██╔═══██╗████╗ ████║████╗ ████║██╔══██╗████╗  ██║██╔══██╗██╔════╝██╔══██╗
  ██████╔╝██║   ██║    ██║     ██║   ██║██╔████╔██║██╔████╔██║███████║██╔██╗ ██║██║  ██║█████╗  ██████╔╝
  ██╔══██╗██║   ██║    ██║     ██║   ██║██║╚██╔╝██║██║╚██╔╝██║██╔══██║██║╚██╗██║██║  ██║██╔══╝  ██╔══██╗
  ██████╔╝╚██████╔╝    ╚██████╗╚██████╔╝██║ ╚═╝ ██║██║ ╚═╝ ██║██║  ██║██║ ╚████║██████╔╝███████╗██║  ██║
  ╚═════╝  ╚═════╝      ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═════╝ ╚══════╝╚═╝  ╚═╝
{RS}"""

W = 102

def _ln():  return f"{GY}{'─' * W}{RS}"
def _pad(s): return f"  {s}"


def print_banner(activated: bool = False, user_name: str = "",
                 machine_key: str = "", web_port: int = 8765):
    """Print the full startup banner."""
    print(LOGO)
    print(_ln())
    print(_pad(f"{BD}{WH}BO Commander{RS}  {GY}v1.0.0{RS}  {BL}│{RS}  "
               f"{CY}Intelligent SAP BusinessObjects Control Center{RS}"))
    print(_pad(f"{GY}AI-Powered Administration · Monitoring · Diagnostics · Security · Housekeeping{RS}"))
    print(_ln())

    # ── Developer block ───────────────────────────────────────────────────────
    print()
    print(_pad(f"{YL}{BD}╔══ DEVELOPED BY ══════════════════════════════════════════════════════════════╗{RS}"))
    print(_pad(f"{YL}{BD}║{RS}  {WH}{BD}Sai Teja Guddanti{RS:<55}{YL}{BD}║{RS}"))
    print(_pad(f"{YL}{BD}║{RS}  {GY}SAP BusinessObjects Developer & Tool Architect{RS:<42}{YL}{BD}║{RS}"))
    print(_pad(f"{YL}{BD}║{RS}  {BL}✉  saitejaguddanti999@gmail.com{RS:<47}{YL}{BD}║{RS}"))
    print(_pad(f"{YL}{BD}║{RS}  {CY}🔗 https://www.linkedin.com/in/sai-teja-628082288{RS:<29}{YL}{BD}║{RS}"))
    print(_pad(f"{YL}{BD}║{RS}  {GY}© 2025 Sai Teja Guddanti. All rights reserved.{RS:<41}{YL}{BD}║{RS}"))
    print(_pad(f"{YL}{BD}╚══════════════════════════════════════════════════════════════════════════════╝{RS}"))

    # ── License block ─────────────────────────────────────────────────────────
    print()
    print(_pad(f"{YL}{BD}License Status:{RS}"))
    if activated and user_name:
        print(_pad(f"  {GR}✔  ACTIVATED   {GY}— registered to: {WH}{BD}{user_name}{RS}"))
    else:
        print(_pad(f"  {YL}◎  TRIAL MODE  {GY}— open the app and enter your key to activate{RS}"))
        if machine_key:
            print(_pad(f"  {GY}Your machine key: {WH}{machine_key}{RS}"))

    # ── System info ───────────────────────────────────────────────────────────
    print()
    print(_pad(f"{YL}{BD}System:{RS}"))
    print(_pad(f"  {GY}OS      : {WH}{platform.system()} {platform.release()}{RS}"))
    print(_pad(f"  {GY}Host    : {WH}{socket.gethostname()}{RS}"))
    print(_pad(f"  {GY}Python  : {WH}{platform.python_version()}{RS}"))
    print(_pad(f"  {GY}Started : {WH}{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}{RS}"))

    # ── Launch info ───────────────────────────────────────────────────────────
    print()
    print(_ln())
    print(_pad(f"  {CY}⚡  Loading GUI ...{RS}"))
    print(_pad(f"  {BL}📖  Product info & features → {WH}http://localhost:{web_port}{RS}"))
    print(_pad(f"  {YL}⚠   {GY}AI tools may make mistakes — always verify critical actions before applying.{RS}"))
    print(_ln())
    print()
