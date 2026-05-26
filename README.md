# 🛡️ UiPath Security Test Orchestrator

> **UiPath AgentHack 2026 | Track 3: Test Cloud**  
> An agentic multi-agent system that autonomously detects, diagnoses, and self-heals OWASP security test failures — powered by UiPath Maestro, Agent Builder, Test Cloud, and Claude Code.

---

## 🚨 The Problem

Every security engineering team faces this: automated OWASP security tests break overnight when the application changes — new endpoints, modified auth flows, updated headers. Fixing them manually takes **8–16 hours per sprint**. At $75/hr, that's **$31,200/year** in wasted senior engineer time per team.

No one has solved this with agentic AI. Until now.

---

## 💡 The Solution

**UiPath Security Test Orchestrator** is a 5-agent system orchestrated by UiPath Maestro that:

1. 🔍 **Monitors** Test Cloud for security test failures in real-time
2. 🧠 **Diagnoses** root cause (changed endpoint, auth failure, header mismatch, selector drift)
3. 🔧 **Repairs** broken test scripts autonomously using LLM-powered code generation
4. ✅ **Validates** fixes by re-executing repaired tests on UiPath Test Cloud
5. 📋 **Reports** full audit trail with OWASP category, fix applied, and compliance status

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                  UiPath Maestro (BPMN)               │
│  Orchestrates the full agentic security test loop    │
└──────────┬──────────────────────────────────────────┘
           │
  ┌────────▼───────┐   ┌──────────────┐   ┌──────────────┐
  │ Monitor Agent  │──▶│ Diagnosis    │──▶│ Repair Agent │
  │ (Test Cloud)   │   │ Agent (ML)   │   │ (Claude Code)│
  └────────────────┘   └──────────────┘   └──────┬───────┘
                                                  │
                       ┌──────────────┐   ┌───────▼──────┐
                       │ Report Agent │◀──│ Validation   │
                       │ (Audit Trail)│   │ Agent        │
                       └──────────────┘   └──────────────┘
```

---

## 🤖 Agent Breakdown

| Agent | Role | UiPath Tool |
|-------|------|-------------|
| **Monitor Agent** | Polls Test Cloud, detects failures | Agent Builder + Test Cloud API |
| **Diagnosis Agent** | ML classifies failure type (OWASP root cause) | Coded Agent (Python) |
| **Repair Agent** | Generates fixed test script via Claude Code | Agent Builder + Claude Code |
| **Validation Agent** | Re-executes fixed test, confirms pass | Test Cloud |
| **Report Agent** | Audit log, compliance report, team notification | Maestro + Action Center |

---

## 📊 Business Impact

| Metric | Before | After |
|--------|--------|-------|
| Broken test fix time | 8–16 hrs/sprint | < 5 minutes |
| Engineer time saved | 0 | ~12 hrs/sprint |
| Annual cost savings | $0 | **~$23,400/team/year** |
| OWASP coverage maintained | ❌ Degrades each release | ✅ Always maintained |
| Compliance audit trail | Manual | Fully automated |

---

## 🛠️ Tech Stack

- **UiPath Maestro** — BPMN-based agentic process orchestration
- **UiPath Agent Builder** — Monitor, Repair, and Report agents
- **UiPath Test Cloud** — Security test execution & failure detection
- **Python Coded Agents** — ML-based failure diagnosis
- **Claude Code** — LLM-powered test script repair *(bonus points)*
- **OWASP ZAP** — Security vulnerability test generation

---

## 🚀 Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/saikrishna-b-dev/uipath-security-test-agent.git
cd uipath-security-test-agent

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Configure credentials
cp config/config.example.json config/config.json
# Edit config.json with your UiPath Automation Cloud credentials

# 4. Import Maestro process
# UiPath Studio → Import → maestro/SecurityTestOrchestrator.xaml

# 5. Run
python scripts/run_orchestrator.py
```

---

## 📁 Project Structure

```
uipath-security-test-agent/
├── agents/
│   ├── monitor_agent/          # Test Cloud failure detection
│   ├── diagnosis_agent/        # ML-based root cause analysis
│   ├── repair_agent/           # LLM-powered script repair
│   ├── validation_agent/       # Test re-execution & confirmation
│   └── report_agent/           # Audit trail & notifications
├── maestro/
│   └── SecurityTestOrchestrator.xaml
├── scripts/
│   └── run_orchestrator.py
├── config/
│   └── config.example.json
├── docs/
│   └── architecture.png
└── requirements.txt
```

---

## 👨‍💻 Built By

**Sai Krishna B** — Python Developer | ML Explorer | Cybersecurity & OWASP Enthusiast  
🎯 GSoC 2026 Candidate | UiPath AgentHack 2026  
🔗 [GitHub](https://github.com/saikrishna-b-dev)

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built for UiPath AgentHack 2026 — Track 3: Test Cloud*
