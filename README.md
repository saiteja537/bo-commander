# BO Commander

**AI-powered SAP BusinessObjects administration control center**

BO Commander is a modern desktop application built for **SAP BusinessObjects administrators**.
It provides monitoring, diagnostics, security validation, and housekeeping tools using **live CMS data** — designed to be a faster and more intelligent alternative to the traditional **CMC interface**.

Built with **Python + CustomTkinter** and enhanced with **AI-powered diagnostics**.

---

# Quick Start

```bash
git clone https://github.com/saiteja537/bo-commander.git
cd bo-commander
pip install -r requirements.txt
python bo_commander.py
```

Enter your **SAP BusinessObjects server details** and begin monitoring your environment.

---

# Why BO Commander?

SAP BusinessObjects administrators often rely on the **Central Management Console (CMC)** for monitoring and troubleshooting.

However, CMC has limitations:

* Limited system health visibility
* Slow troubleshooting workflows
* Manual diagnostics
* No intelligent analysis

BO Commander solves this by providing:

• AI-assisted troubleshooting
• automated health diagnostics
• real-time monitoring tools
• faster administration workflows
• bulk housekeeping operations

---

# Key Features

## AI Sentinel

Automated health scanning for SAP BO environments.

Detects:

* security risks
* performance issues
* failed schedules
* system anomalies

---

## AI Assistant

An **SAP BO–focused AI assistant** designed for administrators.

It helps troubleshoot:

* LDAP configuration issues
* JVM memory problems
* Universe errors
* slow reports
* scheduling failures
* server configuration

Powered by **Google Gemini AI** with optional **live BO system context**.

---

## Self-Healing Suggestions

Detects common system issues and recommends fixes for:

* stopped servers
* failed instances
* orphaned objects
* server configuration problems

---

## System Monitor

Real-time monitoring of system resources:

* memory usage
* disk space
* open ports
* running processes

---

## SSO / Trusted Authentication Tester

Validates the full authentication pipeline:

```
DNS → TCP → Token → Logon → Session → Logoff
```

Supports:

* SAML
* Kerberos
* NTLM
* Trusted Authentication

---

## LDAP Sync Monitor

Detects mismatches between:

* **Active Directory groups**
* **SAP BO user groups**

Helps prevent authorization problems.

---

## Repository Diagnostics

Parallel CMS repository checks including:

* CMS connectivity
* table integrity
* orphan object detection
* query performance diagnostics

---

## Housekeeping Tools

Bulk administrative operations:

* delete old instances
* clean failed schedules
* detect broken reports
* repository cleanup

---

# Screenshot

### AI Assistant

<img width="956" height="500" alt="ai_assistant" src="https://github.com/user-attachments/assets/1da67add-b460-415f-8871-13388f340da1" />


The AI Assistant analyzes your **live BO system context** and provides targeted troubleshooting guidance.

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

## Requirements

* Python **3.10+**
* SAP BusinessObjects **BI 4.x**
* Network access to **BO REST API**
* CMS credentials

---

## Clone the repository

```bash
git clone https://github.com/saiteja537/bo-commander.git
cd bo-commander
```

---

## Install dependencies

```bash
pip install -r requirements.txt
```

---

## Run the application

```bash
python bo_commander.py
```

---

# Project Structure

```
bo-commander
│
├── bo_commander.py       # Application entry point
├── config.py             # Configuration settings
├── requirements.txt
│
├── core/                 # SAP BO REST API integration
├── gui/                  # CustomTkinter UI components
├── ai/                   # AI assistant and sentinel modules
├── assets/               # Icons and UI assets
└── docs/                 # Documentation and screenshots
```

---

# Dependencies

Main Python libraries used:

* customtkinter
* requests
* google-generativeai
* python-dateutil
* pillow

---

# Disclaimer

This tool interacts with a **live SAP BusinessObjects environment** and can perform administrative operations.

Always test in a **non-production environment first**.

AI-generated suggestions should always be **reviewed before applying in production systems**.

---

# Author

**Sai Teja Guddanti**

SAP BusinessObjects Developer

---

# Support the Project

If this project helps you:

⭐ **Star the repository**

---

# Future Improvements

Planned enhancements:

* BO server auto-healing automation
* advanced performance analytics
* AI-driven root cause detection
* interactive system health dashboards

---
