"""
Unit tests for DiagnosisAgent — runnable without any UiPath or ZAP connection.
"""
import pytest
from unittest.mock import MagicMock

from src.agents.diagnosis_agent import DiagnosisAgent
from src.utils.models import (
    HealingAction,
    SecurityFinding,
    SeverityLevel,
    TestFailure,
    TestStatus,
)


def _make_failure(error_message: str, case_id: str = "tc-001") -> TestFailure:
    return TestFailure(
        test_run_id="run-001",
        test_case_id=case_id,
        test_case_name="Login Flow Test",
        status=TestStatus.FAILED,
        error_message=error_message,
    )


@pytest.fixture
def agent():
    tm_mock = MagicMock()
    tm_mock.get_test_case.return_value = {"steps": [], "tags": ["smoke"]}
    return DiagnosisAgent(tm_client=tm_mock)


class TestDiagnosisClassification:
    def test_locator_stale(self, agent):
        f = _make_failure("Element not found: //div[@id='submit-btn']")
        result = agent.diagnose(f)
        assert result.failure_category == "locator_stale"
        assert result.suggested_action == HealingAction.LOCATOR_UPDATE
        assert result.confidence_score >= 0.80

    def test_timeout(self, agent):
        f = _make_failure("Timeout: element not clickable after 10000ms")
        result = agent.diagnose(f)
        assert result.failure_category == "timing"
        assert result.suggested_action == HealingAction.TIMEOUT_INCREASE

    def test_assertion_mismatch(self, agent):
        f = _make_failure("AssertionError: expected 'Welcome' but got 'Hello'")
        result = agent.diagnose(f)
        assert result.failure_category == "assertion_mismatch"
        assert result.suggested_action == HealingAction.ASSERTION_RELAX

    def test_data_dependency(self, agent):
        f = _make_failure("NullPointerException: key 'user_id' not found in fixture data")
        result = agent.diagnose(f)
        assert result.failure_category == "data_dependency"
        assert result.suggested_action == HealingAction.DATA_REFRESH

    def test_unknown_failure(self, agent):
        f = _make_failure("Something totally unexpected happened XYZ_123")
        result = agent.diagnose(f)
        assert result.failure_category == "unknown"
        assert result.confidence_score < 0.6

    def test_confidence_boosted_by_retry(self, agent):
        f = _make_failure("Element not found: //button")
        f.retry_count = 2
        result = agent.diagnose(f)
        # Retry count should push confidence higher
        assert result.confidence_score >= 0.88

    def test_security_correlation_boosts_confidence(self, agent):
        f = _make_failure("Element not found: login form")
        diagnoses = agent.diagnose_batch([f])
        findings = [
            SecurityFinding(
                finding_id="f1",
                name="Authentication Bypass",
                severity=SeverityLevel.HIGH,
                url="http://app/login",
                description="Auth issue",
                solution="Fix auth",
                cwe_id="287",
            )
        ]
        original_confidence = diagnoses[0].confidence_score
        correlated = agent.correlate_with_security(diagnoses, findings)
        assert correlated[0].confidence_score >= original_confidence
        assert any("Correlated OWASP" in e for e in correlated[0].evidence)

    def test_batch_returns_same_length(self, agent):
        failures = [
            _make_failure("Element not found", "tc-1"),
            _make_failure("Timeout exceeded", "tc-2"),
            _make_failure("NullPointer", "tc-3"),
        ]
        results = agent.diagnose_batch(failures)
        assert len(results) == 3


class TestRootCauseDescriptions:
    def test_root_cause_not_empty(self, agent):
        for error in [
            "element not found",
            "timed out",
            "assertion failed expected but got",
            "null key not found",
            "connection refused",
        ]:
            f = _make_failure(error)
            result = agent.diagnose(f)
            assert result.root_cause
            assert len(result.root_cause) > 10
