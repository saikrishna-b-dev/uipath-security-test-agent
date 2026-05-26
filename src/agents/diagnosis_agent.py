"""
Diagnosis Agent — Agent 2 of 5
────────────────────────────────
Analyses test failures and security findings to determine root cause
and recommend the best healing action.

Responsibilities:
  • Classify failure type (locator stale, timing, data dependency, etc.)
  • Map OWASP findings to relevant test cases
  • Score confidence in diagnosis
  • Output a DiagnosisResult per failure
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from src.config.settings import config
from src.integrations.test_manager_client import TestManagerClient
from src.utils.logger import get_logger
from src.utils.models import (
    DiagnosisResult,
    HealingAction,
    SecurityFinding,
    SeverityLevel,
    TestFailure,
)

logger = get_logger("agents.diagnosis")


# -----------------------------------------------------------------------
# Failure pattern catalogue
# Each entry: (regex_on_error_message, category_label, HealingAction, base_confidence)
# -----------------------------------------------------------------------
_FAILURE_PATTERNS: List[Tuple[str, str, HealingAction, float]] = [
    # Locator / selector issues
    (r"(element not found|no such element|unable to locate|stale element|xpath|css selector)",
     "locator_stale", HealingAction.LOCATOR_UPDATE, 0.88),
    (r"(invalid selector|malformed xpath|invalid css)",
     "locator_invalid", HealingAction.SELECTOR_REGENERATE, 0.85),

    # Timing issues
    (r"(timeout|timed out|wait.*exceeded|element not clickable|not interactable)",
     "timing", HealingAction.TIMEOUT_INCREASE, 0.82),

    # Assertion failures
    (r"(assert(ion)?.*fail|expected.*but (was|got)|value mismatch|comparison fail)",
     "assertion_mismatch", HealingAction.ASSERTION_RELAX, 0.75),

    # Data dependency
    (r"(null(pointer)?|undefined|key.*not found|missing.*field|data.*not available)",
     "data_dependency", HealingAction.DATA_REFRESH, 0.70),

    # Network / environment
    (r"(connection refused|502|503|network.*error|unreachable|dns)",
     "environment", HealingAction.SKIP_UNSTABLE, 0.60),
]

# OWASP finding → category mapping for cross-agent correlation
_OWASP_CATEGORY_MAP: Dict[str, str] = {
    "sql injection": "injection",
    "cross-site scripting": "xss",
    "path traversal": "path_traversal",
    "csrf": "csrf",
    "insecure headers": "misconfiguration",
    "sensitive information": "data_exposure",
    "authentication": "auth_bypass",
    "session": "session_management",
}


class DiagnosisAgent:
    """
    Analyses TestFailure objects and produces DiagnosisResult recommendations.

    Example:
        agent = DiagnosisAgent()
        result = agent.diagnose(failure)
        print(result.suggested_action, result.confidence_score)
    """

    def __init__(self, tm_client: Optional[TestManagerClient] = None) -> None:
        self.tm = tm_client or TestManagerClient()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def diagnose(self, failure: TestFailure) -> DiagnosisResult:
        """Produce a DiagnosisResult for a single TestFailure."""
        logger.info("Diagnosing failure: [%s] %s", failure.test_run_id, failure.test_case_name)

        category, action, confidence, evidence = self._classify_failure(failure)

        # Boost or reduce confidence based on retry count
        if failure.retry_count > 0:
            confidence = min(confidence + 0.05 * failure.retry_count, 0.99)

        # Try to enrich with Test Manager test case detail
        enriched_evidence = list(evidence)
        try:
            tc = self.tm.get_test_case(failure.test_case_id)
            steps = tc.get("steps", [])
            if steps:
                enriched_evidence.append(f"Test case has {len(steps)} steps")
            last_tag = tc.get("tags", [])
            if last_tag:
                enriched_evidence.append(f"Tags: {', '.join(last_tag)}")
        except Exception as exc:
            logger.debug("Could not enrich from Test Manager: %s", exc)

        result = DiagnosisResult(
            test_failure=failure,
            root_cause=self._describe_root_cause(category, failure),
            failure_category=category,
            suggested_action=action,
            confidence_score=round(confidence, 3),
            evidence=enriched_evidence,
        )
        logger.info(
            "Diagnosis complete: category=%s action=%s confidence=%.2f",
            result.failure_category, result.suggested_action.value, result.confidence_score,
        )
        return result

    def diagnose_batch(self, failures: List[TestFailure]) -> List[DiagnosisResult]:
        """Diagnose a list of failures and return results in the same order."""
        return [self.diagnose(f) for f in failures]

    def correlate_with_security(
        self,
        diagnoses: List[DiagnosisResult],
        findings: List[SecurityFinding],
    ) -> List[DiagnosisResult]:
        """
        Cross-reference test failures with OWASP findings.
        Adds security context to relevant diagnoses.
        """
        high_findings = [f for f in findings if f.severity in (SeverityLevel.CRITICAL, SeverityLevel.HIGH)]
        if not high_findings:
            return diagnoses

        for diag in diagnoses:
            for finding in high_findings:
                for keyword, category in _OWASP_CATEGORY_MAP.items():
                    if keyword in finding.name.lower():
                        diag.evidence.append(
                            f"Correlated OWASP {finding.severity.value} finding: '{finding.name}' "
                            f"[CWE-{finding.cwe_id}] at {finding.url}"
                        )
                        # Security-related failures get a confidence bump
                        diag.confidence_score = min(diag.confidence_score + 0.05, 0.99)
                        break
        return diagnoses

    # ------------------------------------------------------------------
    # Internal classification
    # ------------------------------------------------------------------

    def _classify_failure(
        self, failure: TestFailure
    ) -> Tuple[str, HealingAction, float, List[str]]:
        """
        Match the error message against known patterns.
        Returns (category, action, confidence, evidence_list).
        """
        combined_text = (
            (failure.error_message or "") + " " + (failure.stack_trace or "")
        ).lower()

        for pattern, category, action, confidence in _FAILURE_PATTERNS:
            match = re.search(pattern, combined_text, re.IGNORECASE)
            if match:
                evidence = [
                    f"Matched pattern '{pattern}' in error message",
                    f"Error excerpt: …{combined_text[max(0, match.start()-40):match.end()+40]}…",
                ]
                return category, action, confidence, evidence

        # Fallback: unknown failure
        return (
            "unknown",
            HealingAction.UNKNOWN,
            0.40,
            [f"No known pattern matched. Error: {failure.error_message[:200]}"],
        )

    @staticmethod
    def _describe_root_cause(category: str, failure: TestFailure) -> str:
        descriptions = {
            "locator_stale": (
                f"UI element locator in '{failure.test_case_name}' is stale or no longer valid. "
                "The application DOM may have changed since the test was last updated."
            ),
            "locator_invalid": (
                f"The selector expression in '{failure.test_case_name}' is syntactically invalid."
            ),
            "timing": (
                f"Test '{failure.test_case_name}' timed out waiting for an element or condition. "
                "Page load or response time may have increased."
            ),
            "assertion_mismatch": (
                f"An assertion in '{failure.test_case_name}' failed due to unexpected data. "
                "The expected value may need to be updated after an application change."
            ),
            "data_dependency": (
                f"Test '{failure.test_case_name}' depends on data that was null or unavailable. "
                "Test data or fixtures may need refreshing."
            ),
            "environment": (
                f"'{failure.test_case_name}' failed due to an environment or network issue. "
                "This may be a transient infrastructure problem."
            ),
        }
        return descriptions.get(
            category,
            f"Unknown root cause for '{failure.test_case_name}'. Manual investigation required."
        )
