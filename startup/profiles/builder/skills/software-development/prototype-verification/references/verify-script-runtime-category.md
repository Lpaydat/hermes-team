# Verify Script Category 5: Runtime Execution

Copy-paste code block for adding runtime execution checks to any verify script
that was built from an older version of the venture-prototype template (pre-2026-07-25).
Category 5 was added to the template on 2026-07-25, but builders may use a cached
copy. Append this block when the verify script lacks runtime checks.

## The problem

The original venture-prototype verify-script-template.md had 4 categories, all static.
A prototype could pass all 47 static checks and still crash on execution. The most
common pattern: optional imports guarded at module level but used unguarded inside
functions. Static analysis sees valid Python (AST parse passes, grep finds the
import). Only running the script exposes the crash.

**Fixed 2026-07-25:** The template now includes Category 5 (runtime execution) and
Category 4 (environment/import checks) by default. Always call skill_view for the
latest template — do not reuse a cached copy from a prior build.

## The fix — append this to every verify script

After Category 4 (build-rules), before the REPORT section:

```python
import subprocess, re

# ════════════════════════════════════════════════════════════════
# CATEGORY 5: RUNTIME EXECUTION (MANDATORY)
# Actually run the prototype and assert exit code + output content.
# This is the ONLY category that catches runtime crashes.
# ════════════════════════════════════════════════════════════════

# Adapt entry_script to your prototype's entry point
# CLI tools: scanner.py, main.py, app.py
# HTML prototypes: skip (note in report)
entry_script = os.path.join(proto_dir, "scanner.py")  # ADAPT THIS

if os.path.exists(entry_script):
    result = subprocess.run(
        [sys.executable, entry_script],
        capture_output=True, text=True, timeout=30, cwd=proto_dir
    )

    # Check: prototype executes without crash
    if result.returncode != 0:
        failures.append(f"RUNTIME CRASH: exit code {result.returncode}")
        # Capture last 5 lines of stderr for the report
        for line in result.stderr.strip().split('\n')[-5:]:
            failures.append(f"  stderr: {line}")
    else:
        output = result.stdout + result.stderr

        # Check: no traceback despite exit 0
        if "Traceback" in output:
            failures.append("Traceback in output despite exit 0")

        # Check: no NameError/ImportError (unguarded optional dependency)
        if "NameError" in output or "ImportError" in output:
            failures.append("Runtime import error (unguarded optional dependency)")

        # For metric-reporting prototypes (precision, recall, accuracy):
        # Parse ACTUAL values from stdout and verify thresholds.
        # Do NOT trust self-reported kanban_complete metadata — verify the
        # numbers appear in real program output.
        #
        # Example:
        # p_match = re.search(r'[Pp]recision:\s*([\d.]+)', output)
        # if p_match:
        #     precision = float(p_match.group(1))
        #     if precision < 35.0:
        #         failures.append(f"Precision {precision}% below 35% threshold")

    total_checks += 4  # Adjust count

    # Check: each documented flag runs without error
    for flag_desc in [("--brand", "Spotify"), ("--export", "json")]:  # ADAPT
        flag, val = flag_desc
        r = subprocess.run(
            [sys.executable, entry_script, flag, val],
            capture_output=True, text=True, timeout=30, cwd=proto_dir
        )
        if r.returncode != 0:
            failures.append(f"Flag {flag} {val}: exit {r.returncode}")

else:
    # HTML prototypes or non-Python entry points
    html_entry = os.path.join(proto_dir, "index.html")
    if os.path.exists(html_entry):
        print("NOTE: HTML prototype — runtime check skipped (verify in browser)")
    else:
        failures.append("No entry point found (no scanner.py, index.html, or app.py)")
```

## Why each check matters

1. **`returncode != 0`**: catches any crash — NameError, TypeError, KeyError,
   unhandled exception. The traceback in stderr names the exact line.

2. **Traceback despite exit 0**: some prototypes catch exceptions silently
   (`except: pass`) but the traceback still leaks to stderr. Exit 0 is misleading.

3. **NameError/ImportError in output**: the signature of unguarded optional
   imports. The module name exists in a `try/except` block at module level but
   is referenced directly in a function body without checking the `HAS_X` guard.

4. **Metric parsing**: prototypes that report precision/recall/accuracy in their
   output should have those metrics parsed from real stdout and verified against
   thresholds. Self-reported metadata in kanban_complete is not evidence — it's
   the builder's claim. Real program output is evidence.

5. **Flag testing**: each documented flag should run without error. A flag that
   silently no-ops or crashes is a broken contract.

## The unguarded optional import anti-pattern (root cause)

```python
# Module level — guarded:
try:
    import imagehash
    HAS_ICON_LIBS = True
except ImportError:
    HAS_ICON_LIBS = False

# Function level — UNGUARDED (bug):
def compute_icon_similarity(brand_hash, cand_hash):
    h1 = imagehash.hex_to_hash(brand_hash)  # NameError if imagehash not installed
    ...
```

Static analysis sees: valid import (AST parse OK), `imagehash` in scope (grep
finds it). Runtime: `NameError: name 'imagehash' is not defined` because the
`except ImportError` branch set `HAS_ICON_LIBS = False` but never defined
`imagehash` as a name.

The fix in the prototype: guard the function body:
```python
def compute_icon_similarity(brand_hash, cand_hash):
    if not HAS_ICON_LIBS:
        return 50.0  # neutral fallback
    h1 = imagehash.hex_to_hash(brand_hash)
    ...
```

But the verify script's job is to CATCH this before it ships, not to fix it.
Running the prototype is the only reliable detection.
