# 🛡️ UiPath Security Test Orchestrator

> **UiPath AgentHack 2026 | Track 3: Test Cloud**  
> A production-grade multi-agent system that autonomously detects, diagnoses, and self-heals OWASP security test failures — powered by UiPath Maestro, Agent Builder, Test Cloud, and Claude Code.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![Tests](https://img.shields.io/badge/Tests-29%2F29%20passing-brightgreen?logo=pytest)
![License](https://img.shields.io/badge/License-MIT-green)
![Track](https://img.shields.io/badge/AgentHack%202026-Track%203%3A%20Test%20Cloud-orange)

---

## 🚨 The Problem

Every security engineering team faces this: automated OWASP security tests break overnight when the application changes — new endpoints, modified auth flows, updated headers. Fixing them manually takes **8–16 hours per sprint**. At $75/hr, that's **$31,200/year** in wasted senior engineer time per team.

No one has solved this with agentic AI. Until now.

---

## 💡 The Solution

**UiPath Security Test Orchestrator** is a 5-agent pipeline orchestrated by UiPath Maestro that:

1. 🔍 **Monitors** UiPath Test Cloud for security test failures in real-time
2. 🧠 **Diagnoses** root cause — changed endpoint, auth failure, header mismatch, locator drift
3. 🔧 **Repairs** the broken test script automatically using Claude Code LLM
4. ✅ **Validates** the fix by re-running the test in Test Cloud
5. 📊 **Reports** findings with an OWASP risk heat-map and full audit trail

**Result: broken security tests go from 8–16 hours of manual work to < 5 minutes of autonomous healing.**

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│          UiPath Maestro Orchestrator                │
│   (BPMN process — drives the full agentic loop)     │
└──────────────────────┬──────────────────────────────┘
                       │
   ┌───────────────────▼──────────────────┐
   │         Monitor Agent                │
   │   Polls Test Cloud every N minutes   │
   │   Emits: TestFailure events          │
   └───────────────────┬──────────────────┘
                       │
   ┌───────────────────▼──────────────────┐
   │         Diagnosis Agent              │
   │   ML-based root cause analysis       │
   │   Categories: auth | locator |       │
   │   endpoint | header | timeout        │
   └───────────────────┬──────────────────┘
                       │
   ┌───────────────────▼──────────────────┐
   │         Repair Agent                 │
   │   LLM-powered (Claude Code) script   │
   │   healing + OWASP ZAP integration    │
   └───────────────────┬──────────────────┘
                       │
   ┌───────────────────▼──────────────────┐
   │        Validation Agent              │
   │   Re-executes fixed test in          │
   │   Test Cloud, confirms pass/fail     │
   └───────────────────┬──────────────────┘
                       │
   ┌───────────────────▼──────────────────┐
   │          Report Agent                │
   │   HTML + JSON audit report           │
   │   OWASP risk heat-map, heal rate     │
   └──────────────────────────────────────┘
```

---

## 📋 Agent Responsibilities

| Agent | What It Does | UiPath Component |
|---|---|---|
| **Monitor Agent** | Polls Test Cloud, detects failures, emits structured events | Agent Builder + Test Cloud API |
| **Diagnosis Agent** | Classifies failure root cause (auth, locator, endpoint, header) | Python Coded Agent + ML |
| **Repair Agent** | Rewrites broken test selectors/payloads, hardens locators, rolls back on failure | Agent Builder + Claude Code |
| **Validation Agent** | Re-runs fixed test, confirms healing, triggers rollback if needed | Test Cloud |
| **Report Agent** | Produces HTML report with OWASP heat-map, JSON audit trail | Maestro + Action Center |

---

## 📊 Business Impact

| Metric | Before | After |
|---|---|---|
| Broken test fix time | 8–16 hrs/sprint | **< 5 minutes** |
| Engineer time saved | 0 | ~12 hrs/sprint |
| Annual cost savings | $0 | **~$23,400/team/year** |
| OWASP coverage | ❌ Degrades each release | ✅ Always maintained |
| Compliance audit trail | Manual | Fully automated |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | UiPath Maestro (BPMN agentic process) |
| Agent Runtime | UiPath Agent Builder |
| Test Execution | UiPath Test Cloud |
| LLM Repair Engine | Claude Code (Anthropic) |
| Security Scanning | OWASP ZAP API |
| Coded Agents | Python 3.10+ |
| Testing | pytest — **29/29 tests passing** ✅ |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- UiPath Orchestrator + Test Cloud access
- OWASP ZAP running locally (default: `http://localhost:8080`)
- Claude API key (for Repair Agent)

### Install

```bash
git clone https://github.com/saikrishna-b-dev/uipath-security-test-agent.git
cd uipath-security-test-agent
pip install -r requirements.txt
cp config/config.example.json config/config.json
# Edit config/config.json with your credentials
```

### Run

```bash
python scripts/run_orchestrator.py
```

### Run Tests

```bash
pytest tests/ -v
# Expected: 29 passed
```

---

## 📁 Project Structure

```
uipath-security-test-agent/
├── src/
│   ├── agents/
│   │   ├── monitor_agent.py        # Test Cloud failure detection
│   │   ├── diagnosis_agent.py      # ML-based root cause analysis
│   │   ├── repair_agent.py         # LLM-powered script repair
│   │   ├── validation_agent.py     # Test re-execution & confirmation
│   │   └── report_agent.py         # Audit trail & HTML reports
│   ├── integrations/
│   │   └── owasp_zap_client.py     # OWASP ZAP REST API client
│   ├── config/
│   │   └── settings.py             # Centralised configuration
│   └── utils/
│       ├── models.py               # Pydantic data models
│       └── logger.py               # Structured logging
├── tests/
│   ├── test_bugfixes.py            # Regression tests (all bugs fixed)
│   └── ...                         # Additional test suites
├── scripts/
│   └── run_orchestrator.py         # Entry point
├── config/
│   └── config.example.json         # Config template
└── requirements.txt
```

---

## 🔐 Security Findings Report (Sample)

After each orchestration cycle, the Report Agent generates a visual HTML report:

- **Heal Rate** — % of broken tests autonomously fixed
- **OWASP Risk Heat-map** — Critical / High / Medium / Low / Informational counts
- **Per-test healing log** — what failed, what was diagnosed, what was repaired, and whether it passed
- **CWE mapping** — each finding linked to its CWE identifier

---

## 🧪 Test Coverage

All regression tests pass against the fixed codebase:

| Test Suite | Tests | Status |
|---|---|---|
| Locator hardening (XPath fix) | 4 | ✅ |
| ZAP risk-level client-side filtering | 6 | ✅ |
| Token/URL injection prevention | 5 | ✅ |
| Repair JSON rollback safety | 7 | ✅ |
| Integration smoke tests | 7 | ✅ |
| **Total** | **29** | **✅ All passing** |

---

## 👨‍💻 Built By

**Sai Krishna B** — Python Developer | ML Explorer | Cybersecurity & OWASP Enthusiast  
🎯 GSoC 2026 Candidate | UiPath AgentHack 2026 Solo Builder  
🔗 [GitHub](https://github.com/saikrishna-b-dev)

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built for UiPath AgentHack 2026, Track 3: Test Cloud*
