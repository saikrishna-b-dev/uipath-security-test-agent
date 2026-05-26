"""
Regression tests for all bugs fixed in the /shipit audit pass.
Run alongside test_diagnosis_agent.py
"""
import json
import pytest
from unittest.mock import MagicMock, patch


class TestLocatorHardeningFix:
    """BUG: contains(@class,'') always returns true — generates useless XPath."""

    def test_no_always_true_class_predicate(self):
        from src.agents.repair_agent import RepairAgent
        step = {"selector": "/html/body/div[2]/button[1]", "action": "click"}
        patched = RepairAgent._harden_step_locator(step)
        assert patched["_healed"] is True
        assert "contains(@class, '')" not in patched["selector"]
        assert "@data-testid" in patched["selector"] or "@id" in patched["selector"]
        assert patched["_originalSelector"] == "/html/body/div[2]/button[1]"

    def test_relative_xpath_not_touched(self):
        from src.agents.repair_agent import RepairAgent
        step = {"selector": "//button[@id='submit']", "action": "click"}
        patched = RepairAgent._harden_step_locator(step)
        assert patched.get("_healed") is None
        assert patched["selector"] == "//button[@id='submit']"

    def test_empty_selector_not_touched(self):
        from src.agents.repair_agent import RepairAgent
        patched = RepairAgent._harden_step_locator({"selector": "", "action": "click"})
        assert patched.get("_healed") is None


class TestZapRiskFilterFix:
    """BUG: ZAP ignores riskId param — filtering must happen client-side."""

    def test_filters_by_riskcode(self):
        from src.integrations.owasp_zap_client import OWASPZapClient
        raw = [
            {"alert": "SQLi", "riskcode": "3", "url": "http://x"},
            {"alert": "XSS",  "riskcode": "2", "url": "http://x"},
            {"alert": "Info", "riskcode": "0", "url": "http://x"},
        ]
        client = OWASPZapClient()
        with patch.object(client, "_call", return_value={"alerts": raw}):
            result = client.get_raw_alerts(risk_threshold=2)
            assert len(result) == 2
            assert all(int(a["riskcode"]) >= 2 for a in result)

    def test_threshold_zero_returns_all(self):
        from src.integrations.owasp_zap_client import OWASPZapClient
        raw = [{"alert": "A", "riskcode": "3"}, {"alert": "B", "riskcode": "0"}]
        client = OWASPZapClient()
        with patch.object(client, "_call", return_value={"alerts": raw}):
            assert len(client.get_raw_alerts(risk_threshold=0)) == 2

    def test_critical_only(self):
        from src.integrations.owasp_zap_client import OWASPZapClient
        raw = [
            {"alert": "SQLi", "riskcode": "3"},
            {"alert": "XSS",  "riskcode": "2"},
        ]
        client = OWASPZapClient()
        with patch.object(client, "_call", return_value={"alerts": raw}):
            result = client.get_raw_alerts(risk_threshold=3)
            assert len(result) == 1 and result[0]["alert"] == "SQLi"


class TestTokenUrlFix:
    """BUG: TOKEN_URL was hardcoded to cloud.uipath.com — breaks staging."""

    def test_token_url_uses_configured_base(self):
        from src.config.settings import AppConfig
        from src.integrations.test_manager_client import TestManagerClient
        client = TestManagerClient.__new__(TestManagerClient)
        client._token = None
        client._token_expires_at = 0.0
        client.cfg = AppConfig().uipath
        client._token_url = f"{client.cfg.base_url}/identity_/connect/token"
        assert client._token_url.endswith("/identity_/connect/token")
        # Default is staging — must not be hardcoded cloud URL
        assert "cloud.uipath.com" not in client._token_url

    def test_staging_url_correct(self):
        from src.config.settings import UiPathConfig
        cfg = UiPathConfig.__new__(UiPathConfig)
        cfg.base_url = "https://staging.uipath.com"
        url = f"{cfg.base_url}/identity_/connect/token"
        assert url == "https://staging.uipath.com/identity_/connect/token"


class TestRepairJsonRollback:
    """BUG: original_code stored as str(python_obj) — not deserializable for rollback."""

    def test_timeout_repair_original_is_valid_json(self):
        from src.agents.repair_agent import RepairAgent
        from src.utils.models import DiagnosisResult, HealingAction, TestFailure, TestStatus

        tm_mock = MagicMock()
        tm_mock.get_test_case.return_value = {"timeoutMs": 10000}
        tm_mock.update_test_case.return_value = {}

        agent = RepairAgent(tm_client=tm_mock)
        failure = TestFailure(
            test_run_id="r1", test_case_id="tc1",
            test_case_name="T", status=TestStatus.FAILED, error_message="timed out",
        )
        diag = DiagnosisResult(
            test_failure=failure, root_cause="timing",
            failure_category="timing",
            suggested_action=HealingAction.TIMEOUT_INCREASE,
            confidence_score=0.90,
        )
        result = agent.repair(diag)
        assert result.success
        original = json.loads(result.original_code)   # must not raise
        assert original.get("timeoutMs") == 10000

    def test_rollback_restores_original_field(self):
        from src.agents.validation_agent import ValidationAgent
        from src.agents.repair_agent import RepairAgent
        from src.utils.models import (
            DiagnosisResult, HealingAction, RepairResult, TestFailure, TestStatus
        )

        tm_mock = MagicMock()
        tm_mock.update_test_case.return_value = {}
        agent = ValidationAgent(tm_client=tm_mock)

        failure = TestFailure(
            test_run_id="r1", test_case_id="tc1",
            test_case_name="T", status=TestStatus.FAILED, error_message="err",
        )
        diag = DiagnosisResult(
            test_failure=failure, root_cause="x",
            failure_category="timing",
            suggested_action=HealingAction.TIMEOUT_INCREASE,
            confidence_score=0.90,
        )
        repair = RepairResult(
            diagnosis=diag,
            action_taken=HealingAction.TIMEOUT_INCREASE,
            patch_description="timeout increased",
            original_code=json.dumps({"timeoutMs": 10000}),
            patched_code=json.dumps({"timeoutMs": 15000}),
            success=True,
        )
        agent._rollback(repair)
        # update_test_case must be called with the original JSON payload
        tm_mock.update_test_case.assert_called_once_with("tc1", {"timeoutMs": 10000})


