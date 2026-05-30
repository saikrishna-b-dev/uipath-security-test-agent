# 🎬 Demo — UiPath Security Test Orchestrator

> **UiPath AgentHack 2026 | Track 3: Test Cloud**  
> See the full autonomous healing cycle in action without running any code.

---

## What Happens in One Run

```
03:14:02  Monitor Agent    — polls Test Cloud, finds 8 failed security tests
03:14:19  Diagnosis Agent  — classifies root causes (endpoint changed, auth failure, locator drift)
03:14:38  Repair Agent     — Claude Code LLM rewrites broken test scripts
03:17:44  Validation Agent — re-runs all 8 tests in Test Cloud: 7 PASS, 1 ESCALATED
03:18:39  Report Agent     — HTML + JSON audit report written, TC-008 sent to Action Center
Total: 4 minutes 37 seconds  |  87% self-heal rate  |  0 human actions required
```

---

## Step 1 — Monitor Agent Detects Failures

The Monitor Agent polls UiPath Test Cloud every N minutes via the Test Manager API.
When it finds failed test executions in the **Security-Test-Orchestrator** project, it emits
a structured `TestFailure` event for each one:

```json
{
  "test_case_id": "TC-001",
  "test_case_name": "SQL Injection endpoint scan",
  "failure_reason": "Connection refused — endpoint /api/v1/users/search returned 404",
  "last_passed": "2026-05-26T22:00:00Z",
  "consecutive_failures": 3
}
```

---

## Step 2 — Diagnosis Agent Classifies Root Cause

The Diagnosis Agent analyses the failure log and HTTP response using a lightweight ML
classifier. It assigns one of five categories:

| Category | Meaning | Example |
|---|---|---|
| `endpoint_changed` | API path moved or renamed | `/api/users` → `/api/v1/users/search` |
| `auth_failure` | Token expired or auth flow changed | JWT expiry, new OAuth scopes |
| `locator_drift` | UI selector no longer matches DOM | CSSclass renamed after front-end deploy |
| `header_mismatch` | Expected header absent or changed value | CSP policy tightened |
| `timeout` | Response too slow for current threshold | Infra degradation |

---

## Step 3 — Repair Agent Heals the Script

The Repair Agent calls **Claude Code** with the broken test script + diagnosis + live
API response. Claude rewrites only the affected parts and returns a patched script.

**Before (broken):**
```python
response = requests.get(f"{BASE_URL}/api/users/search?q={payload}")
assert response.status_code == 200
```

**After (healed by Claude Code):**
```python
response = requests.get(
    f"{BASE_URL}/api/v1/users/search",
    params={"q": payload},
    headers={"Authorization": f"Bearer {self._get_token()}"}
)
assert response.status_code == 200
```

If the repair fails validation, the Repair Agent **auto-rolls back** to the last known-good
version and escalates to UiPath Action Center.

---

## Step 4 — Validation Agent Confirms

The Validation Agent re-executes each patched test in Test Cloud and checks the result:

- ✅ **HEALED** — test passes; healing logged in audit trail
- ❌ **ESCALATED** — test still fails; human reviewer assigned via Action Center

---

## Step 5 — Report Agent Output

After every cycle the Report Agent generates a full HTML report. Open the sample now:

👉 **[sample/run_a3f9b12c_report.html](sample/run_a3f9b12c_report.html)**

### Sample Run Metrics

| Metric | Value |
|---|---|
| Run ID | `a3f9b12c-7e41-4d28-9f03-c5d82a1b6e94` |
| Duration | 4 min 37 sec |
| Failures detected | 8 |
| Tests healed | **7 (87%)_** |
| Tests escalated | 1 |
| OWASP findings | 11 (1 Critical, 2 High, 5 Medium, 3 Low) |

### Security Findings Detected (OWASP ZAP)

| Finding | Severity | CWE |
|---|---|---|
| SQL Injection | 🔴 CRITICAL | CWE-89 |
| JWT None Algorithm | 🟠 HIGH | CWE-287 |
| Insecure Direct Object Reference | 🟠 HIGH | CWE-639 |
| Missing Security Headers (CSP) | 🟡 MEDIUM | CWE-693 |
| Cross-Site Request Forgery | 🟡 MEDIUM | CWE-352 |
| Sensitive Data in URL Parameters | 🟡 MEDIUM | CWE-598 |

### Self-Healing Log

| Test Case | Root Cause | Action | Result |
|---|---|---|---|
| TC-001 · SQL Injection scan | `endpoint_changed` | `update_endpoint` | ✅ HEALED |
| TC-002 · JWT auth token | `auth_failure` | `refresh_auth_token` | ✅ HEALED |
| TC-003 · IDOR order-access | `endpoint_changed` | `update_endpoint` | ✅ HEALED |
| TC-004 · CSP header assertion | `header_mismatch` | `update_assertion` | ✅ HEALED |
| TC-005 · CSRF token verification | `locator_drift` | `harden_locator` | ✅ HEALED |
| TC-006 · TLS version negotiation | `header_mismatch` | `update_assertion` | ✅ HEALED |
| TC-007 · Cookie security flags | `locator_drift` | `harden_locator` | ✅ HEALED |
| TC-008 · Verbose error message leak | `auth_failure` | `refresh_auth_token` | ❌ ESCALATED → Action Center |

---

## Run It Yourself (60 seconds)

```bash
git clone https://github.com/saikrishna-b-dev/uipath-security-test-agent.git
cd uipath-security-test-agent
cp config/config.example.json config/config.json
# Edit config/config.json — add your UiPath + ZAP credentials

docker compose up          # starts ZAP + orchestrator automatically
# OR: pytest tests/ -v     # run the 29-test suite offline (no credentials needed)
```

---

## Why This Wins

| Problem | This Project |
|---|---|
| 8–16 hrs/sprint fixing broken security tests | **< 5 minutes autonomous healing** |
| Manual OWASP test maintenance | **Continuous, self-maintaining coverage** |
| No audit trail for compliance | **Full HTML + JSON report every run** |
| Broken tests silently skip security gaps | **Action Center escalation — nothing slips** |

---

*Built for UiPath AgentHack 2026, Track 3: Test Cloud — Solo Submission by Sai Krishna B*
