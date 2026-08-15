#!/usr/bin/env python3
"""Wrapper — runs the workflow engine tick + park healer from the shared location."""
import sys
from pathlib import Path

engine = Path.home() / ".hermes-teams/startup/scripts/workflow_engine"
sys.path.insert(0, str(engine))

# 1. heal stranded dependency parks (sticky 'dependency:' blocks, parents done)
try:
    from park_healer import heal
    for line in heal():
        print(line)
except Exception as e:  # healer must never break the tick
    print(f"park_healer error (non-fatal): {e}")

# 2. engine tick
sys.argv = [str(engine / "main.py")] + sys.argv[1:]
if len(sys.argv) == 1:
    sys.argv.append("tick")  # default to tick if no subcommand

exec(open(engine / "main.py").read())
