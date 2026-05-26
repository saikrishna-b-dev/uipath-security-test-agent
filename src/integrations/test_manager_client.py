"""
UiPath Test Manager API client.
Handles auth, test run polling, test case updates, and defect creation.

API reference: https://docs.uipath.com/test-manager/automation-cloud/latest/api-guide
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import requests

from src.config.settings import config
from src.utils.logger import get_logger
from src.utils.models import TestFailure, TestStatus

logger = get_logger("integrations.test_manager")


class TestManagerClient:
    """
    Authenticated client for UiPath Test Manager REST API.

    Authentication uses the UiPath OAuth2 client-credentials flow.
    Token is cached and refreshed automatically on expiry.
    """

    TOKEN_URL = "https://cloud.uipath.com/identity_/connect/token"

    def __init__(self) -> None:
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self.cfg = config.uipath

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _get_token(self) -> str:
        """Fetch or return a cached OAuth2 access token."""
        if self._token and time.time() < self._token_expires_at - 30:
            return self._token

        logger.debug("Refreshing UiPath OAuth2 token …")
        resp = requests.post(
            self.TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.cfg.client_id,
                "client_secret": self.cfg.client_secret,
                "scope": "TM.TestRuns TM.TestCases TM.Projects",
            },
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expires_at = time.time() + payload.get("expires_in", 3600)
        logger.debug("Token refreshed, expires in %ss", payload.get("expires_in"))
        return self._token

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: Optional[Dict] = None) -> Any:
        url = f"{self.cfg.tm_base}/api/v2{path}"
        resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: Dict) -> Any:
        url = f"{self.cfg.tm_base}/api/v2{path}"
        resp = requests.post(url, headers=self._headers(), json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path: str, body: Dict) -> Any:
        url = f"{self.cfg.tm_base}/api/v2{path}"
        resp = requests.patch(url, headers=self._headers(), json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def get_project(self, project_key: Optional[str] = None) -> Dict:
        """Return project details for the configured project key."""
        key = project_key or self.cfg.tm_project_key
        data = self._get("/projects", params={"projectKey": key})
        projects = data.get("projects", [])
        if not projects:
            raise ValueError(f"Project with key '{key}' not found")
        return projects[0]

    # ------------------------------------------------------------------
    # Test Runs
    # ------------------------------------------------------------------

    def list_test_runs(
        self,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Return recent test runs for a project, optionally filtered by status."""
        pid = project_id or self.cfg.tm_project_id
        params: Dict[str, Any] = {"projectId": pid, "$top": limit}
        if status:
            params["status"] = status
        data = self._get("/testruns", params=params)
        return data.get("testRuns", [])

    def get_test_run(self, run_id: str) -> Dict:
        return self._get(f"/testruns/{run_id}")

    def get_failed_test_results(self, run_id: str) -> List[Dict]:
        """Return only the failed test results within a test run."""
        data = self._get(f"/testruns/{run_id}/testresults", params={"status": "Failed"})
        return data.get("testResults", [])

    def trigger_test_run(self, test_set_id: str) -> Dict:
        """Trigger a new execution of a test set (for re-validation after repair)."""
        if config.agent.dry_run:
            logger.warning("[DRY RUN] Would trigger test set %s", test_set_id)
            return {"id": "dry-run-id", "status": "queued"}
        return self._post("/testruns", {"testSetId": test_set_id})

    # ------------------------------------------------------------------
    # Test Cases
    # ------------------------------------------------------------------

    def get_test_case(self, case_id: str) -> Dict:
        return self._get(f"/testcases/{case_id}")

    def update_test_case(self, case_id: str, updates: Dict) -> Dict:
        """Apply a patch to a test case (e.g. updated selector or description)."""
        if config.agent.dry_run:
            logger.warning("[DRY RUN] Would update test case %s: %s", case_id, updates)
            return {}
        return self._patch(f"/testcases/{case_id}", updates)

    def add_defect(self, case_id: str, title: str, description: str, severity: str = "High") -> Dict:
        """Attach a defect/issue to a test case."""
        if config.agent.dry_run:
            logger.warning("[DRY RUN] Would create defect on %s: %s", case_id, title)
            return {}
        return self._post(f"/testcases/{case_id}/defects", {
            "title": title,
            "description": description,
            "severity": severity,
        })

    # ------------------------------------------------------------------
    # Helper: poll until run completes
    # ------------------------------------------------------------------

    def wait_for_run(self, run_id: str, timeout: int = 300, poll_every: int = 10) -> Dict:
        """Block until a test run reaches a terminal status or times out."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            run = self.get_test_run(run_id)
            status = run.get("status", "").lower()
            logger.debug("Test run %s status: %s", run_id, status)
            if status in ("passed", "failed", "aborted", "error"):
                return run
            time.sleep(poll_every)
        raise TimeoutError(f"Test run {run_id} did not complete within {timeout}s")

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def to_test_failure(raw_result: Dict, run_id: str) -> TestFailure:
        """Convert a raw Test Manager API result dict into a TestFailure model."""
        status_map = {
            "passed": TestStatus.PASSED,
            "failed": TestStatus.FAILED,
            "blocked": TestStatus.BLOCKED,
            "notrun": TestStatus.NOT_RUN,
            "inprogress": TestStatus.IN_PROGRESS,
        }
        raw_status = raw_result.get("status", "").lower().replace(" ", "")
        return TestFailure(
            test_run_id=run_id,
            test_case_id=raw_result.get("testCaseId", ""),
            test_case_name=raw_result.get("testCaseName", "Unknown"),
            status=status_map.get(raw_status, TestStatus.FAILED),
            error_message=raw_result.get("errorMessage", "No error message"),
            stack_trace=raw_result.get("stackTrace"),
            screenshot_url=raw_result.get("screenshotUrl"),
            metadata=raw_result,
        )
