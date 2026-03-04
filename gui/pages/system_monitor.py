"""
gui/pages/system_monitor.py
Background OS System Monitor per SAP BO PAM 4.2/4.3/4.4.
Checks: Firewall (must be OFF), BO services, BO processes,
        required ports, disk space, Java version.
Auto-refreshes every 60s.
"""

import re
import time
import socket
import shutil
import threading
import subprocess
import customtkinter as ctk
from config import Config
from core.sapbo_connection import bo_session
from datetime import datetime

C = Config.COLORS

BO_SERVICES = [
    'SAPBOBJEnterpriseXI40',
    'SAPBOBJ Enterprise XI 4.0 Tomcat',
    'SAPHostControl',
]

BO_PROCESSES = [
    'java.exe', 'BOEXIRd.exe', 'CrystalProcessing.exe',
    'DpMonitor.exe', 'SLPBroker.exe', 'FMSHandler.exe',
    'RSProcMgr.exe', 'AdaptiveJobServer.exe',
    'AdaptiveProcessingServer.exe', 'ConnectionServer.exe',
    'EventServer.exe', 'InputFileServer.exe', 'OutputFileServer.exe',
]

REQUIRED_PORTS = [
    (6400, 'CMS Name Server'), (6405, 'CMS'),
    (8080, 'BI Launchpad HTTP'), (8443, 'Tomcat HTTPS'),
    (6410, 'SIA'), (6411, 'CMS Admin'),
]

STATUS_COLORS = {
    'OK': '#10B981', 'WARNING': '#F59E0B',
    'ERROR': '#EF4444', 'INFO': '#3B82F6',
}


def _cmd(command):
    try:
        r = subprocess.run(command, shell=True, capture_output=True,
                           text=True, timeout=10)
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return str(e)


def _check_firewall():
    out = _cmd('netsh advfirewall show allprofiles state')
    active = any('STATE' in l.upper() and 'ON' in l.upper()
                 for l in out.splitlines())
    return {
        'name': 'Windows Firewall',
        'status': 'WARNING' if active else 'OK',
        'detail': ('Firewall ON — PAM requires DISABLED during BO install/patching'
                   if active else 'Firewall OFF — PAM-compliant for install/patch'),
    }


def _check_services():
    results = []
    for svc in BO_SERVICES:
        out = _cmd(f'sc query "{svc}"')
        if 'does not exist' in out.lower() or 'FAILED' in out:
            st, dt = 'INFO', f'Not installed'
        elif 'RUNNING' in out.upper():
            st, dt = 'OK', 'Running'
        elif 'STOPPED' in out.upper():
            st, dt = 'ERROR', 'STOPPED'
        else:
            st, dt = 'INFO', 'Unknown state'
        results.append({'name': svc, 'status': st, 'detail': dt})
    return results


def _check_processes():
    out = _cmd('tasklist /FO CSV /NH')
    running = {}
    for line in out.splitlines():
        parts = line.strip('"').split('","')
        if len(parts) >= 5:
            pname = parts[0].lower()
            try:
                running[pname] = int(parts[4].replace(',','').replace(' K','').strip()) // 1024
            except Exception:
                running[pname] = 0
    results = []
    for proc in BO_PROCESSES:
        mem = running.get(proc.lower())
        if mem is not None:
            heap_warn = proc == 'java.exe' and mem > 3000
            st = 'WARNING' if heap_warn else 'OK'
            dt = f'Running — {mem} MB' + (' (high memory — check JVM heap)' if heap_warn else '')
        else:
            st, dt = 'INFO', 'Not running'
        results.append({'name': proc, 'status': st, 'detail': dt})
    return results


def _check_ports(host='localhost'):
    results = []
    for port, label in REQUIRED_PORTS:
        try:
            s = socket.create_connection((host, port), timeout=2)
            s.close()
            st, dt = 'OK', f'Open'
        except (ConnectionRefusedError, OSError):
            st, dt = 'ERROR', f'CLOSED — {label} may be down'
        except Exception as e:
            st, dt = 'WARNING', f'Check error: {e}'
        results.append({'name': f'{label} :{port}', 'status': st, 'detail': dt})
    return results


def _check_disk():
    try:
        total, used, free = shutil.disk_usage('C:\\')
        fg = free / (1024**3)
        tg = total / (1024**3)
        pct = free / total * 100
        st = 'ERROR' if pct < 10 else ('WARNING' if pct < 20 else 'OK')
        dt = f'{fg:.1f} GB free of {tg:.0f} GB ({pct:.0f}%)'
    except Exception as e:
        st, dt = 'INFO', str(e)
    return {'name': 'Disk Space (C:\\)', 'status': st, 'detail': dt}


def _check_java():
    out = _cmd('java -version')
    if 'version' in out.lower():
        m = re.search(r'"([^"]+)"', out)
        ver = m.group(1) if m else out.split('\n')[0]
        ok = any(x in ver for x in ('1.8', '11.', '11 ', '17.'))
        return {'name': 'Java Version', 'status': 'OK' if ok else 'WARNING',
                'detail': f'Java {ver} — PAM supports JDK 8/11/17'}
    return {'name': 'Java Version', 'status': 'INFO', 'detail': 'java not found in PATH'}


class SystemMonitorPage(ctk.CTkFrame):

    def __init__(self, parent):
        super().__init__(parent, fg_color=C['bg_primary'], corner_radius=0)

        top = ctk.CTkFrame(self, fg_color='transparent', height=52)
        top.pack(fill='x', padx=20, pady=(15, 0))
        top.pack_propagate(False)

        ctk.CTkLabel(top, text='🖥  System Monitor',
                     font=('Segoe UI', 22, 'bold'),
                     text_color=C['text_primary']).pack(side='left')

        ctk.CTkButton(top, text='⟳ Scan Now', width=100, height=32,
                      command=self._scan).pack(side='right')

        self._auto_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(top, text='Auto refresh (60s)',
                        variable=self._auto_var,
                        font=('Segoe UI', 11),
                        text_color=C['text_secondary']).pack(side='right', padx=10)

        self._status = ctk.CTkLabel(top, text='',
                                    font=('Segoe UI', 11),
                                    text_color=C['text_secondary'])
        self._status.pack(side='right', padx=12)

        ctk.CTkLabel(self,
                     text='OS health checks per SAP BO PAM 4.2/4.3/4.4: '
                          'firewall, services, processes, ports, disk, Java.',
                     font=('Segoe UI', 11),
                     text_color=C['text_secondary']).pack(anchor='w', padx=22, pady=(2, 8))

        self._summary_frame = ctk.CTkFrame(self, fg_color='transparent')
        self._summary_frame.pack(fill='x', padx=15, pady=(0, 8))

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=C['bg_secondary'],
                                             corner_radius=8)
        self.scroll.pack(fill='both', expand=True, padx=15, pady=(0, 15))

        ctk.CTkLabel(self.scroll, text='Click "Scan Now" to check OS health.',
                     font=('Segoe UI', 12),
                     text_color=C['text_secondary']).pack(pady=40)

        self.after(1500, self._scan)
        self.after(2000, self._auto_loop)

    def _auto_loop(self):
        if self._auto_var.get():
            self._scan()
        self.after(60_000, self._auto_loop)

    def _scan(self):
        self._status.configure(text='Scanning…')
        threading.Thread(target=self._do_scan, daemon=True).start()

    def _do_scan(self):
        host = 'localhost'
        try:
            if bo_session.connected:
                host = bo_session.cms_details.get('host', 'localhost')
        except Exception:
            pass

        sections = {
            'Firewall (PAM Requirement)': [_check_firewall()],
            'Disk & Java':                [_check_disk(), _check_java()],
            'Windows Services':           _check_services(),
            'BO Processes':               _check_processes(),
            f'Ports ({host})':            _check_ports(host),
        }
        self.after(0, lambda s=sections: self._render(s))

    def _render(self, sections):
        for w in self.scroll.winfo_children():
            w.destroy()
        for w in self._summary_frame.winfo_children():
            w.destroy()

        all_items = [item for sec in sections.values() for item in sec]
        counts = {'OK': 0, 'WARNING': 0, 'ERROR': 0, 'INFO': 0}
        for item in all_items:
            counts[item.get('status', 'INFO')] += 1

        for label, key, color in [('OK', 'OK', '#10B981'), ('Warning', 'WARNING', '#F59E0B'),
                                   ('Error', 'ERROR', '#EF4444'), ('Info', 'INFO', '#3B82F6')]:
            if counts[key]:
                chip = ctk.CTkFrame(self._summary_frame, fg_color=color, corner_radius=6)
                chip.pack(side='left', padx=4)
                ctk.CTkLabel(chip, text=f'  {label}: {counts[key]}  ',
                             font=('Segoe UI', 10, 'bold'),
                             text_color='white').pack(pady=4)

        self._status.configure(
            text=f'Last scan: {datetime.now().strftime("%H:%M:%S")} — '
                 f'{counts["ERROR"]} errors, {counts["WARNING"]} warnings'
        )

        for section_title, items in sections.items():
            sec_f = ctk.CTkFrame(self.scroll, fg_color=C['bg_tertiary'], corner_radius=8)
            sec_f.pack(fill='x', padx=6, pady=5)

            ctk.CTkLabel(sec_f, text=section_title,
                         font=('Segoe UI', 11, 'bold'),
                         text_color=C['text_primary']).pack(anchor='w', padx=12, pady=(8, 4))

            for item in items:
                status = item.get('status', 'INFO')
                color  = STATUS_COLORS.get(status, '#64748B')
                row = ctk.CTkFrame(sec_f, fg_color=C['bg_secondary'], corner_radius=5)
                row.pack(fill='x', padx=8, pady=2)

                dot_f = ctk.CTkFrame(row, fg_color='transparent', width=82)
                dot_f.pack(side='left', padx=6)
                dot_f.pack_propagate(False)
                ctk.CTkLabel(dot_f, text=f'● {status}',
                             font=('Segoe UI', 9, 'bold'),
                             text_color=color).pack(anchor='w', pady=8)

                ctk.CTkLabel(row, text=item.get('name', ''),
                             width=240, anchor='w',
                             font=('Segoe UI', 10, 'bold'),
                             text_color=C['text_primary']).pack(side='left', padx=4, pady=6)

                ctk.CTkLabel(row, text=item.get('detail', ''),
                             anchor='w',
                             font=('Segoe UI', 10),
                             text_color=C['text_secondary'],
                             wraplength=550).pack(side='left', padx=4)

            ctk.CTkFrame(sec_f, fg_color='transparent', height=6).pack()
