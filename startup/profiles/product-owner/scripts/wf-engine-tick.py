#!/usr/bin/env python3
"""Wrapper — runs the workflow engine tick from the shared location."""
import sys
from pathlib import Path

engine_main = Path.home() / ".hermes-teams/startup/scripts/workflow_engine/main.py"
sys.argv = [str(engine_main)] + sys.argv[1:]
if len(sys.argv) == 1:
    sys.argv.append("tick")  # default to tick if no subcommand

exec(open(engine_main).read())
