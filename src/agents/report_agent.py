"""
Report Agent — Agent 5 of 5
─────────────────────────────
Generates human-readable HTML and JSON reports from a completed OrchestratorRun.
Reports include: heal rate, security findings summary, OWASP risk heat-map, and
per-test-case healing details.

Outputs:
  • reports/run_{id}_summary.json  — machine-readable full run record
  • reports/run_{id}_report.html   — judge-friendly visual report
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, List

from src.config.settings import config
from src.utils.logger import get_logger
from src.utils.models import OrchestratorRun, SeverityLevel, ValidationResult

logger = get_logger("agents.report")


class ReportAgent:
    """
    Produces structured reports from a completed orchestrator run.

    Example:
        agent = ReportAgent()
        paths = agent.generate(orchestrator_run)
        print("Report written to:", paths["html"])
    """

    def __init__(self, output_dir: str = "") -> None:
        self.output_dir = output_dir or config.agent.report_output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate(self, run: OrchestratorRun) -> Dict[str, str]:
        """Generate JSON + HTML reports. Returns dict of {format: filepath}."""
        logger.info("Generating reports for run %s …", run.run_id)
        paths = {}
        paths["json"] = self._write_json(run)
        paths["html"] = self._write_html(run)
        logger.info("Reports written: %s", paths)
        return paths

    # ------------------------------------------------------------------
    # JSON report
    # ------------------------------------------------------------------

    def _write_json(self, run: OrchestratorRun) -> str:
        path = os.path.join(self.output_dir, f"run_{run.run_id[:8]}_summary.json")
        payload = {
            "run_id": run.run_id,
            "started_at": run.started_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "heal_rate": round(run.heal_rate, 3),
            "failures_detected": len(run.failures_detected),
            "repairs_attempted": len(run.repairs),
            "repairs_successful": sum(1 for r in run.repairs if r.success),
            "validations_passed": sum(1 for v in run.validations if v.re_run_passed),
            "security_findings": {
                "total": len(run.security_findings),
                "critical": sum(1 for f in run.security_findings if f.severity == SeverityLevel.CRITICAL),
                "high":     sum(1 for f in run.security_findings if f.severity == SeverityLevel.HIGH),
                "medium":   sum(1 for f in run.security_findings if f.severity == SeverityLevel.MEDIUM),
                "low":      sum(1 for f in run.security_findings if f.severity == SeverityLevel.LOW),
            },
            "findings_detail": [f.to_dict() for f in run.security_findings],
            "validations": [
                {
                    "test_case": v.repair.diagnosis.test_failure.test_case_name,
                    "category": v.repair.diagnosis.failure_category,
                    "action": v.repair.action_taken.value,
                    "healed": v.re_run_passed,
                    "notes": v.validation_notes,
                }
                for v in run.validations
            ],
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)
        return path

    # ------------------------------------------------------------------
    # HTML report
    # ------------------------------------------------------------------

    def _write_html(self, run: OrchestratorRun) -> str:
        path = os.path.join(self.output_dir, f"run_{run.run_id[:8]}_report.html")
        html = self._render_html(run)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
        return path

    def _render_html(self, run: OrchestratorRun) -> str:  # noqa: C901
        heal_pct = int(run.heal_rate * 100)
        elapsed = ""
        if run.completed_at:
            secs = int((run.completed_at - run.started_at).total_seconds())
            elapsed = f"{secs // 60}m {secs % 60}s"

        sev_counts = {s: 0 for s in SeverityLevel}
        for f in run.security_findings:
            sev_counts[f.severity] += 1

        # Severity badge colours
        SEV_COLORS = {
            SeverityLevel.CRITICAL: "#dc2626",
            SeverityLevel.HIGH: "#ea580c",
            SeverityLevel.MEDIUM: "#d97706",
            SeverityLevel.LOW: "#16a34a",
            SeverityLevel.INFORMATIONAL: "#6b7280",
        }

        def badge(sev: SeverityLevel, count: int) -> str:
            if count == 0:
                return ""
            return (f'<span style="background:{SEV_COLORS[sev]};color:#fff;'
                    f'padding:2px 8px;border-radius:12px;font-size:12px;margin-right:4px">'
                    f'{sev.value.upper()} {count}</span>')

        findings_rows = "".join(
            '<tr><td>{name}</td><td>{sev}</td>'
            '<td style="max-width:300px;overflow:hidden;text-overflow:ellipsis">{url}</td>'
            '<td>CWE-{cwe}</td></tr>'.format(
                name=f.name, sev=badge(f.severity, 1), url=f.url, cwe=f.cwe_id or "N/A"
            )
            for f in sorted(run.security_findings, key=lambda x: list(SeverityLevel).index(x.severity))
        )

        heal_rows = "".join(
            '<tr><td>{tc}</td><td>{cat}</td><td>{act}</td>'
            '<td style="color:{color};font-weight:bold">{outcome}</td></tr>'.format(
                tc=v.repair.diagnosis.test_failure.test_case_name,
                cat=v.repair.diagnosis.failure_category,
                act=v.repair.action_taken.value,
                color="#16a34a" if v.re_run_passed else "#dc2626",
                outcome="&#x2705; HEALED" if v.re_run_passed else "&#x274C; FAILED",
            )
            for v in run.validations
        )

        # Pre-compute conditional sections — Python 3.10 forbids nested f-strings
        # that reuse the same quote delimiter as the outer template.
        if run.security_findings:
            findings_section = (
                "<table>\n  <thead><tr>"
                "<th>Finding</th><th>Severity</th><th>URL</th><th>CWE</th>"
                "</tr></thead>\n  <tbody>" + findings_rows + "</tbody>\n</table>"
            )
        else:
            findings_section = (
                "<p style='color:#64748b;font-style:italic'>"
                "No security findings this cycle.</p>"
            )

        if run.validations:
            heal_section = (
                "<table>\n  <thead><tr>"
                "<th>Test Case</th><th>Failure Category</th>"
                "<th>Healing Action</th><th>Outcome</th>"
                "</tr></thead>\n  <tbody>" + heal_rows + "</tbody>\n</table>"
            )
        else:
            heal_section = (
                "<p style='color:#64748b;font-style:italic'>"
                "No test failures detected this cycle.</p>"
            )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Security Test Orchestrator — Run Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          margin: 0; padding: 24px; background: #f8fafc; color: #1e293b; }}
  h1   {{ color: #0f172a; border-bottom: 3px solid #f97316; padding-bottom: 8px; }}
  h2   {{ color: #475569; margin-top: 32px; }}
  .metrics {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 24px 0; }}
  .card {{ background: #fff; border-radius: 12px; padding: 20px 28px;
           box-shadow: 0 1px 4px rgba(0,0,0,.1); min-width: 140px; }}
  .card-value {{ font-size: 2.4rem; font-weight: 700; color: #f97316; }}
  .card-label {{ font-size: 0.85rem; color: #64748b; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff;
           border-radius: 8px; overflow: hidden;
           box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-top: 12px; }}
  th {{ background: #1e293b; color: #fff; text-align: left; padding: 10px 14px; font-size: 13px; }}
  td {{ padding: 9px 14px; border-bottom: 1px solid #f1f5f9; font-size: 13px; }}
  tr:last-child td {{ border-bottom: none; }}
  .tag {{ background: #e2e8f0; padding: 2px 8px; border-radius: 10px;
          font-size: 11px; color: #475569; }}
  footer {{ margin-top: 48px; color: #94a3b8; font-size: 12px; text-align: center; }}
</style>
</head>
<body>
<h1>🔐 UiPath Security Test Orchestrator — Run Report</h1>
<p style="color:#64748b">
  Run ID: <code>{run.run_id}</code> &nbsp;|&nbsp;
  Started: {run.started_at.strftime("%Y-%m-%d %H:%M UTC")} &nbsp;|&nbsp;
  Duration: {elapsed}
</p>

<div class="metrics">
  <div class="card"><div class="card-value">{len(run.failures_detected)}</div><div class="card-label">Failures Detected</div></div>
  <div class="card"><div class="card-value">{heal_pct}%</div><div class="card-label">Self-Heal Rate</div></div>
  <div class="card"><div class="card-value">{sum(1 for v in run.validations if v.re_run_passed)}</div><div class="card-label">Tests Healed</div></div>
  <div class="card"><div class="card-value">{len(run.security_findings)}</div><div class="card-label">Security Findings</div></div>
  <div class="card"><div class="card-value" style="color:#dc2626">{sev_counts[SeverityLevel.CRITICAL]+sev_counts[SeverityLevel.HIGH]}</div><div class="card-label">Critical/High Findings</div></div>
</div>

<h2>&#x1F6E1; Security Findings</h2>
<p>
  {badge(SeverityLevel.CRITICAL, sev_counts[SeverityLevel.CRITICAL])}
  {badge(SeverityLevel.HIGH, sev_counts[SeverityLevel.HIGH])}
  {badge(SeverityLevel.MEDIUM, sev_counts[SeverityLevel.MEDIUM])}
  {badge(SeverityLevel.LOW, sev_counts[SeverityLevel.LOW])}
</p>
{findings_section}

<h2>&#x1F527; Self-Healing Results</h2>
{heal_section}

<footer>
  Generated by <strong>UiPath Security Test Orchestrator</strong> &mdash;
  UiPath AgentHack 2026, Track 3: Test Cloud &mdash;
  {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
</footer>
</body>
</html>"""
