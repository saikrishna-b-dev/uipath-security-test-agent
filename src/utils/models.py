"""
Shared data models used across all agents.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class TestStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NOT_RUN = "not_run"
    IN_PROGRESS = "in_progress"


class SeverityLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class HealingAction(str, Enum):
    LOCATOR_UPDATE = "locator_update"
    ASSERTION_RELAX = "assertion_relax"
    TIMEOUT_INCREASE = "timeout_increase"
    SELECTOR_REGENERATE = "selector_regenerate"
    DATA_REFRESH = "data_refresh"
    SKIP_UNSTABLE = "skip_unstable"
    UNKNOWN = "unknown"


@dataclass
class SecurityFinding:
    """A single OWASP ZAP finding."""
    finding_id: str
    name: str
    severity: SeverityLevel
    url: str
    description: str
    solution: str
    cwe_id: Optional[str] = None
    wasc_id: Optional[str] = None
    evidence: Optional[str] = None
    confidence: str = "Medium"
    tags: List[str] = field(default_factory=list)
    discovered_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.finding_id,
            "name": self.name,
            "severity": self.severity.value,
            "url": self.url,
            "description": self.description,
            "solution": self.solution,
            "cwe": self.cwe_id,
            "wasc": self.wasc_id,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "tags": self.tags,
            "discovered_at": self.discovered_at.isoformat(),
        }


@dataclass
class TestFailure:
    """A test execution failure from Test Manager."""
    test_run_id: str
    test_case_id: str
    test_case_name: str
    status: TestStatus
    error_message: str
    stack_trace: Optional[str] = None
    screenshot_url: Optional[str] = None
    failed_at: datetime = field(default_factory=datetime.utcnow)
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagnosisResult:
    """Output from the Diagnosis Agent."""
    test_failure: TestFailure
    root_cause: str
    failure_category: str  # e.g. "locator_stale", "timing", "data_dependency"
    suggested_action: HealingAction
    confidence_score: float  # 0.0 – 1.0
    evidence: List[str] = field(default_factory=list)
    similar_past_failures: List[str] = field(default_factory=list)


@dataclass
class RepairResult:
    """Output from the Repair Agent."""
    diagnosis: DiagnosisResult
    action_taken: HealingAction
    patch_description: str
    original_code: Optional[str] = None
    patched_code: Optional[str] = None
    success: bool = False
    error: Optional[str] = None
    repaired_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ValidationResult:
    """Output from the Validation Agent."""
    repair: RepairResult
    re_run_passed: bool
    re_run_status: TestStatus
    validation_notes: str
    validated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class OrchestratorRun:
    """Top-level record of a full Monitor → Report cycle."""
    run_id: str
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    failures_detected: List[TestFailure] = field(default_factory=list)
    diagnoses: List[DiagnosisResult] = field(default_factory=list)
    repairs: List[RepairResult] = field(default_factory=list)
    validations: List[ValidationResult] = field(default_factory=list)
    security_findings: List[SecurityFinding] = field(default_factory=list)
    summary: Optional[str] = None

    @property
    def heal_rate(self) -> float:
        if not self.repairs:
            return 0.0
        successful = sum(1 for r in self.repairs if r.success)
        return successful / len(self.repairs)
