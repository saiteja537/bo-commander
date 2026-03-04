import customtkinter as ctk
from tkinter import messagebox
import json, os, threading
from utils.encryption import encrypt_password, decrypt_password
from core.sapbo_connection import bo_session
from config import Config

class LoginPage(ctk.CTkFrame):
    def __init__(self, parent, on_success, sentinel_agent): 
        super().__init__(parent, fg_color=Config.COLORS['bg_primary'])
        self.on_success = on_success
        self.agent = sentinel_agent
        self.pack(fill="both", expand=True)
        
        self.card = ctk.CTkFrame(self, width=450, height=600, corner_radius=20,
                                  fg_color=Config.COLORS['bg_secondary'])
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        self.card.grid_propagate(False)
        self.setup_ui()
        self.load_profile()

    def setup_ui(self):
        ctk.CTkLabel(self.card, text="🎯", font=("Segoe UI", 50)).pack(pady=(40, 10))
        ctk.CTkLabel(self.card, text="BO Commander", font=("Segoe UI", 28, "bold")).pack()

        self.form = ctk.CTkFrame(self.card, fg_color="transparent")
        self.form.pack(fill="x", padx=50, pady=20)
        self.host = ctk.CTkEntry(self.form, placeholder_text="CMS Host", height=40)
        self.host.pack(fill="x", pady=5)
        self.user = ctk.CTkEntry(self.form, placeholder_text="Username", height=40)
        self.user.pack(fill="x", pady=5)
        self.pwd = ctk.CTkEntry(self.form, placeholder_text="Password", show="*", height=40)
        self.pwd.pack(fill="x", pady=5)

        self.status_lbl = ctk.CTkLabel(self.card, text="", text_color=Config.COLORS['danger'])
        self.status_lbl.pack()

        self.btn_connect = ctk.CTkButton(self.card, text="CONNECT", height=45,
                                          command=self.handle_login)
        self.btn_connect.pack(pady=10, padx=50, fill="x")

        self.emergency_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        self.btn_emergency = ctk.CTkButton(
            self.emergency_frame,
            text="🚨 Emergency AI Diagnosis",
            fg_color="#DC2626",
            command=self.run_emergency
        )
        self.btn_emergency.pack(fill="x", expand=True)

    def handle_login(self):
        h, u, p = self.host.get().strip(), self.user.get().strip(), self.pwd.get().strip()
        self.btn_connect.configure(state="disabled", text="CONNECTING...")
        threading.Thread(target=self.perform_login, args=(h, u, p)).start()

    def perform_login(self, h, u, p):
        success, msg = bo_session.login(h, "6405", u, p)
        self.after(0, lambda: self.finish_login(success, msg, h, u, p))

    def finish_login(self, success, msg, h, u, p):
        if success:
            self.save_profile(h, u, p)
            self.on_success()
        else:
            self.btn_connect.configure(state="normal", text="CONNECT")
            self.status_lbl.configure(text=f"Failed: {msg}")
            self.emergency_frame.pack(pady=10, padx=50, fill="x")

    def run_emergency(self):
        """
        ✅ THE ROOT FIX — Original code was a dead stub:
            messagebox.showinfo("AI Sentinel", "Starting Autonomous Diagnostic Scan...")
            # nothing else — agent was NEVER called

        Now actually:
          1. Opens a live results dialog
          2. Wires the agent callback to update the dialog when done
          3. Calls agent.investigate() with full connection context
        """
        if not self.agent:
            messagebox.showerror("Error", "Sentinel Agent not initialized.")
            return

        # Build live dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("🛡️ AI Sentinel — Emergency Diagnosis")
        dialog.geometry("680x520")
        dialog.attributes("-topmost", True)
        dialog.resizable(True, True)

        ctk.CTkLabel(dialog, text="🛡️ AI Sentinel — Emergency Diagnosis",
                     font=("Segoe UI", 18, "bold")).pack(pady=(20, 5))

        self._diag_status = ctk.CTkLabel(
            dialog,
            text="⏳ Running 8-layer cross-layer diagnostic scan...",
            font=("Segoe UI", 12), text_color="#60A5FA"
        )
        self._diag_status.pack(pady=5)

        # Show user what layers are being checked
        steps_box = ctk.CTkTextbox(dialog, font=("Consolas", 10), height=90)
        steps_box.pack(fill="x", padx=20)
        steps_box.insert("1.0",
            "Layer 1: BO context + log file collection\n"
            "Layer 2: BO logs — CMS, Tomcat, APS, WebI, FRS, Crystal, Audit\n"
            "Layer 3: OS — Windows services, memory, disk, Java processes\n"
            "Layer 4: Windows Event Viewer — System + Application errors\n"
            "Layer 5: Network — ports 6405/8080, DNS, ping, traceroute\n"
            "Layer 6: BO server status (if connected)\n"
            "Layer 7: Cross-layer correlation (failure chain analysis)\n"
            "Layer 8: AI analysis — root cause + solution generation\n"
        )
        steps_box.configure(state="disabled")

        ctk.CTkLabel(dialog, text="Diagnosis Result:", font=("Segoe UI", 12, "bold"),
                     anchor="w").pack(padx=20, anchor="w", pady=(8, 0))

        self._diag_result = ctk.CTkTextbox(dialog, font=("Consolas", 11))
        self._diag_result.pack(fill="both", expand=True, padx=20, pady=5)
        self._diag_result.insert("1.0",
            "⏳ Scanning in progress — please wait 15-30 seconds...\n\n"
            "The AI Sentinel is now:\n"
            "  • Reading SAP BO log files\n"
            "  • Checking Windows services\n"
            "  • Scanning Windows Event Viewer\n"
            "  • Testing network ports and connectivity\n"
            "  • Correlating findings across all layers\n"
            "  • Generating AI-powered root cause analysis\n"
        )
        self._diag_result.configure(state="disabled")

        self._btn_close = ctk.CTkButton(dialog, text="Close", fg_color="gray",
                                         command=dialog.destroy)
        self._btn_close.pack(pady=8)

        # Disable button while running
        self.btn_emergency.configure(state="disabled", text="🔍 Scanning all layers...")

        # Wire callback to update THIS dialog when scan completes
        original_callback = self.agent.ui_callback

        def on_rca_complete():
            try:
                incidents = self.agent.incidents
                if not incidents:
                    self._refresh_diag_dialog(dialog,
                        "⚠️ Scan complete — no incident recorded.",
                        "No incident was created. Possible causes:\n"
                        "  - Gemini API key not working (check ai/gemini_client.py)\n"
                        "  - No BO log files found (BOE_INSTALL_DIR may be wrong)\n"
                        "  - Check console/log output for error details\n"
                    )
                    return

                inc = incidents[0]
                sev = inc.get('severity', '?')
                pri = inc.get('priority', '?')

                report = (
                    f"{'='*58}\n"
                    f"  {inc.get('title', 'Unknown')}\n"
                    f"  Severity: {sev}  |  Priority: {pri}  |  Owner: {inc.get('owner','?')}\n"
                    f"  Est. Resolution: {inc.get('estimated_resolution_time','?')}\n"
                    f"{'='*58}\n\n"
                    f"ROOT CAUSE:\n{inc.get('root_cause','N/A')}\n\n"
                    f"FAILURE CHAIN:\n{inc.get('failure_chain', 'N/A')}\n\n"
                    f"EVIDENCE:\n{inc.get('evidence','N/A')}\n\n"
                    f"IMPACT:\n{inc.get('impact','N/A')}\n\n"
                    f"PREDICTION:\n{inc.get('prediction','N/A')}\n\n"
                    f"RECOMMENDED FIX STEPS:\n"
                )
                for i, step in enumerate(inc.get('solution_steps', []), 1):
                    report += f"  {i}. {step}\n"

                cmds = inc.get('os_commands', [])
                if cmds:
                    report += "\nOS COMMANDS TO RUN:\n"
                    for cmd in cmds:
                        report += f"  > {cmd}\n"

                self._refresh_diag_dialog(dialog,
                    f"✅ Diagnosis complete — {sev} severity | {pri}", report)

            except Exception as e:
                self._refresh_diag_dialog(dialog, f"❌ Error: {e}", str(e))
            finally:
                self.agent.ui_callback = original_callback

        self.agent.ui_callback = on_rca_complete

        # ─────────────────────────────────────────────────────────────────────
        # THIS IS THE LINE THAT WAS MISSING IN THE ORIGINAL CODE.
        # Without this call, the agent just sat idle forever.
        # ─────────────────────────────────────────────────────────────────────
        host = self.host.get().strip()
        self.agent.investigate(
            trigger="EMERGENCY_CONNECTION_REFUSED",
            details={
                "error": "Connection refused",
                "host": host or "unknown",
                "port": "6405",
                "user": self.user.get().strip(),
                "description": (
                    f"Login to {host}:6405 failed with 'Connection refused'. "
                    "Emergency diagnosis triggered from login screen."
                )
            }
        )

    def _refresh_diag_dialog(self, dialog, status_text, report_text):
        """Thread-safe UI update — uses after() to run on main thread."""
        def _do():
            try:
                self._diag_status.configure(text=status_text)
                self._diag_result.configure(state="normal")
                self._diag_result.delete("1.0", "end")
                self._diag_result.insert("1.0", report_text)
                self._diag_result.configure(state="disabled")
                self.btn_emergency.configure(state="normal", text="🚨 Emergency AI Diagnosis")
            except Exception:
                pass  # Widget destroyed — safe to ignore
        self.after(0, _do)

    def save_profile(self, h, u, p):
        if not os.path.exists("data"):
            os.makedirs("data")
        with open("data/connections.json", "w") as f:
            json.dump({"host": h, "user": u, "pwd": encrypt_password(p)}, f)

    def load_profile(self):
        if os.path.exists("data/connections.json"):
            try:
                with open("data/connections.json", "r") as f:
                    d = json.load(f)
                    self.host.insert(0, d.get('host', ""))
                    self.user.insert(0, d.get('user', ""))
                    if d.get('pwd'):
                        self.pwd.insert(0, decrypt_password(d['pwd']))
            except Exception:
                pass
