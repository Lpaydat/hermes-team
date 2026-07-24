# Verification Script Template

Write this to `/tmp/verify-<slug>.py` before calling loop_engine. It parses locked decisions from context/ and checks the prototype + README against them.

**Minimum requirement: 20 checks.** If your script has fewer, it is not thorough enough. The RouteOpt prototype used 48 checks. Aim for that level of coverage.

The script must check FOUR categories:
1. **Structural checks** (prototype exists, HTML is well-formed, tabs/sections present)
2. **Decision-content checks** (specific decisions from context/ are reflected in the prototype)
3. **README checks** (all 9 sections, decision IDs referenced, specific How-to-Review steps)
4. **Build-rule checks** (zero dependencies, dark theme, simulated data label)

```python
#!/usr/bin/env python3
"""Verify <slug> prototype against grill decisions in context/."""
import re, os, sys

SLUG = "<slug>"
context_dir = os.path.expanduser(f"~/projects/{SLUG}/context")
proto_dir = os.path.expanduser(f"~/projects/{SLUG}/prototype")
readme_path = os.path.expanduser(f"~/projects/{SLUG}/README.md")
html_path = os.path.join(proto_dir, "index.html")

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

# ── Load files ──
html = ""
html_lower = ""
if os.path.exists(html_path):
    html = open(html_path).read()
    html_lower = html.lower()
else:
    failures.append("index.html not found in prototype/")

readme = ""
readme_lower = ""
if os.path.exists(readme_path):
    readme = open(readme_path).read()
    readme_lower = readme.lower()
else:
    failures.append("README.md does not exist")

# ════════════════════════════════════════════════════════════════
# CATEGORY 1: STRUCTURAL CHECKS (prototype exists, well-formed)
# ════════════════════════════════════════════════════════════════

# Check: Prototype directory has files
if not os.path.isdir(proto_dir) or not os.listdir(proto_dir):
    failures.append("No prototype files in prototype/")

# Check: HTML has DOCTYPE
if html and not html.lstrip().startswith("<!DOCTYPE"):
    failures.append("HTML missing DOCTYPE declaration")

# Check: HTML has <html> and </html> tags
if html and ("<html" not in html_lower or "</html>" not in html_lower):
    failures.append("HTML missing <html>/</html> tags")

# Check: JS braces balanced (no syntax errors in script blocks)
if html:
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.S)
    for i, s in enumerate(scripts):
        if s.count('{') != s.count('}'):
            failures.append(f"Script block {i}: unbalanced braces ({s.count('{')} open vs {s.count('}')} close)")

# Check: Tab/section mechanism exists (adapt to your prototype's pattern)
# Common patterns: data-tab, onclick=showTab, class="tab", data-section
tab_patterns = [
    (r'data-tab=', 'data-tab attributes'),
    (r'onclick=["\']\s*showtab', 'onclick showTab'),
    (r'class=["\']tab', 'class=tab elements'),
    (r'data-section=', 'data-section attributes'),
]
# At least ONE tab mechanism should exist for multi-tab prototypes
# (Remove this check if your prototype is single-page with no tabs)

# ════════════════════════════════════════════════════════════════
# CATEGORY 2: DECISION-CONTENT CHECKS
# Each check maps a grill decision to a specific element in the prototype.
# Replace these with YOUR decisions. Use the decision values as search targets.
# ════════════════════════════════════════════════════════════════

# Pattern: for each important decision, check that its VALUE appears in the HTML.
# Example (adapt to your decisions):
#
# html_decision_checks = [
#     ("D51", "$2,847", "savings headline amount"),
#     ("D55", "99.2%", "quality maintained metric"),
#     ("D52", "8,200", "counterfactual baseline amount"),
#     ("D33", "80%", "soft cap threshold"),
#     ("D33", "100%", "hard cap threshold"),
#     ("D54", "$0.00", "no-route row proving quality floor"),
# ]
# for d_id, needle, label in html_decision_checks:
#     if needle not in html:
#         failures.append(f"Decision {d_id}: {label} ('{needle}') not found in prototype")

# Also check interactive elements exist:
# interactive_checks = [
#     ("ROI calculator slider", lambda h: 'type="range"' in h and ('spend' in h or 'monthly' in h)),
#     ("Budget slider", lambda h: h.count('type="range"') >= 2),
#     ("Traffic light system", lambda h: "green" in h and "amber" in h and "red" in h),
# ]
# for label, check_fn in interactive_checks:
#     if not check_fn(html_lower):
#         failures.append(f"Interactive element missing: {label}")

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

# Check: How to Review has specific click/open steps (not vague)
if readme:
    review_section = re.search(r'## How to Review(.*?)(##|\Z)', readme, re.S)
    if review_section:
        review_text = review_section.group(1).lower()
        if not ("open" in review_text or "click" in review_text):
            failures.append("How to Review lacks specific steps (open/click)")
        if "index.html" not in review_text and "app.py" not in review_text:
            failures.append("How to Review doesn't reference index.html or app.py")

# Check: Key decisions referenced in README (at least D1 and the highest D number)
if decisions and readme:
    first_d = f"D1"
    # Find highest decision number
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
# CATEGORY 4: BUILD-RULE CHECKS
# ════════════════════════════════════════════════════════════════

# Check: Zero external dependencies (no CDN links, no external script src)
if html:
    cdn_patterns = ['cdn.', 'unpkg.com', 'jsdelivr.com', 'fonts.googleapis.com']
    for pattern in cdn_patterns:
        if pattern in html_lower:
            failures.append(f"External dependency found: {pattern}")

    # Check: No external src= attributes (all JS must be inline)
    external_srcs = re.findall(r'src="https?://', html)
    if external_srcs:
        failures.append(f"External script/style sources: {len(external_srcs)} found")

# Check: Dark theme (common dark color patterns)
if html:
    dark_indicators = ['#1a1a', '#0d0d', '#111', '#1e1e', '#222', '#0f0f',
                       '#1a1a2e', '#0d1117', 'background-color: #1', 'dark']
    if not any(d in html_lower for d in dark_indicators):
        failures.append("No dark theme detected (check CSS background colors)")

# Check: Simulated data label (prototype must label its data as simulated)
if html:
    sim_indicators = ['simulated', 'sample data', 'demo data', 'representative']
    if not any(s in html_lower for s in sim_indicators):
        failures.append("No 'simulated/sample data' label found")

# ════════════════════════════════════════════════════════════════
# REPORT
# ════════════════════════════════════════════════════════════════

print(f"\n{'='*60}")
print(f"Decisions checked: {len(decisions)}")
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
3. **Fill in CATEGORY 2** — map your specific decisions to HTML content checks. This is the most important part. Read each `Lock D` line from context/ and write a check that verifies that decision's value appears in the prototype.
4. Count your checks. The 4 categories above give you ~15 structural/README/build checks automatically. You need at least 5 decision-content checks to hit 20 minimum. Aim for more.
5. Run it: `python3 /tmp/verify-<slug>.py`
6. Exit 0 = pass, Exit 1 = fail

## Check count guide

| Prototype complexity | Expected checks |
|---|---|
| Simple (single page, few features) | 20-30 |
| Medium (multi-tab, interactive elements) | 30-40 |
| Complex (dashboard, multiple data views, ROI calc) | 40-50+ |
