"""
Validation Agent — Agent 4 of 5
─────────────────────────────────
Re-executes repaired tests to confirm the heal succeeded.
Closes the feedback loop back to the Monitor Agent.

Responsibilities:
  • Trigger a fresh test run for each repaired test case
  • Wait for execution to complete
  • Record pass/fail outcome as ValidationResult
  • Roll back failed repairs (restore original test case config)
"""
from __future__ import annotations

import json
from typing import List, Optional

from src.config.settings import config
from src.integrations.test_manager_client import TestManagerClient
from src.utils.logger import get_logger
from src.utils.models import (
    RepairResult,
    TestStatus,
    ValidationResult,
)

logger = get_logger("agents.validation")


class ValidationAgent:
    """
    Confirms whether a repair actually fixed the failing test.

    Example:
        agent = ValidationAgent()
        result = agent.validate(repair_result)
        print("Healed!" if result.re_run_passed else "Still failing")
    """

    def __init__(self, tm_client: Optional[TestManagerClient] = None) -> None:
        self.tm = tm_client or TestManagerClient()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def validate(self, repair: RepairResult) -> ValidationResult:
        """
        Trigger a re-run of the repaired test and return a ValidationResult.
        If the repair failed (success=False), skip re-run and mark as not validated.
        """
        failure = repair.diagnosis.test_failure
        logger.info("Validating repair for '%s' …", failure.test_case_name)

        if not repair.success:
            logger.info("Repair was not applied — skipping validation re-run")
            return ValidationResult(
                repair=repair,
                re_run_passed=False,
                re_run_status=TestStatus.NOT_RUN,
                validation_notes="Repair was not applied; no re-run performed.",
            )

        # Get the test set that owns this test case
        test_set_id = failure.metadata.get("testSetId")
        if not test_set_id:
            logger.warning("No testSetId in metadata for '%s'; cannot trigger re-run", failure.test_case_name)
            return ValidationResult(
                repair=repair,
                re_run_passed=False,
                re_run_status=TestStatus.NOT_RUN,
                validation_notes="Cannot validate: testSetId not available in failure metadata.",
            )

        try:
            # Trigger fresh run
            new_run = self.tm.trigger_test_run(test_set_id)
            run_id = new_run.get("id", "dry-run-id")
            logger.info("Re-run triggered, run_id=%s", run_id)

            # Wait for completion
            if config.agent.dry_run:
                completed_run = {"status": "Passed", "id": run_id}
            else:
                completed_run = self.tm.wait_for_run(run_id, timeout=300)

            final_status = completed_run.get("status", "").lower()
            passed = final_status == "passed"

            status_map = {
                "passed": TestStatus.PASSED,
                "failed": TestStatus.FAILED,
                "aborted": TestStatus.BLOCKED,
            }
            tm_status = status_map.get(final_status, TestStatus.NOT_RUN)

            notes = (
                f"Re-run {run_id} completed with status: {final_status.upper()}. "
                f"Repair action was: {repair.action_taken.value}. "
                f"Patch: {repair.patch_description}"
            )

            if not passed:
                logger.warning("Re-run FAILED for '%s' — rolling back repair", failure.test_case_name)
                self._rollback(repair)
                notes += " | Repair rolled back."

            return ValidationResult(
                repair=repair,
                re_run_passed=passed,
                re_run_status=tm_status,
                validation_notes=notes,
            )

        except TimeoutError:
            logger.error("Re-run timed out for '%s'", failure.test_case_name)
            return ValidationResult(
                repair=repair,
                re_run_passed=False,
                re_run_status=TestStatus.NOT_RUN,
                validation_notes="Validation timed out waiting for re-run to complete.",
            )
        except Exception as exc:
            logger.error("Validation error: %s", exc, exc_info=True)
            return ValidationResult(
                repair=repair,
                re_run_passed=False,
                re_run_status=TestStatus.NOT_RUN,
                validation_notes=f"Validation error: {exc}",
            )

    def validate_batch(self, repairs: List[RepairResult]) -> List[ValidationResult]:
        """Validate a list of repairs sequentially."""
        return [self.validate(r) for r in repairs]

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------

    def _rollback(self, repair: RepairResult) -> None:
        """Restore the original test case configuration if repair made things worse.

        original_code is stored as a JSON string keyed by the field that was changed,
        e.g. {"steps": [...]} — we restore exactly that field to its pre-repair value.
        """
        if not repair.original_code:
            logger.warning("No original snapshot stored for '%s' — cannot roll back",
                           repair.diagnosis.test_failure.test_case_name)
            return
        failure = repair.diagnosis.test_failure
        try:
            original_payload = json.loads(repair.original_code)
        except json.JSONDecodeError as exc:
            logger.error("Rollback aborted: original_code is not valid JSON: %s", exc)
            return
        try:
            logger.info("Rolling back test case '%s' (id=%s) …",
                        failure.test_case_name, failure.test_case_id)
            self.tm.update_test_case(failure.test_case_id, original_payload)
            logger.info("Rollback successful for '%s'", failure.test_case_name)
        except Exception as exc:
            logger.error("Rollback API call failed: %s", exc, exc_info=True)
