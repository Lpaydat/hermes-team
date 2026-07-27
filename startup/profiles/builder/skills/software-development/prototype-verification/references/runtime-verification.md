# Runtime Verification Recipes

Concrete, copy-adaptable recipes for Layer 2 (runtime) verification. These
supplement the static verify-script with checks that only running the tool can
provide. Each recipe produces an assertion, not an impression.

## Recipe: assert exit-code contract

A CI-ready tool that promises "exit 1 on HIGH findings" must actually exit 1.
Capture and assert `$?` explicitly.

```bash
python3 scan.py <sample-repo> --verbose; ec=$?
echo "EXIT_CODE=$ec"
# For a HIGH-finding sample repo, assert ec == 1.
# ec == 0 → broken gate (findings not flagged). ec == 2 → scanner crash.
test "$ec" -eq 1 && echo "PASS: exit contract" || echo "FAIL: expected 1, got $ec"
```

## Recipe: validate --json schema programmatically

Never eyeball JSON. Pipe through `json.load()` and assert the shape.

```bash
python3 scan.py <repo> --json > /tmp/out.json 2>/tmp/err.log; echo "exit=$?"
python3 - <<'PY'
import json
from collections import Counter
d = json.load(open('/tmp/out.json'))
assert 'findings' in d and isinstance(d['findings'], list), "no findings array"
print("top-level keys:", list(d.keys()))
print("findings count:", len(d['findings']))
print("severity breakdown:", Counter(f.get('severity') for f in d['findings']))
# Add schema-specific asserts, e.g. every finding has rule_id + file + severity
for f in d['findings']:
    assert all(k in f for k in ('rule_id','severity','file')), f"malformed finding: {f}"
print("PASS: schema valid")
PY
```

## Recipe: confirm every promised capability fires

List the capabilities the design decisions promise, then grep the real output
for each rule ID or message. Anything absent is a miss.

```bash
OUT=$(python3 scan.py <repo> --verbose 2>&1)
for rule in INJ-ZERO-WIDTH INJ-BIDI INJ-HTML-COMMENT EXEC-PIPE-SHELL \
            EXEC-REVERSE-SHELL EXFIL-ENV EXFIL-SSH EXEC-DESTRUCTIVE AUTO-PR-TARGET; do
  if echo "$OUT" | grep -q "$rule"; then
    echo "DETECTED: $rule"
  else
    echo "MISSED:   $rule"
  fi
done
```

## Recipe: flag-coupling probe (silent no-op detection)

For each documented flag, run it ALONE and confirm it produces its promised
artifact. A flag that silently no-ops is the most common single-file-tool bug.

```bash
# Does --save-manifest alone actually write a file?
rm -f /tmp/m.json
python3 scan.py <repo> --save-manifest /tmp/m.json --json >/dev/null 2>&1
test -f /tmp/m.json && echo "PASS: manifest written" || echo "FAIL: no manifest file"

# If it failed, try coupling it with its sibling flag to confirm the bug:
python3 scan.py <repo> --drift /tmp/nonexistent.json --save-manifest /tmp/m2.json --json >/dev/null 2>&1
test -f /tmp/m2.json && echo "coupled run worked → flag is silently gated on sibling" \
                        || echo "still broken → different root cause"
```

## Recipe: drift / provenance round-trip

Full drift verification in a sandbox (so the fixture stays pristine):

```bash
cp -r ~/projects/<slug>/prototype/sample-repo /tmp/pf_sandbox
python3 scan.py /tmp/pf_sandbox --save-manifest /tmp/base.json --json >/dev/null 2>&1

# 1) clean run against baseline → expect zero DRIFT-CHANGED
python3 scan.py /tmp/pf_sandbox --drift /tmp/base.json --json \
  | python3 -c "import json,sys;d=json.load(sys.stdin);\
     x=[f for f in d['findings'] if f.get('rule_id')=='DRIFT-CHANGED'];\
     print('clean drift-changed (want 0):',len(x))"

# 2) mutate, re-run → expect >=1 DRIFT-CHANGED
printf '\n# mutation\n' >> /tmp/pf_sandbox/README.md
python3 scan.py /tmp/pf_sandbox --drift /tmp/base.json --json \
  | python3 -c "import json,sys;d=json.load(sys.stdin);\
     x=[f for f in d['findings'] if f.get('rule_id')=='DRIFT-CHANGED'];\
     print('post-mutation drift-changed (want >0):',len(x))"
```

## Recipe: AST / structured-file probe

If the tool parses structured files (JSON configs, package.json scripts,
workflow YAML), confirm it reads the nested field, not just the file. Plant a
payload only in a nested key and confirm detection.

```bash
# e.g. detection should fire on .mcp.json .mcpServers.X.args even though the
# top-level file is valid JSON. If detection only fires on top-level text scans,
# nested-key obfuscation is a gap.
```

## Recipe: optional-import guard check (unguarded usage detection)

Many prototypes wrap optional dependencies in a try/except import block:

```python
try:
    from PIL import Image
    import imagehash
    HAS_ICON_LIBS = True
except ImportError:
    HAS_ICON_LIBS = False
```

But then use the optional module WITHOUT checking the guard flag:

```python
def compute_icon_similarity(brand_hash, candidate_hash):
    # BUG: no check for HAS_ICON_LIBS — crashes if imagehash not installed
    h1 = imagehash.hex_to_hash(brand_hash)
    ...
```

When the optional package isn't installed in the environment, this throws
`NameError` (not `ImportError`) at runtime — which static analysis cannot catch.
The prototype passes AST parse and all grep checks but crashes on execution.

To detect this pattern:

```bash
# 1. Run the prototype with no arguments (happy path)
python3 prototype/scanner.py 2>&1 | head -5; echo "exit=$?"

# 2. If it crashes with NameError or ImportError on a line INSIDE a function
#    (not at module level), check whether that function guards on the HAS_* flag.
#    The crash traceback will name the function and line.

# 3. Quick grep for the anti-pattern: module used in functions but not guarded
python3 -c "
import re
with open('prototype/scanner.py') as f: src = f.read()
# Find try/except import blocks and their guard variables
guards = re.findall(r'(\w+)\s*=\s*(?:True|False)', src)
imports = re.findall(r'import\s+(\w+)', src)
# Check if any imported module name appears in a function body without the guard
funcs = re.findall(r'def\s+\w+\([^)]*\):(.*?)(?=\ndef |\Z)', src, re.DOTALL)
for func in funcs:
    for imp in imports:
        if imp in func and imp not in str(guards):
            print(f'WARNING: module \"{imp}\" used in function body — check guard')
"
```

This recipe is critical because verify scripts that only do static analysis
(AST parse + regex grep) will report 47/47 PASS for a prototype that crashes
on launch. The runtime execution check (just running `python3 script.py`)
is the only reliable way to catch unguarded optional-import usage.

## Interpreting mixed results

- All recipes pass → **PASS**.
- Any recipe fails → **PARTIAL PASS** (core works, specific defect) or **FAIL**
  (core broken). Always list the failing recipe's command and output verbatim in
  the report so the builder can reproduce.
- If the prototype crashes on basic execution (happy path), that's a **FAIL**
  regardless of how many static checks pass. A prototype that can't run is
  not a prototype — it's a text file.
