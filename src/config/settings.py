"""
Central configuration for the UiPath Security Test Orchestrator.
All environment variables and constants live here.
"""
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UiPathConfig:
    """UiPath Cloud / Test Manager connection settings."""
    base_url: str = os.getenv("UIPATH_BASE_URL", "https://staging.uipath.com")
    org_name: str = os.getenv("UIPATH_ORG", "hackathon26_154")
    tenant_name: str = os.getenv("UIPATH_TENANT", "DefaultTenant")
    client_id: str = os.getenv("UIPATH_CLIENT_ID", "")
    client_secret: str = os.getenv("UIPATH_CLIENT_SECRET", "")
    # Test Manager project
    tm_project_id: str = os.getenv("TM_PROJECT_ID", "")
    tm_project_key: str = os.getenv("TM_PROJECT_KEY", "SSTO")

    @property
    def tm_base(self) -> str:
        return f"{self.base_url}/{self.org_name}/{self.tenant_name}/testmanager_"

    @property
    def portal_base(self) -> str:
        return f"{self.base_url}/{self.org_name}/portal_"


@dataclass
class OWASPConfig:
    """OWASP ZAP configuration."""
    zap_host: str = os.getenv("ZAP_HOST", "localhost")
    zap_port: int = int(os.getenv("ZAP_PORT", "8080"))
    zap_api_key: str = os.getenv("ZAP_API_KEY", "changeme")
    target_url: str = os.getenv("TARGET_URL", "http://localhost:3000")  # default: OWASP Juice Shop
    scan_policy: str = os.getenv("ZAP_SCAN_POLICY", "Default Policy")
    spider_max_depth: int = int(os.getenv("ZAP_SPIDER_DEPTH", "5"))
    active_scan_timeout: int = int(os.getenv("ZAP_SCAN_TIMEOUT", "300"))  # seconds

    @property
    def zap_url(self) -> str:
        return f"http://{self.zap_host}:{self.zap_port}"


@dataclass
class AgentConfig:
    """Agent runtime settings."""
    poll_interval_seconds: int = int(os.getenv("POLL_INTERVAL", "30"))
    max_repair_attempts: int = int(os.getenv("MAX_REPAIR_ATTEMPTS", "3"))
    healing_confidence_threshold: float = float(os.getenv("HEALING_THRESHOLD", "0.75"))
    report_output_dir: str = os.getenv("REPORT_DIR", "./reports")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    dry_run: bool = os.getenv("DRY_RUN", "false").lower() == "true"


@dataclass
class AppConfig:
    uipath: UiPathConfig = field(default_factory=UiPathConfig)
    owasp: OWASPConfig = field(default_factory=OWASPConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)


# Singleton config — import and use anywhere
config = AppConfig()
