"""
Maestro Orchestrator — The brain that drives the 5-agent pipeline.
────────────────────────────────────────────────────────────────────
Pipeline:
  Monitor → Diagnosis → Repair → Validation → Report

This class mirrors the UiPath Maestro BPMN flow defined in
docs/maestro_flow.json, so the same logic runs locally (for testing)
and in the UiPath cloud (for production).

Each step emits events that the next step consumes — inspired by
the UiPath Maestro agent-handoff pattern.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from src.agents.diagnosis_agent import DiagnosisAgent
from src.agents.monitor_agent import MonitorAgent
from src.agents.repair_agent import RepairAgent
from src.agents.report_agent import ReportAgent
from src.agents.validation_agent import ValidationAgent
from src.config.settings import config
from src.integrations.owasp_zap_client import OWASPZapClient
from src.integrations.test_manager_client import TestManagerClient
from src.utils.logger import get_logger
from src.utils.models import (
    DiagnosisResult,
    OrchestratorRun,
    RepairResult,
    SecurityFinding,
    TestFailure,
    ValidationResult,
)

logger = get_logger("orchestrator.maestro")


class MaestroOrchestrator:
    """
    Coordinates the full Monitor → Diagnosis → Repair → Validation → Report cycle.

    Example (single run):
        orch = MaestroOrchestrator()
        report_paths = orch.run_cycle()

    Example (production loop):
        orch = MaestroOrchestrator()
        orch.run_loop()
    """

    def __init__(
        self,
        tm_client: Optional[TestManagerClient] = None,
        zap_client: Optional[OWASPZapClient] = None,
    ) -> None:
        tm = tm_client or TestManagerClient()
        zap = zap_client or OWASPZapClient()

        self.monitor    = MonitorAgent(tm_client=tm, zap_client=zap)
        self.diagnosis  = DiagnosisAgent(tm_client=tm)
        self.repair     = RepairAgent(tm_client=tm)
        self.validation = ValidationAgent(tm_client=tm)
        self.report     = ReportAgent()

        self._run_history: List[OrchestratorRun] = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run_cycle(self) -> dict:
        """
        Execute one full pipeline cycle.
        Returns the file paths of the generated reports.
        """
        run_id = str(uuid.uuid4())
        logger.info("=" * 60)
        logger.info("ORCHESTRATOR CYCLE START  run_id=%s", run_id)
        logger.info("=" * 60)

        run = OrchestratorRun(run_id=run_id, started_at=datetime.utcnow())

        # ── Step 1: Monitor ──────────────────────────────────────────
        logger.info("[1/5] MONITOR — polling Test Manager + OWASP ZAP")
        monitor_result = self.monitor.run_once()
        run.failures_detected = monitor_result.failures_detected
        run.security_findings = monitor_result.security_findings

        if not run.failures_detected and not run.security_findings:
            logger.info("No failures or findings — cycle complete (nothing to heal).")
            run.completed_at = datetime.utcnow()
            run.summary = "Clean cycle — no failures detected."
            return self._finish(run)

        # ── Step 2: Diagnosis ────────────────────────────────────────
        logger.info("[2/5] DIAGNOSIS — analysing %d failure(s)", len(run.failures_detected))
        diagnoses: List[DiagnosisResult] = self.diagnosis.diagnose_batch(run.failures_detected)

        # Cross-reference test failures with security findings
        if run.security_findings:
            diagnoses = self.diagnosis.correlate_with_security(diagnoses, run.security_findings)

        run.diagnoses = diagnoses
        logger.info("Diagnosis complete: %d results", len(diagnoses))

        # ── Step 3: Repair ───────────────────────────────────────────
        logger.info("[3/5] REPAIR — applying healing actions")
        repairs: List[RepairResult] = self.repair.repair_batch(diagnoses)
        run.repairs = repairs

        successful = sum(1 for r in repairs if r.success)
        logger.info("Repair complete: %d/%d repairs applied", successful, len(repairs))

        # ── Step 4: Validation ───────────────────────────────────────
        logger.info("[4/5] VALIDATION — re-running repaired tests")
        validations: List[ValidationResult] = self.validation.validate_batch(repairs)
        run.validations = validations

        healed = sum(1 for v in validations if v.re_run_passed)
        logger.info("Validation complete: %d/%d tests confirmed healed", healed, len(validations))

        # ── Step 5: Report ───────────────────────────────────────────
        logger.info("[5/5] REPORT — generating run report")
        run.completed_at = datetime.utcnow()
        run.summary = self._build_summary(run)

        self._run_history.append(run)
        return self._finish(run)

    def run_loop(self, max_cycles: Optional[int] = None) -> None:
        """
        Production loop — run_cycle() every poll_interval_seconds.
        Pass max_cycles=N for testing; omit for infinite loop.
        """
        import time
        interval = config.agent.poll_interval_seconds
        cycle = 0
        logger.info("Maestro Orchestrator starting (interval=%ds) …", interval)

        while max_cycles is None or cycle < max_cycles:
            try:
                paths = self.run_cycle()
                logger.info("Cycle %d complete. Reports: %s", cycle + 1, paths)
            except Exception as exc:
                logger.error("Cycle %d failed: %s", cycle + 1, exc, exc_info=True)
            cycle += 1
            if max_cycles is None or cycle < max_cycles:
                logger.info("Sleeping %ds before next cycle …", interval)
                time.sleep(interval)

    def get_run_history(self) -> List[OrchestratorRun]:
        return list(self._run_history)

    def latest_heal_rate(self) -> float:
        if not self._run_history:
            return 0.0
        return self._run_history[-1].heal_rate

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _finish(self, run: OrchestratorRun) -> dict:
        paths = self.report.generate(run)
        elapsed = ""
        if run.completed_at:
            secs = (run.completed_at - run.started_at).total_seconds()
            elapsed = f"{secs:.1f}s"
        logger.info(
            "ORCHESTRATOR CYCLE END  run_id=%s  elapsed=%s  heal_rate=%.0f%%  reports=%s",
            run.run_id, elapsed, run.heal_rate * 100, paths,
        )
        return paths

    @staticmethod
    def _build_summary(run: OrchestratorRun) -> str:
        healed = sum(1 for v in run.validations if v.re_run_passed)
        critical = sum(
            1 for f in run.security_findings
            if f.severity.value in ("critical", "high")
        )
        return (
            f"Run {run.run_id[:8]}: detected {len(run.failures_detected)} failure(s), "
            f"healed {healed}/{len(run.repairs)} ({int(run.heal_rate * 100)}%), "
            f"{len(run.security_findings)} security findings "
            f"({critical} critical/high)."
        )
