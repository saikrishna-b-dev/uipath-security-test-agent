#!/usr/bin/env python3
"""
UiPath Security Test Orchestrator — main entry point.

Usage:
    # Run one cycle (for testing / CI)
    python main.py --once

    # Run the production polling loop
    python main.py --loop

    # Dry-run (no real API writes, no ZAP required)
    DRY_RUN=true python main.py --once

    # Show version / config
    python main.py --info
"""
import argparse
import sys

from src.config.settings import config
from src.orchestrator.maestro_orchestrator import MaestroOrchestrator
from src.utils.logger import get_logger

logger = get_logger("main")


def print_info() -> None:
    print("=" * 55)
    print("  UiPath Security Test Orchestrator")
    print("  UiPath AgentHack 2026 — Track 3: Test Cloud")
    print("=" * 55)
    print(f"  UiPath env   : {config.uipath.base_url}")
    print(f"  Org          : {config.uipath.org_name}")
    print(f"  Tenant       : {config.uipath.tenant_name}")
    print(f"  TM project   : {config.uipath.tm_project_key}")
    print(f"  ZAP target   : {config.owasp.target_url}")
    print(f"  Poll interval: {config.agent.poll_interval_seconds}s")
    print(f"  Heal threshold: {config.agent.healing_confidence_threshold}")
    print(f"  Dry run      : {config.agent.dry_run}")
    print("=" * 55)


def main() -> int:
    parser = argparse.ArgumentParser(description="UiPath Security Test Orchestrator")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once",  action="store_true", help="Run a single cycle and exit")
    mode.add_argument("--loop",  action="store_true", help="Run indefinitely (production mode)")
    mode.add_argument("--info",  action="store_true", help="Print configuration and exit")
    parser.add_argument("--cycles", type=int, default=None,
                        help="Max cycles for --loop (omit = infinite)")
    args = parser.parse_args()

    if args.info:
        print_info()
        return 0

    print_info()
    orchestrator = MaestroOrchestrator()

    if args.once:
        logger.info("Running single cycle …")
        paths = orchestrator.run_cycle()
        logger.info("Done. Reports: %s", paths)
    elif args.loop:
        logger.info("Starting production loop …")
        orchestrator.run_loop(max_cycles=args.cycles)

    return 0


if __name__ == "__main__":
    sys.exit(main())
