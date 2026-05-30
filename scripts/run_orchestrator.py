#!/usr/bin/env python3
"""
Entry point for the UiPath Security Test Orchestrator.
Loads config, initialises all 5 agents, and starts the Maestro-driven loop.

Usage:
    python scripts/run_orchestrator.py
    python scripts/run_orchestrator.py --once        # single run, then exit
    python scripts/run_orchestrator.py --dry-run     # diagnose only, no repairs
"""

import sys
import os
import argparse

# Allow running from repo root or from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from main import main

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='UiPath Security Test Orchestrator')
    parser.add_argument('--once',    action='store_true', help='Run one cycle and exit')
    parser.add_argument('--dry-run', action='store_true', help='Diagnose only — no repairs applied')
    args = parser.parse_args()
    main(once=args.once, dry_run=args.dry_run)
