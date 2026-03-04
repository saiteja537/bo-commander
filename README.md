Your current README is **too weak**. It doesn’t explain the tool, show features, or help someone run it. If a recruiter or SAP admin opens the repo, they’ll leave in 5 seconds.

Use a **structured README** like this.

Paste this into `README.md`.

---

# BO Commander

**AI-powered SAP BusinessObjects admin control center**

A desktop application for **SAP BusinessObjects administrators** that provides monitoring, diagnostics, security validation, and housekeeping tools using **real CMS data**.

Built with Python and designed to give admins a faster alternative to the traditional CMC interface.

---

# Key Features

### AI Sentinel

Automated health scanning for SAP BO environments.
Detects security risks, performance issues, failed schedules, and anomalies.

### AI Assistant

SAP BO–focused chatbot that helps administrators troubleshoot:

* LDAP configuration
* JVM tuning
* Universe errors
* Scheduling failures
* Server configuration

### Self-Healing Suggestions

Detects common issues and recommends fixes for:

* stopped servers
* failed instances
* orphaned objects

### System Monitor

Real-time monitoring of:

* memory usage
* disk space
* open ports
* running processes

### SSO / Trusted Authentication Tester

Validates the full authentication pipeline:

```
DNS → TCP → Token → Logon → Session → Logoff
```

Supports:

* SAML
* Kerberos
* NTLM
* Trusted Authentication

### LDAP Sync Monitor

Detects mismatches between **Active Directory groups and SAP BO groups**.

### Repository Diagnostics

Parallel CMS health checks including:

* connectivity
* table integrity
* orphan detection
* query performance

### Housekeeping Tools

Bulk operations for administrators:

* delete old instances
* clean failed schedules
* detect broken reports
* repository cleanup

---

# Architecture

```
BO Commander (Python GUI)
        ↓
SAP BO REST API (/biprws)
        ↓
CMS Database
```

Additional integrations:

* Google Gemini AI
* Windows OS monitoring
* Local documentation server

---

# Installation

### Requirements

* Python 3.10+
* SAP BusinessObjects BI 4.x
* Network access to BO REST API

### Clone the repository

```
git clone https://github.com/saiteja537/bo-commander.git
cd bo-commander
```

### Install dependencies

```
pip install -r requirements.txt
```

### Run the application

```
python bo_commander.py
```

---

# Dependencies

* customtkinter
* requests
* google-generativeai
* python-dateutil
* pillow

---


# Disclaimer

This tool interacts with a live SAP BusinessObjects environment and can perform administrative actions.

Always test in a **non-production environment first**.

AI-generated suggestions should be reviewed before applying them in production systems.

---

# Author

**Sai Teja Guddanti**

SAP BusinessObjects Developer

---

# Support the Project

If this project helps you:

⭐ Star the repository

---
