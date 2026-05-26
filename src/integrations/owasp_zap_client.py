"""
OWASP ZAP API client for active/passive security scanning.

OWASP ZAP must be running in daemon mode:
    zap.sh -daemon -host 0.0.0.0 -port 8080 -config api.key=changeme
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import requests

from src.config.settings import config
from src.utils.logger import get_logger
from src.utils.models import SecurityFinding, SeverityLevel

logger = get_logger("integrations.owasp_zap")

# ZAP risk codes -> SeverityLevel
_RISK_MAP: Dict[str, SeverityLevel] = {
    "3": SeverityLevel.CRITICAL,
    "2": SeverityLevel.HIGH,
    "1": SeverityLevel.MEDIUM,
    "0": SeverityLevel.LOW,
    "-1": SeverityLevel.INFORMATIONAL,
}


class OWASPZapClient:
    """Thin wrapper around the ZAP REST API."""

    def __init__(self) -> None:
        self.cfg = config.owasp
        self._scan_id: Optional[str] = None
        self._spider_id: Optional[str] = None

    def _call(self, component: str, view_or_action: str, name: str,
              params: Optional[Dict] = None) -> Any:
        url = f"{self.cfg.zap_url}/JSON/{component}/{view_or_action}/{name}/"
        p = {"apikey": self.cfg.zap_api_key}
        if params:
            p.update(params)
        resp = requests.get(url, params=p, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Spider
    # ------------------------------------------------------------------

    def start_spider(self, target: Optional[str] = None,
                     context_name: Optional[str] = None) -> str:
        t = target or self.cfg.target_url
        logger.info("Starting ZAP spider on %s ...", t)
        params: Dict[str, Any] = {
            "url": t,
            "maxChildren": str(self.cfg.spider_max_depth),
            "recurse": "true",
        }
        if context_name:
            params["contextName"] = context_name
        result = self._call("spider", "action", "scan", params)
        self._spider_id = result.get("scan", "0")
        logger.info("Spider started, ID=%s", self._spider_id)
        return self._spider_id

    def spider_progress(self) -> int:
        if not self._spider_id:
            return 100
        data = self._call("spider", "view", "status", {"scanId": self._spider_id})
        return int(data.get("status", 100))

    def wait_for_spider(self, timeout: int = 120, poll_every: int = 5) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            progress = self.spider_progress()
            logger.debug("Spider progress: %d%%", progress)
            if progress >= 100:
                logger.info("Spider complete.")
                return
            time.sleep(poll_every)
        logger.warning("Spider timed out after %ds; continuing anyway.", timeout)

    # ------------------------------------------------------------------
    # Active scan
    # ------------------------------------------------------------------

    def start_active_scan(self, target: Optional[str] = None,
                          policy: Optional[str] = None) -> str:
        t = target or self.cfg.target_url
        p = policy or self.cfg.scan_policy
        logger.info("Starting ZAP active scan on %s (policy: %s) ...", t, p)
        result = self._call("ascan", "action", "scan", {
            "url": t,
            "scanPolicyName": p,
            "recurse": "true",
        })
        self._scan_id = result.get("scan", "0")
        logger.info("Active scan started, ID=%s", self._scan_id)
        return self._scan_id

    def scan_progress(self) -> int:
        if not self._scan_id:
            return 100
        data = self._call("ascan", "view", "status", {"scanId": self._scan_id})
        return int(data.get("status", 100))

    def wait_for_active_scan(self, timeout: Optional[int] = None,
                             poll_every: int = 10) -> None:
        deadline = time.time() + (timeout or self.cfg.active_scan_timeout)
        while time.time() < deadline:
            progress = self.scan_progress()
            logger.debug("Active scan progress: %d%%", progress)
            if progress >= 100:
                logger.info("Active scan complete.")
                return
            time.sleep(poll_every)
        logger.warning("Active scan timed out; fetching partial results.")

    # ------------------------------------------------------------------
    # Alerts / findings
    # BUG FIX: ZAP ignores any riskId parameter — filtering must be client-side
    # ------------------------------------------------------------------

    def get_raw_alerts(self, target: Optional[str] = None,
                       risk_threshold: int = 0) -> List[Dict]:
        """Return ZAP alerts at or above risk_threshold (client-side filter).

        NOTE: ZAP's alert API has NO server-side risk filter. We fetch all
        alerts and filter by riskcode ourselves. Passing 'riskId' to ZAP
        is silently ignored — that was a bug in the original implementation.
        """
        params: Dict[str, Any] = {}
        if target:
            params["baseurl"] = target
        data = self._call("alert", "view", "alerts", params)
        all_alerts = data.get("alerts", [])
        # Client-side filter: keep only alerts at or above the threshold
        return [
            a for a in all_alerts
            if int(a.get("riskcode", 0)) >= risk_threshold
        ]

    def get_findings(self, target: Optional[str] = None,
                     min_severity: SeverityLevel = SeverityLevel.LOW,
                     ) -> List[SecurityFinding]:
        """Return parsed SecurityFinding objects for the current scan."""
        risk_floor = {
            SeverityLevel.CRITICAL: 3,
            SeverityLevel.HIGH: 2,
            SeverityLevel.MEDIUM: 1,
            SeverityLevel.LOW: 0,
            SeverityLevel.INFORMATIONAL: -1,
        }.get(min_severity, 0)

        raw = self.get_raw_alerts(target, risk_threshold=max(risk_floor, 0))
        findings: List[SecurityFinding] = []
        seen: set = set()

        for alert in raw:
            key = (alert.get("alert", ""), alert.get("url", ""),
                   alert.get("evidence", ""))
            if key in seen:
                continue
            seen.add(key)

            severity = _RISK_MAP.get(str(alert.get("riskcode", "0")),
                                     SeverityLevel.LOW)
            findings.append(SecurityFinding(
                finding_id=alert.get("id", f"zap-{len(findings)}"),
                name=alert.get("alert", "Unknown"),
                severity=severity,
                url=alert.get("url", ""),
                description=alert.get("description", ""),
                solution=alert.get("solution", ""),
                cwe_id=alert.get("cweid"),
                wasc_id=alert.get("wascid"),
                evidence=alert.get("evidence"),
                confidence=alert.get("confidence", "Medium"),
                tags=alert.get("tags", []),
            ))

        logger.info("Found %d unique security findings (min severity: %s)",
                    len(findings), min_severity.value)
        return findings

    def run_full_scan(self, target: Optional[str] = None,
                      min_severity: SeverityLevel = SeverityLevel.MEDIUM,
                      ) -> List[SecurityFinding]:
        """Execute spider + active scan and return findings."""
        self.start_spider(target)
        self.wait_for_spider()
        self.start_active_scan(target)
        self.wait_for_active_scan()
        return self.get_findings(target, min_severity)

    def new_session(self, name: str = "security-test-orchestrator") -> None:
        """Start a fresh ZAP session (clears previous scan state)."""
        self._call("core", "action", "newSession",
                   {"name": name, "overwrite": "true"})
        self._scan_id = None
        self._spider_id = None
        logger.info("ZAP session '%s' started.", name)

    def get_version(self) -> str:
        """Return ZAP version — used as connectivity check."""
        data = self._call("core", "view", "version", {})
        return data.get("version", "unknown")
