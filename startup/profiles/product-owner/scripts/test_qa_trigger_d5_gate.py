#!/usr/bin/env python3
"""D5 gate test for phase_qa_trigger (hermes-hq t_b5d33aeb).

Sandbox scenarios against the patched workflow-engine.py:
  A. local master ahead of origin (unpushed)      -> NO card  (old code cut one)
  B. code push to origin + recent verifier card   -> card citing origin merge commit
  C. docs-only push to origin                     -> NO card
  D. history rewrite on origin (force-push)       -> tracker reset, NO card
"""
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ENGINE = Path.home() / ".hermes-teams/startup/profiles/product-owner/scripts/workflow-engine.py"

spec = importlib.util.spec_from_file_location("workflow_engine", ENGINE)
we = importlib.util.module_from_spec(spec)
spec.loader.exec_module(we)

FAILURES = []

def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)

def git(repo, *args, **kw):
    return subprocess.run(["git", "-C", str(repo)] + list(args),
                          capture_output=True, text=True, timeout=30, **kw)

def make_sandbox():
    """bare origin + clone with one code commit; returns (origin, clone)."""
    tmp = Path(tempfile.mkdtemp(prefix="d5gate-"))
    origin = tmp / "origin.git"
    clone = tmp / "proj"
    subprocess.run(["git", "init", "--bare", "-b", "master", str(origin)],
                   capture_output=True, check=True)
    subprocess.run(["git", "clone", str(origin), str(clone)],
                   capture_output=True, check=True)
    git(clone, "config", "user.email", "t@t")
    git(clone, "config", "user.name", "t")
    (clone / "app.py").write_text("print('v1')\n")
    git(clone, "add", "-A")
    git(clone, "commit", "-m", "v1", "-q")
    git(clone, "push", "-q", "origin", "master")
    return tmp, origin, clone

def make_board(root, board, verifier_done=True):
    """minimal kanban.db with the columns phase_qa_trigger reads."""
    bdir = root / "boards" / board
    if bdir.exists():
        shutil.rmtree(bdir)
    bdir.mkdir(parents=True)
    db = bdir / "kanban.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE tasks (id TEXT, title TEXT, assignee TEXT, "
                 "status TEXT, completed_at INT, idempotency_key TEXT)")
    conn.execute("CREATE TABLE task_runs (id INTEGER PRIMARY KEY, task_id TEXT, "
                 "outcome TEXT, summary TEXT)")
    if verifier_done:
        conn.execute("INSERT INTO tasks VALUES ('t_v1','[verify-b] fix X','verifier','done',?,NULL)",
                     (int(time.time()) - 60,))
        conn.execute("INSERT INTO task_runs (task_id,outcome,summary) VALUES "
                     "('t_v1','completed','PASS merged fix abc1234 (stale sha)')")
    conn.commit(); conn.close()
    return db

def fresh_state(root):
    we.QA_TRIGGER_STATE_FILE = root / "qa-trigger-state.json"
    if we.QA_TRIGGER_STATE_FILE.exists():
        we.QA_TRIGGER_STATE_FILE.unlink()
    we.KANBAN_ROOT = root / "boards"

def setup(root, origin, clone, board="sandbox", verifier_done=True):
    shutil.rmtree(root / "boards", ignore_errors=True)
    make_board(root, board, verifier_done)
    fresh_state(root)
    created = []
    def fake_run_kanban(b, args):
        created.append((b, list(args)))
        return True, "{}"
    we.run_kanban = fake_run_kanban
    we.DRY_RUN = False
    return created

def card_sha(created):
    for b, args in created:
        if args and args[0] == "create" and "Re-test after merge:" in args[1]:
            return args[1].split(":")[1].strip(), args
    return None, None

def card_body(args):
    return args[args.index("--body") + 1]

# ── Scenario A: local master ahead of origin (the 6-instance wrong-HEAD class)
tmp, origin, clone = make_sandbox()
root = tmp / "state"; root.mkdir()
created = setup(root, origin, clone)
git(clone, "fetch", "-q", "origin")
# first run seeds state at origin/master tip
a1 = we.phase_qa_trigger("sandbox", str(clone))
# now commit locally WITHOUT pushing, verifier card still 'done'
(clone / "app.py").write_text("print('v2 unpushed')\n")
git(clone, "add", "-A"); git(clone, "commit", "-q", "-m", "v2 unpushed fix")
a2 = we.phase_qa_trigger("sandbox", str(clone))
sha, _ = card_sha(created)
check("A: unpushed local master cuts NO card", sha is None and not a2,
      f"created={created} actions={a2}")

# push it -> card MUST appear citing the origin/master sha
git(clone, "push", "-q", "origin", "master")
a3 = we.phase_qa_trigger("sandbox", str(clone))
sha, args = card_sha(created)
origin_tip = git(clone, "rev-parse", "--short=12", "origin/master").stdout.strip()
check("A→B: after push, card cites origin/master tip", sha == origin_tip,
      f"card sha={sha} origin/master={origin_tip}")
body = card_body(args)
check("B: body cites merge commit + merge-diff instructions",
      "Merge commit (origin/master)" in body and "merge-base" in body
      and "NOT pin or re-test" in body and f"{sha}" in body)

# ── Scenario C: docs-only push -> no card
(clone / "NOTES.md").write_text("docs only\n")
git(clone, "add", "-A"); git(clone, "commit", "-q", "-m", "docs only")
git(clone, "push", "-q", "origin", "master")
created.clear()
c1 = we.phase_qa_trigger("sandbox", str(clone))
sha, _ = card_sha(created)
check("C: docs-only push cuts NO card", sha is None, f"created={created}")

# ── Scenario D: history rewrite (force-push) -> tracker reset, no card
git(clone, "reset", "-q", "--hard", "HEAD~1")
git(clone, "push", "-q", "--force", "origin", "master")
(clone / "app.py").write_text("print('v3 rewritten')\n")
git(clone, "add", "-A"); git(clone, "commit", "-q", "-m", "v3 rewrite")
git(clone, "push", "-q", "--force", "origin", "master")
created.clear()
d1 = we.phase_qa_trigger("sandbox", str(clone))
sha, _ = card_sha(created)
check("D: history rewrite resets tracker, cuts NO card on first sight",
      sha is None and any("history rewrite" in a for a in d1),
      f"actions={d1} created={created}")
# rewrite absorbed: next landing advances cleanly from the reset base
(clone / "app.py").write_text("print('v3b new landing')\n")
git(clone, "add", "-A"); git(clone, "commit", "-q", "-m", "v3b new landing")
git(clone, "push", "-q", "origin", "master")
d2 = we.phase_qa_trigger("sandbox", str(clone))
sha, _ = card_sha(created)
check("D2: post-rewrite next landing cuts card normally", sha is not None,
      f"created={created}")

# ── Scenario E: no verifier card -> no card even on code push (regression guard)
(clone / "app.py").write_text("print('v4')\n")
git(clone, "add", "-A"); git(clone, "commit", "-q", "-m", "v4")
git(clone, "push", "-q", "origin", "master")
make_board(root, "sandbox", verifier_done=False)
created.clear()
e1 = we.phase_qa_trigger("sandbox", str(clone))
sha, _ = card_sha(created)
check("E: code push WITHOUT verifier card cuts NO card", sha is None,
      f"created={created}")

print()
if FAILURES:
    print(f"RESULT: {len(FAILURES)} FAILURE(S): {FAILURES}")
    sys.exit(1)
print("RESULT: all D5 gate checks passed")
shutil.rmtree(tmp, ignore_errors=True)
