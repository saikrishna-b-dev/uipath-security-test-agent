"""
Repair Agent — Agent 3 of 5
─────────────────────────────
Applies self-healing patches to failing tests based on DiagnosisResult recommendations.

Responsibilities:
  • Execute the recommended HealingAction for each diagnosis
  • Update test case selectors, timeouts, or assertions via Test Manager API
  • Record what was changed (original vs patched)
  • Respect the max_repair_attempts limit
  • Skip repairs below the confidence threshold
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Dict, List, Optional

from src.config.settings import config
from src.integrations.test_manager_client import TestManagerClient
from src.utils.logger import get_logger
from src.utils.models import DiagnosisResult, HealingAction, RepairResult

logger = get_logger("agents.repair")

# Timeout multiplier applied when healing timing issues
_TIMEOUT_MULTIPLIER = 1.5
_DEFAULT_TIMEOUT_MS = 30_000


class RepairAgent:
    """
    Applies self-healing patches based on DiagnosisAgent output.

    Example:
        agent = RepairAgent()
        result = agent.repair(diagnosis)
        if result.success:
            print("Patched:", result.patch_description)
    """

    def __init__(self, tm_client: Optional[TestManagerClient] = None) -> None:
        self.tm = tm_client or TestManagerClient()
        self._attempt_counts: Dict[str, int] = {}  # test_case_id → attempts

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def repair(self, diagnosis: DiagnosisResult) -> RepairResult:
        """Attempt to repair the test case identified by the diagnosis."""
        failure = diagnosis.test_failure
        case_id = failure.test_case_id

        # Guard: confidence threshold
        if diagnosis.confidence_score < config.agent.healing_confidence_threshold:
            logger.info(
                "Skipping repair for '%s' — confidence %.2f below threshold %.2f",
                failure.test_case_name,
                diagnosis.confidence_score,
                config.agent.healing_confidence_threshold,
            )
            return RepairResult(
                diagnosis=diagnosis,
                action_taken=HealingAction.UNKNOWN,
                patch_description="Skipped: confidence below threshold",
                success=False,
                error=f"Confidence {diagnosis.confidence_score:.2f} < threshold {config.agent.healing_confidence_threshold}",
            )

        # Guard: max attempts
        attempts = self._attempt_counts.get(case_id, 0)
        if attempts >= config.agent.max_repair_attempts:
            logger.warning(
                "Max repair attempts (%d) reached for '%s'",
                config.agent.max_repair_attempts, failure.test_case_name,
            )
            return RepairResult(
                diagnosis=diagnosis,
                action_taken=diagnosis.suggested_action,
                patch_description=f"Skipped: max attempts ({config.agent.max_repair_attempts}) reached",
                success=False,
                error="max_repair_attempts exceeded",
            )

        self._attempt_counts[case_id] = attempts + 1
        logger.info(
            "Repairing '%s' (attempt %d/%d) using action: %s",
            failure.test_case_name,
            attempts + 1,
            config.agent.max_repair_attempts,
            diagnosis.suggested_action.value,
        )

        action = diagnosis.suggested_action
        dispatch = {
            HealingAction.LOCATOR_UPDATE:      self._repair_locator,
            HealingAction.SELECTOR_REGENERATE: self._repair_selector_regenerate,
            HealingAction.TIMEOUT_INCREASE:    self._repair_timeout,
            HealingAction.ASSERTION_RELAX:     self._repair_assertion,
            HealingAction.DATA_REFRESH:        self._repair_data,
            HealingAction.SKIP_UNSTABLE:       self._repair_skip,
        }
        handler = dispatch.get(action, self._repair_unknown)
        return handler(diagnosis)

    def repair_batch(self, diagnoses: List[DiagnosisResult]) -> List[RepairResult]:
        """Repair multiple diagnoses and return results."""
        return [self.repair(d) for d in diagnoses]

    # ------------------------------------------------------------------
    # Healing action handlers
    # ------------------------------------------------------------------

    def _repair_locator(self, diagnosis: DiagnosisResult) -> RepairResult:
        failure = diagnosis.test_failure
        try:
            tc = self.tm.get_test_case(failure.test_case_id)
            original_steps = tc.get("steps", [])

            # Build patched steps: upgrade brittle xpath selectors to robust ones
            patched_steps = [self._harden_step_locator(step) for step in original_steps]
            changed = [i for i, (o, p) in enumerate(zip(original_steps, patched_steps)) if o != p]

            if not changed:
                return RepairResult(
                    diagnosis=diagnosis,
                    action_taken=HealingAction.LOCATOR_UPDATE,
                    patch_description="No brittle locators detected in test steps — no change made",
                    original_code=str(original_steps),
                    patched_code=str(patched_steps),
                    success=True,  # nothing to fix = pass-through
                )

            self.tm.update_test_case(failure.test_case_id, {"steps": patched_steps})
            return RepairResult(
                diagnosis=diagnosis,
                action_taken=HealingAction.LOCATOR_UPDATE,
                patch_description=f"Hardened locators in {len(changed)} step(s): steps {changed}",
                original_code=json.dumps({"steps": original_steps}),
                patched_code=json.dumps({"steps": patched_steps}),
                success=True,
            )
        except Exception as exc:
            logger.error("Locator repair failed: %s", exc, exc_info=True)
            return RepairResult(
                diagnosis=diagnosis, action_taken=HealingAction.LOCATOR_UPDATE,
                patch_description="Locator repair failed",
                success=False, error=str(exc),
            )

    def _repair_selector_regenerate(self, diagnosis: DiagnosisResult) -> RepairResult:
        failure = diagnosis.test_failure
        try:
            tc = self.tm.get_test_case(failure.test_case_id)
            original = tc.get("configuration", {})
            patched = dict(original)
            patched["selectorStrategy"] = "data-testid"  # prefer stable data-testid attrs
            patched["fallbackStrategies"] = ["aria-label", "role+text", "css-class"]
            self.tm.update_test_case(failure.test_case_id, {"configuration": patched})
            return RepairResult(
                diagnosis=diagnosis,
                action_taken=HealingAction.SELECTOR_REGENERATE,
                patch_description="Updated selector strategy to data-testid with fallbacks",
                original_code=json.dumps({"configuration": original}),
                patched_code=json.dumps({"configuration": patched}),
                success=True,
            )
        except Exception as exc:
            logger.error("Selector regenerate failed: %s", exc, exc_info=True)
            return RepairResult(
                diagnosis=diagnosis, action_taken=HealingAction.SELECTOR_REGENERATE,
                patch_description="Selector regeneration failed",
                success=False, error=str(exc),
            )

    def _repair_timeout(self, diagnosis: DiagnosisResult) -> RepairResult:
        failure = diagnosis.test_failure
        try:
            tc = self.tm.get_test_case(failure.test_case_id)
            original_timeout = tc.get("timeoutMs", _DEFAULT_TIMEOUT_MS)
            new_timeout = int(original_timeout * _TIMEOUT_MULTIPLIER)
            self.tm.update_test_case(failure.test_case_id, {"timeoutMs": new_timeout})
            return RepairResult(
                diagnosis=diagnosis,
                action_taken=HealingAction.TIMEOUT_INCREASE,
                patch_description=f"Timeout increased {original_timeout}ms → {new_timeout}ms (×{_TIMEOUT_MULTIPLIER})",
                original_code=json.dumps({"timeoutMs": original_timeout}),
                patched_code=json.dumps({"timeoutMs": new_timeout}),
                success=True,
            )
        except Exception as exc:
            logger.error("Timeout repair failed: %s", exc, exc_info=True)
            return RepairResult(
                diagnosis=diagnosis, action_taken=HealingAction.TIMEOUT_INCREASE,
                patch_description="Timeout repair failed",
                success=False, error=str(exc),
            )

    def _repair_assertion(self, diagnosis: DiagnosisResult) -> RepairResult:
        failure = diagnosis.test_failure
        try:
            tc = self.tm.get_test_case(failure.test_case_id)
            original_assertions = tc.get("assertions", [])
            patched_assertions = []
            for assertion in original_assertions:
                patched = dict(assertion)
                # Convert strict equality to contains-check
                if patched.get("type") == "equals":
                    patched["type"] = "contains"
                    patched["_healed"] = True
                patched_assertions.append(patched)
            self.tm.update_test_case(failure.test_case_id, {"assertions": patched_assertions})
            changed = sum(1 for a in patched_assertions if a.get("_healed"))
            return RepairResult(
                diagnosis=diagnosis,
                action_taken=HealingAction.ASSERTION_RELAX,
                patch_description=f"Relaxed {changed} strict assertion(s) from 'equals' to 'contains'",
                original_code=json.dumps({"assertions": original_assertions}),
                patched_code=json.dumps({"assertions": patched_assertions}),
                success=True,
            )
        except Exception as exc:
            logger.error("Assertion repair failed: %s", exc, exc_info=True)
            return RepairResult(
                diagnosis=diagnosis, action_taken=HealingAction.ASSERTION_RELAX,
                patch_description="Assertion repair failed",
                success=False, error=str(exc),
            )

    def _repair_data(self, diagnosis: DiagnosisResult) -> RepairResult:
        failure = diagnosis.test_failure
        try:
            tc = self.tm.get_test_case(failure.test_case_id)
            original_fixtures = tc.get("testData", {})
            patched_fixtures = dict(original_fixtures)
            patched_fixtures["_refreshedAt"] = datetime.utcnow().isoformat()
            patched_fixtures["_nullableFields"] = True
            self.tm.update_test_case(failure.test_case_id, {"testData": patched_fixtures})
            return RepairResult(
                diagnosis=diagnosis,
                action_taken=HealingAction.DATA_REFRESH,
                patch_description="Marked test data for refresh and enabled nullable field tolerance",
                original_code=json.dumps({"testData": original_fixtures}),
                patched_code=json.dumps({"testData": patched_fixtures}),
                success=True,
            )
        except Exception as exc:
            logger.error("Data refresh repair failed: %s", exc, exc_info=True)
            return RepairResult(
                diagnosis=diagnosis, action_taken=HealingAction.DATA_REFRESH,
                patch_description="Data refresh failed",
                success=False, error=str(exc),
            )

    def _repair_skip(self, diagnosis: DiagnosisResult) -> RepairResult:
        failure = diagnosis.test_failure
        try:
            self.tm.update_test_case(failure.test_case_id, {
                "status": "skipped",
                "skipReason": f"Auto-skipped by RepairAgent: environment instability detected. "
                              f"Root cause: {diagnosis.root_cause}",
            })
            return RepairResult(
                diagnosis=diagnosis,
                action_taken=HealingAction.SKIP_UNSTABLE,
                patch_description="Test marked as skipped due to environment instability",
                success=True,
            )
        except Exception as exc:
            return RepairResult(
                diagnosis=diagnosis, action_taken=HealingAction.SKIP_UNSTABLE,
                patch_description="Skip failed",
                success=False, error=str(exc),
            )

    def _repair_unknown(self, diagnosis: DiagnosisResult) -> RepairResult:
        logger.warning("No repair handler for action: %s", diagnosis.suggested_action.value)
        return RepairResult(
            diagnosis=diagnosis,
            action_taken=HealingAction.UNKNOWN,
            patch_description="No automated repair available for this failure category",
            success=False,
            error="No handler for HealingAction.UNKNOWN",
        )

    # ------------------------------------------------------------------
    # Locator hardening helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _harden_step_locator(step: Dict) -> Dict:
        """
        Replace brittle absolute XPath selectors with more robust alternatives.
        Example: /html/body/div[3]/button[1] → //button[@data-testid]
        """
        patched = dict(step)
        selector = patched.get("selector", "") or ""

        # Replace positional XPath like /html/body/div[N]/...
        # Bug fix: contains(@class, '') is always true — use attribute-based predicates instead
        if re.match(r"^/html/", selector):
            tag_match = re.search(r"/(\w+)(?:\[\d+\])?$", selector)
            tag = tag_match.group(1) if tag_match else "*"
            patched["selector"] = f"//{tag}[@data-testid or @id or @name or @aria-label]"
            patched["_originalSelector"] = selector
            patched["_healed"] = True

        return patched
