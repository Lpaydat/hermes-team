#!/usr/bin/env python3
"""Wrapper — runs the workflow engine tick from the shared location."""
import sys
from pathlib import Path

engine_main = Path.home() / ".hermes-teams/startup/scripts/workflow_engine/main.py"
exec(open(engine_main).read())
