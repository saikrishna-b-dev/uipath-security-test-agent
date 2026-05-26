"""
Monitor Agent — Agent 1 of 5
─────────────────────────────
Continuously polls UiPath Test Manager for new test run failures
AND triggers OWASP ZAP security scans on each cycle.

Responsibilities:
  • Watch the SSTO project for failing test runs
  • Run OWASP ZAP spider + active scan against the target application
  • Emit TestFailure and SecurityFinding events to the orchestrator queue
  • Track run history to avoid re-processing the same failures
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Callable, List, Optional, Set

from src.config.settings import config
from src.integrations.owasp_zap_client import OWASPZapClient
from src.integrations.test_manager_client import TestManagerClient
from src.utils.logger import get_logger
from src.utils.models import OrchestratorRun, SecurityFinding, SeverityLevel, TestFailure

logger = get_logger("agents.monitor")


# Callback types used by the orchestrator
OnFailureCallback = Callable[[TestFailure], None]
OnFindingCallback = Callable[[SecurityFinding], None]


class MonitorAgent:
    """
    Watches UiPath Test Manager and OWASP ZAP.

    Example usage (standalone):
        agent = MonitorAgent()
        agent.run_once()          # single scan cycle
        agent.run_loop()          # blocking poll loop
    """

    def __init__(
        self,
        tm_client: Optional[TestManagerClient] = None,
        zap_client: Optional[OWASPZapClient] = None,
        on_failure: Optional[OnFailureCallback] = None,
        on_security_finding: Optional[OnFindingCallback] = None,
    ) -> None:
        self.tm = tm_client or TestManagerClient()
        self.zap = zap_client or OWASPZapClient()
        self.on_failure = on_failure
        self.on_security_finding = on_security_finding
        self._seen_run_ids: Set[str] = set()
        self._seen_finding_keys: Set[tuple] = set()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run_once(self) -> OrchestratorRun:
        """
        Execute a single monitor cycle:
          1. Check Test Manager for failed runs
          2. Run ZAP scan and collect security findings
        Returns an OrchestratorRun with everything discovered this cycle.
        """
        run = OrchestratorRun(run_id=str(uuid.uuid4()), started_at=datetime.utcnow())
        logger.info("Monitor cycle started — run_id=%s", run.run_id)

        # --- Step 1: Test Manager failures ---
        run.failures_detected = self._poll_test_manager()
        for failure in run.failures_detected:
            if self.on_failure:
                self.on_failure(failure)

        # --- Step 2: OWASP ZAP security scan ---
        run.security_findings = self._run_security_scan()
        for finding in run.security_findings:
            if self.on_security_finding:
                self.on_security_finding(finding)

        run.completed_at = datetime.utcnow()
        elapsed = (run.completed_at - run.started_at).total_seconds()
        logger.info(
            "Monitor cycle complete in %.1fs — %d failures, %d security findings",
            elapsed, len(run.failures_detected), len(run.security_findings),
        )
        return run

    def run_loop(self, max_cycles: Optional[int] = None) -> None:
        """
        Blocking poll loop. Calls run_once() every `poll_interval_seconds`.
        Pass max_cycles for testing; omit for infinite production loop.
        """
        interval = config.agent.poll_interval_seconds
        cycle = 0
        logger.info("Monitor agent starting (interval=%ds) …", interval)
        while max_cycles is None or cycle < max_cycles:
            try:
                self.run_once()
            except Exception as exc:
                logger.error("Monitor cycle failed: %s", exc, exc_info=True)
            cycle += 1
            if max_cycles is None or cycle < max_cycles:
                logger.debug("Sleeping %ds before next cycle …", interval)
                time.sleep(interval)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _poll_test_manager(self) -> List[TestFailure]:
        """Check for new failed test runs and return unseen failures."""
        failures: List[TestFailure] = []
        try:
            project = self.tm.get_project()
            project_id = project.get("id", config.uipath.tm_project_id)
            logger.info("Scanning project '%s' (id=%s) …", project.get("name"), project_id)

            # Get the most recent failed runs
            failed_runs = self.tm.list_test_runs(project_id=project_id, status="Failed", limit=20)
            new_runs = [r for r in failed_runs if r.get("id") not in self._seen_run_ids]

            logger.info("Found %d new failed run(s) (total failed: %d)", len(new_runs), len(failed_runs))

            for run in new_runs:
                run_id = run["id"]
                self._seen_run_ids.add(run_id)
                results = self.tm.get_failed_test_results(run_id)
                for result in results:
                    failure = TestManagerClient.to_test_failure(result, run_id)
                    failures.append(failure)
                    logger.warning(
                        "FAILURE detected: [%s] %s — %s",
                        failure.test_run_id, failure.test_case_name, failure.error_message[:120],
                    )
        except Exception as exc:
            logger.error("Test Manager polling error: %s", exc, exc_info=True)

        return failures

    def _run_security_scan(self) -> List[SecurityFinding]:
        """Run a ZAP scan cycle and return new security findings."""
        findings: List[SecurityFinding] = []
        try:
            logger.info("Initiating OWASP ZAP scan on %s …", config.owasp.target_url)
            self.zap.new_session()
            all_findings = self.zap.run_full_scan(min_severity=SeverityLevel.MEDIUM)

            for f in all_findings:
                key = (f.name, f.url, f.evidence or "")
                if key not in self._seen_finding_keys:
                    self._seen_finding_keys.add(key)
                    findings.append(f)
                    logger.warning(
                        "SECURITY FINDING [%s]: %s @ %s",
                        f.severity.value.upper(), f.name, f.url,
                    )
        except Exception as exc:
            logger.error("OWASP ZAP scan error: %s", exc, exc_info=True)

        return findings
