#!/usr/bin/env python3
"""
Workflow Engine — combined cron for the dev workflow.
See scripts/workflow-engine.py in the profile's scripts/ directory for the full source.
This is a symlink/reference — the actual script lives at:
  ~/.hermes-teams/startup/profiles/product-owner/scripts/workflow-engine.py

Runs three phases in order, every tick (1min):
  1. bead-sync:   sync kanban card status → bd bead status
  2. auto-dispatch: check bd ready → create tech-lead cards for new work
  3. board-scanner:  detect blocked tasks → escalate to proper profile

Zero-token (no_agent=True). Silent when nothing to do.
"""
