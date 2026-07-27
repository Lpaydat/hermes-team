# Verification Script Template

Write this to `/tmp/verify-<slug>.py` before calling loop_engine. It parses locked decisions from context/ and checks the prototype + README against them.

**Minimum requirement: 20 checks.** If your script has fewer, it is not thorough enough. The RouteOpt prototype used 48 checks. Aim for that level of coverage.

The script must check FIVE categories:
1. **Structural checks** (directories, files exist; prototype type determined — HTML vs CLI vs API)
2. **Decision-content checks** (specific decisions from context/ are reflected in the prototype)
3. **README checks** (all 9 sections, decision IDs referenced, specific How-to-Review steps)
4. **Build-rule checks** (zero dependencies, simulated data label, environment checks)
5. **Runtime execution checks** (subprocess-run the prototype, assert exit code 0, parse output)

**CRITICAL: Category 5 (runtime execution) is MANDATORY.** Static-only checks (AST parse, grep, regex) are NOT sufficient — they catch syntax errors but NOT runtime crashes. The prototype MUST execute without crashing. The verify script MUST run it and assert exit code 0.

```python
#!/usr/bin/env python3
"""Verify <slug> prototype against grill decisions in context/.

FIVE categories. Category 5 (runtime execution) is mandatory — it catches
crashes that static analysis cannot detect (import errors, missing deps, logic bugs).
"""
import os, re, sys, subprocess, ast

SLUG = "<slug>"
context_dir = os.path.expanduser(f"~/projects/{SLUG}/context")
proto_dir = os.path.expanduser(f"~/projects/{SLUG}/prototype")
readme_path = os.path.expanduser(f"~/projects/{SLUG}/README.md")
html_path = os.path.join(proto_dir, "index.html")
script_path_guess = os.path.join(proto_dir, "scanner.py")  # CLI prototypes
app_path_guess = os.path.join(proto_dir, "app.py")          # API prototypes

failures = []

# ── Parse locked decisions from context/ ──
decisions = {}
for f in sorted(os.listdir(context_dir)):
    if f.startswith("_") or not f.endswith(".md"):
        continue
    with open(os.path.join(context_dir, f)) as fh:
        for line in fh:
            m = re.match(r'(?:Lock\s+)?(D\d+):\s*(.+?)\s*=\s*(.+)', line.strip())
            if m:
                decisions[m.group(1)] = (m.group(2).strip(), m.group(3).strip())

print(f"Parsed {len(decisions)} decisions from {len(os.listdir(context_dir))} files")

# ── Detect prototype type ──
is_html = os.path.exists(html_path)
is_python_cli = os.path.exists(script_path_guess)
is_python_api = os.path.exists(app_path_guess)
proto_type = "html" if is_html else ("api" if is_python_api else "cli" if is_python_cli else "unknown")
print(f"Prototype type: {proto_type}")

# ── Load files ──
html = ""
html_lower = ""
if is_html:
    html = open(html_path).read()
    html_lower = html.lower()

cli_src = ""
if is_python_cli:
    cli_src = open(script_path_guess).read()
elif is_python_api:
    cli_src = open(app_path_guess).read()

readme = ""
readme_lower = ""
if os.path.exists(readme_path):
    readme = open(readme_path).read()
    readme_lower = readme.lower()
else:
    failures.append("README.md does not exist")

# ════════════════════════════════════════════════════════════════
# CATEGORY 1: STRUCTURAL CHECKS (files exist, well-formed)
# ════════════════════════════════════════════════════════════════

# Check: Prototype directory has files
if not os.path.isdir(proto_dir) or not os.listdir(proto_dir):
    failures.append("No prototype files in prototype/")

# HTML-specific structural checks
if is_html:
    # Check: HTML has DOCTYPE
    if not html.lstrip().startswith("<!DOCTYPE"):
        failures.append("HTML missing DOCTYPE declaration")

    # Check: HTML has <html> and </html> tags
    if "<html" not in html_lower or "</html>" not in html_lower:
        failures.append("HTML missing <html>/</html> tags")

    # Check: JS braces balanced (no syntax errors in script blocks)
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.S)
    for i, s in enumerate(scripts):
        if s.count('{') != s.count('}'):
            failures.append(f"Script block {i}: unbalanced braces ({s.count('{')} open vs {s.count('}')} close)")

    # Check: Tab/section mechanism exists (adapt to your prototype's pattern)
    tab_patterns = [
        (r'data-tab=', 'data-tab attributes'),
        (r'onclick=[\"\']\s*showtab', 'onclick showTab'),
        (r'class=[\"\']tab', 'class=tab elements'),
        (r'data-section=', 'data-section attributes'),
    ]
    # At least ONE tab mechanism should exist for multi-tab prototypes
    # (Remove this check if your prototype is single-page with no tabs)

# Python-specific structural checks
if is_python_cli or is_python_api:
    try:
        ast.parse(cli_src)
        failures.append("scanner.py/app.py is valid Python (AST)")  # We'll reverse this logic
    except SyntaxError as e:
        failures.append(f"Python file has syntax error: {e}")

    # Check: Runs on Python 3 (shebang or __main__ guard)
    if "if __name__" not in cli_src:
        failures.append("Python file missing __main__ guard")

# ════════════════════════════════════════════════════════════════
# CATEGORY 2: DECISION-CONTENT CHECKS
# Each check maps a grill decision to a specific element in the prototype.
# Replace these with YOUR decisions. Use the decision values as search targets.
# ════════════════════════════════════════════════════════════════

# Pattern: for each important decision, check that its VALUE appears in the prototype.
# Adapt to your prototype type:
#
# For HTML prototypes, search in `html`:
#   html_decision_checks = [
#       ("D51", "$2,847", "savings headline amount"),
#       ("D55", "99.2%", "quality maintained metric"),
#       ("D52", "8,200", "counterfactual baseline amount"),
#       ("D33", "80%", "soft cap threshold"),
#       ("D33", "100%", "hard cap threshold"),
#   ]
#   for d_id, needle, label in html_decision_checks:
#       if needle not in html:
#           failures.append(f"Decision {d_id}: {label} ('{needle}') not found in prototype")
#
# For CLI prototypes, search in `cli_src`:
#   cli_decision_checks = [
#       ("D10", "0.55", "name similarity weight"),
#       ("D10", "0.25", "icon similarity weight"),
#       ("D11", "80", "auto-flag threshold"),
#       ("D11", "55", "review threshold"),
#       ("D8", "apple", "Apple App Store adapter"),
#   ]
#   for d_id, needle, label in cli_decision_checks:
#       if needle not in cli_src:
#           failures.append(f"Decision {d_id}: {label} ('{needle}') not found in prototype")
#
# Also check interactive elements exist (for HTML):
#   interactive_checks = [
#       ("ROI calculator slider", lambda h: 'type="range"' in h and ('spend' in h or 'monthly' in h)),
#       ("Budget slider", lambda h: h.count('type="range"') >= 2),
#   ]
#   for label, check_fn in interactive_checks:
#       if not check_fn(html_lower):
#           failures.append(f"Interactive element missing: {label}")

# ════════════════════════════════════════════════════════════════
# CATEGORY 3: README CHECKS
# ════════════════════════════════════════════════════════════════

# Check: All 9 required sections present
required_sections = [
    "## What It Is", "## The Problem", "## Core Features",
    "## How to Review", "## Grill Decisions", "## Riskiest Assumption",
    "## How to Run", "## What Happens Next", "## Dossier"
]
for section in required_sections:
    if section not in readme:
        failures.append(f"README missing section: {section}")

# Check: How to Review has specific steps (not vague)
if readme:
    review_section = re.search(r'## How to Review(.*?)(##|\Z)', readme, re.S)
    if review_section:
        review_text = review_section.group(1).lower()
        # Check for actionable language (open/click/run/python3)
        action_words = ["open", "click", "run", "python3", "browser", "curl"]
        if not any(w in review_text for w in action_words):
            failures.append("How to Review lacks specific action steps (open/click/run)")
        # Check the prototype file is referenced
        proto_refs = ["index.html", "scanner.py", "app.py", "script.py"]
        if not any(ref in review_text for ref in proto_refs):
            failures.append("How to Review doesn't reference the prototype file")

# Check: Key decisions referenced in README (at least D1 and the highest D number)
if decisions and readme:
    first_d = "D1"
    max_num = 0
    for d_id in decisions:
        m = re.match(r'D(\d+)', d_id)
        if m:
            max_num = max(max_num, int(m.group(1)))
    last_d = f"D{max_num}"

    for d_id in [first_d, last_d]:
        if d_id not in readme:
            failures.append(f"Decision {d_id} not referenced in README")

# ════════════════════════════════════════════════════════════════
# CATEGORY 4: BUILD-RULE & ENVIRONMENT CHECKS
# ════════════════════════════════════════════════════════════════

# Check: Zero external dependencies (no CDN links for HTML)
if is_html:
    cdn_patterns = ['cdn.', 'unpkg.com', 'jsdelivr.com', 'fonts.googleapis.com']
    for pattern in cdn_patterns:
        if pattern in html_lower:
            failures.append(f"External CDN dependency found: {pattern}")

    # Check: No external src= attributes (all JS must be inline)
    external_srcs = re.findall(r'src="https?://', html)
    if external_srcs:
        failures.append(f"External script/style sources: {len(external_srcs)} found")

    # Check: Dark theme (common dark color patterns)
    dark_indicators = ['#1a1a', '#0d0d', '#111', '#1e1e', '#222', '#0f0f',
                       '#1a1a2e', '#0d1117', 'background-color: #1', 'dark']
    if not any(d in html_lower for d in dark_indicators):
        failures.append("No dark theme detected (check CSS background colors)")

# Check: Environment safety — verify the prototype doesn't import uninstalled packages
# Common problematic imports that crash at runtime:
if is_python_cli or is_python_api:
    # Extract imports from AST
    try:
        tree = ast.parse(cli_src)
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_names.add(node.module.split('.')[0])

        # Known problematic packages that are often NOT installed
        # (These should be guarded with try/except or avoided entirely)
        risky_imports = {
            'imagehash': 'NameError if uninstalled — use string-based hash comparison instead',
            'PIL': 'PIL may not be installed',
            'pillow': 'pillow may not be installed',
            'tensorflow': 'not installed — avoid',
            'torch': 'not installed — avoid',
            'transformers': 'not installed — avoid',
            'selenium': 'not installed — avoid',
            'playwright': 'not installed — avoid',
            'opencv': 'not installed — avoid',
            'cv2': 'not installed — avoid',
        }
        for name, reason in risky_imports.items():
            if name in imported_names:
                # Check if the import is guarded by try/except
                failures.append(f"Import '{name}' is UNAGUARDED — {reason}. Must be wrapped in try/except.")
    except SyntaxError:
        pass  # Already caught above

    # Check: Simulated data label in CLI output
    # (If the prototype outputs anything, it should clearly label simulated data)
    if "simulated" not in cli_src.lower() and "sample data" not in cli_src.lower():
        failures.append("No 'simulated/sample data' label found in source code")

# Simulated data label for HTML
if is_html:
    sim_indicators = ['simulated', 'sample data', 'demo data', 'representative']
    if not any(s in html_lower for s in sim_indicators):
        failures.append("No 'simulated/sample data' label found")

# Check: No .venv inside prototype/
if os.path.isdir(os.path.join(proto_dir, ".venv")):
    failures.append(".venv found inside prototype/ — should be at project root, not in prototype/")

# ════════════════════════════════════════════════════════════════
# CATEGORY 5: RUNTIME EXECUTION CHECKS (MANDATORY)
# ════════════════════════════════════════════════════════════════
#
# CRITICAL: Static analysis (AST parse, grep, regex) catches syntax errors
# but NOT runtime crashes. This category actually EXECUTES the prototype
# and checks it runs without error.
#
# Adapt the execute command to your prototype type.

# Determine what to execute
exec_path = None
exec_cmd = None
if is_html:
    # For HTML, check the file is valid HTML (no subprocess run needed)
    pass  # Structural checks above cover this
elif is_python_api:
    exec_path = app_path_guess
    exec_cmd = [sys.executable, app_path_guess]
elif is_python_cli:
    exec_path = script_path_guess
    # Use --help or a safe flag if --help is available; otherwise run with default
    # (Default run should work with simulated/demo data for prototypes)
    exec_cmd = [sys.executable, script_path_guess]

# Execute the prototype and check it runs without error
if exec_cmd:
    try:
        result = subprocess.run(
            exec_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=proto_dir,
        )
        if result.returncode != 0:
            failures.append(
                f"RUNTIME: prototype crashed (exit code {result.returncode}) — "
                f"stderr: {result.stderr[:300]}"
            )
        else:
            print(f"  [RUNTIME] Prototype runs clean: exit 0")

            # Check stdout for at least some output (not empty)
            combined = (result.stdout + result.stderr).strip()
            if len(combined) < 10:
                failures.append("RUNTIME: prototype produced almost no output")

            # Check no unhandled traceback in output
            if "Traceback" in combined:
                failures.append("RUNTIME: traceback found in output (unhandled exception at some point)")

            # Check no NameError or ImportError in output
            for err_type in ["NameError", "ImportError", "ModuleNotFoundError", "AttributeError"]:
                if err_type in combined:
                    failures.append(f"RUNTIME: {err_type} found in output — unhandled error")

    except subprocess.TimeoutExpired:
        failures.append("RUNTIME: prototype timed out (>30s)")
    except FileNotFoundError:
        failures.append(f"RUNTIME: executable not found at {exec_path}")
    except Exception as e:
        failures.append(f"RUNTIME: unexpected error running prototype: {e}")

# ════════════════════════════════════════════════════════════════
# REPORT
# ════════════════════════════════════════════════════════════════

total_checks = 5 + len(decisions) + 9 + 5 + 1  # Structural + Decision + README + Build + Runtime
    # (rough estimate — the actual counts depend on how many checks you add)

print(f"\n{'='*60}")
print(f"Decisions parsed: {len(decisions)}")
print(f"Total checks: {total_checks}")
print(f"Checks passed: {total_checks - len(failures)}/{total_checks}")
print(f"Failures: {len(failures)}")
for f in failures:
    print(f"  FAIL: {f}")
print(f"{'='*60}")

sys.exit(1 if failures else 0)
```

## How to use this template

1. Copy to `/tmp/verify-<slug>.py`
2. Replace `<slug>` everywhere
3. **Fill in CATEGORY 2** — map your specific decisions to prototype content checks. This is the most important part. Read each `Lock D` line from context/ and write a check that verifies that decision's value appears in the prototype.
4. **Adapt CATEGORY 5** — set the correct `exec_cmd` for your prototype type (CLI script, API server, etc.)
5. Count your checks. Aim for 40+ for complex prototypes.
6. Run it: `python3 /tmp/verify-<slug>.py`
7. Exit 0 = pass, Exit 1 = fail

## Check count guide

| Prototype complexity | Expected checks |
|---|---|
| Simple (single page, few features) | 20-30 |
| Medium (multi-tab, interactive elements) | 30-40 |
| Complex (dashboard, multiple data views, ROI calc) | 40-50+ |

## Common pitfalls

- **Static-only verification passes but prototype crashes at runtime.** This is the #1 failure mode. Always add Category 5 checks that subprocess-run the prototype.
- **Defaulting to HTML for everything.** If the product is a CLI tool, build a Python script, not a web page. HTML prototypes should have DOCTYPE + dark theme checks; CLI prototypes should have Python AST + runtime execution checks.
- **Using uninstalled packages.** Check imports in Category 4. `import imagehash` without try/except is the most common cause of runtime crashes in prototypes. Use string-based comparison instead of external hashing libraries.
- **Simulated data is not labeled.** The prototype must clearly state the data is simulated. Otherwise reviewers think they're seeing real data.
- **Forgetting to adapt the execution command in Category 5.** The default `exec_cmd` may not work for all prototype types (e.g., an API server needs different handling).
