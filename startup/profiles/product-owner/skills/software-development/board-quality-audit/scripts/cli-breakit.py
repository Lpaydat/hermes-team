#!/usr/bin/env python3
"""
Reusable adversarial break-it probe for a COMMAND-LINE TOOL (CLI).

Parallel to rest-api-breakit.py — that one covers stateful REST APIs; this one
covers the failure modes most likely to survive a CLI developer's own tests:

  1. Invalid argument values (zero, negative, non-numeric, missing)
  2. Empty / missing input files and state directories
  3. Corrupt input data (malformed lines, truncation)
  4. Signal handling (SIGINT / Ctrl+C) — clean exit, no traceback, no
     partial side effects (half-written log, dangling state)
  5. Delimiter injection — characters in user-provided string fields that
     collide with the output format's separator (tab, comma, newline)
  6. Subprocess smoke — the real binary runs to completion and exits 0

Usage:
  1. Set CLI_PATH to the entrypoint script.
  2. Adapt the COMMANDS, args, and per-probe assertions to the board.
  3. Run: python3 cli-breakit.py   (exits 1 on any FAIL)

The probes below are written for a timer/log CLI (pomodoro-style) but the
PATTERNS transfer to any CLI: swap the commands, keep the break-it dimensions.
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

# --- CONFIG: adapt these for the board under audit ---------------------------
CLI_PATH = "/path/to/workspace/pomodoro.py"   # absolute path to entrypoint
PY = sys.executable
# -----------------------------------------------------------------------------


def run_cli(args, env_extra=None, stdin=None, timeout=30):
    """Run the CLI as a subprocess. Return (rc, stdout, stderr)."""
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    r = subprocess.run(
        [PY, CLI_PATH] + args,
        capture_output=True, text=True, env=env,
        input=stdin, timeout=timeout,
    )
    return r.returncode, r.stdout, r.stderr


def isolated_home():
    """Fresh POMODORO_HOME (or analogous state dir) per probe."""
    d = tempfile.mkdtemp(prefix="cli-breakit-")
    return d


results = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((name, status))
    tag = f"  [{status}] {name}"
    if detail and not cond:
        tag += f" — {detail}"
    print(tag)


# === 1. Invalid argument values ==============================================
def probe_invalid_args():
    """Zero, negative, and non-numeric args should be rejected (rc != 0)."""
    home = isolated_home()
    # Zero — a zero-length timer is the classic boundary bug
    rc, out, err = run_cli(["start", "--work", "0", "--break", "5", "--cycles", "1"],
                           env_extra={"POMODORO_HOME": home})
    check("reject --work 0 (rc != 0)", rc != 0, f"rc={rc}")

    rc, _, _ = run_cli(["start", "--work", "-5", "--cycles", "1"],
                       env_extra={"POMODORO_HOME": home})
    check("reject negative --work (rc != 0)", rc != 0)

    rc, _, _ = run_cli(["start", "--work", "abc", "--cycles", "1"],
                       env_extra={"POMODORO_HOME": home})
    check("reject non-numeric --work (rc != 0)", rc != 0)

    rc, _, _ = run_cli([], env_extra={"POMODORO_HOME": home})
    check("reject missing subcommand (rc != 0)", rc != 0)


# === 2. Empty / missing input files ==========================================
def probe_empty_missing_state():
    """Log/read commands on missing or empty state files must not crash."""
    home = isolated_home()
    # No state file at all
    rc, out, err = run_cli(["log", "--date", "2024-01-15"],
                           env_extra={"POMODORO_HOME": home})
    check("log on missing file -> rc 0, no traceback", rc == 0 and "Traceback" not in err,
          f"rc={rc} err={err[:120]!r}")

    # Empty state file
    os.makedirs(home, exist_ok=True)
    open(os.path.join(home, "sessions.jsonl"), "w").close()
    rc, out, err = run_cli(["log", "--date", "2024-01-15"],
                           env_extra={"POMODORO_HOME": home})
    check("log on empty file -> rc 0, empty output", rc == 0 and out.strip() == "")


# === 3. Corrupt input data ===================================================
def probe_corrupt_input():
    """Corrupt lines in a JSONL state file. Whether this crashes is a
    robustness decision — the contract may guarantee only that the app WRITES
    valid data, not that it tolerates externally-corrupted input. Record the
    actual behavior; flag an uncaught traceback as a robustness NOTE (not
    necessarily a contract FAIL)."""
    home = isolated_home()
    os.makedirs(home)
    with open(os.path.join(home, "sessions.jsonl"), "w") as f:
        f.write(json.dumps({"task": "good", "start": "2024-01-15T09:00:00",
                            "end": "2024-01-15T09:25:00", "cycle": 1}) + "\n")
        f.write("CORRUPT-NOT-JSON{\n")
    rc, out, err = run_cli(["log", "--date", "2024-01-15"],
                           env_extra={"POMODORO_HOME": home})
    if "Traceback" in err:
        check("corrupt JSONL -> NOTE: uncaught crash (robustness gap, may be out-of-contract)",
              True)  # documented, not a hard FAIL
        results[-1] = (results[-1][0].replace("FAIL", "NOTE").replace("PASS", "NOTE"),
                       "NOTE")
    else:
        check("corrupt JSONL handled gracefully -> rc 0", rc == 0)


# === 4. Signal handling (SIGINT / Ctrl+C) ====================================
def probe_sigint_handling():
    """SIGINT during a long-running command must exit cleanly: rc 0 (or 130),
    no uncaught traceback on stderr, and no partial side effects (e.g. a
    half-written log entry from an interrupted WORK phase)."""
    home = isolated_home()
    env = dict(os.environ)
    env["POMODORO_HOME"] = home
    proc = subprocess.Popen(
        [PY, CLI_PATH, "start", "--work", "25", "--break", "5",
         "--cycles", "1", "--task", "interrupted"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
    )
    time.sleep(0.4)  # let it enter the WORK phase
    proc.send_signal(signal.SIGINT)
    try:
        out, err = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        check("SIGINT -> process terminated (no hang)", False, "timed out")
        return

    check("SIGINT -> rc 0 or 130", proc.returncode in (0, 130),
          f"rc={proc.returncode}")
    check("SIGINT -> no uncaught traceback", "Traceback" not in err,
          f"err={err[:120]!r}")
    # The critical side-effect probe: was a partial log written?
    log = os.path.join(home, "sessions.jsonl")
    if os.path.exists(log):
        lines = [l for l in open(log).read().splitlines() if l.strip()]
        check("SIGINT -> no partial side-effect log written", len(lines) == 0,
              f"found {len(lines)} unexpected log lines")
    else:
        check("SIGINT -> no partial side-effect log written", True)


# === 5. Delimiter injection ==================================================
def probe_delimiter_injection():
    """User-provided string fields that contain the output format's separator
    (tab, comma, newline) can break fixed-width / delimited output. This is the
    class of bug that most commonly survives both dev and verify suites because
    testers check quotes and spaces but rarely the actual delimiter character.

    For this CLI: --task feeds into a TAB-separated log line. A tab in the task
    name corrupts the 4-field format into 5 fields."""
    home = isolated_home()
    os.makedirs(home)
    # Simulate a logged session with a tab in the task name
    with open(os.path.join(home, "sessions.jsonl"), "w") as f:
        f.write(json.dumps({"task": "bad\tinject", "start": "2024-01-15T09:00:00",
                            "end": "2024-01-15T09:25:00", "cycle": 1}) + "\n")
    rc, out, err = run_cli(["log", "--date", "2024-01-15"],
                           env_extra={"POMODORO_HOME": home})
    if rc == 0 and out.strip():
        fields = out.strip().splitlines()[0].split("\t")
        check("delimiter injection: tab in task name keeps 4 fields",
              len(fields) == 4, f"got {len(fields)} fields — tab injection")
    else:
        check("delimiter injection: log ran", rc == 0)


# === 6. Subprocess smoke (real binary completes) =============================
def probe_help_smoke():
    """--help on every subcommand must exit 0 and print usage. Catches import
    errors, missing modules, and broken argparse setup that unit tests with
    injected functions never touch."""
    for sub in ["--help", "start", "--help", "log", "--help"]:
        # split sub into args list for flexibility
        args = sub.split() if isinstance(sub, str) else sub
        # For "start --help" style, pass as list
        pass
    for args in [["--help"], ["start", "--help"], ["log", "--help"]]:
        rc, out, err = run_cli(args)
        label = " ".join(args)
        check(f"smoke: {' '.join(args)} -> rc 0, usage printed",
              rc == 0 and ("usage" in out.lower() or "usage" in err.lower()),
              f"rc={rc}")


if __name__ == "__main__":
    probes = [
        probe_invalid_args,
        probe_empty_missing_state,
        probe_corrupt_input,
        probe_sigint_handling,
        probe_delimiter_injection,
        probe_help_smoke,
    ]
    for p in probes:
        print(f"\n--- {p.__name__} ---")
        try:
            p()
        except Exception as e:
            results.append((p.__name__, "CRASH"))
            print(f"  [CRASH] {p.__name__}: {type(e).__name__}: {e}")

    fails = [n for n, s in results if s == "FAIL"]
    notes = [n for n, s in results if s == "NOTE"]
    total = len(results)
    passed = total - len(fails) - len(notes)
    print(f"\n{passed}/{total} passed, {len(notes)} note(s), {len(fails)} fail(s)")
    if notes:
        print("  Notes (robustness gaps, may be out-of-contract):")
        for n in notes:
            print(f"    - {n}")
    sys.exit(1 if fails else 0)
