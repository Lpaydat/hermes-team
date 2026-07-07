#!/usr/bin/env python3
"""Ad-hoc verification script template.

Copy this to /tmp/hermes-verify-<topic>.py, edit the REPO path, the module
name, and the check bodies, then run: python3 /tmp/hermes-verify-<topic>.py
Remove it afterwards: rm -f /tmp/hermes-verify-<topic>.py

Structure:
  1. Load the target module via importlib (no `import` side-effects).
  2. Assert the public surface.
  3. Exercise changed behavior with inputs that distinguish old vs new.
  4. Use tempfile for any filesystem touch.
  5. AST-walk for static constraints (never substring-search source).
  6. Print [PASS]/[FAIL] per check; exit non-zero on any failure.
"""

import os
import sys
import ast
import inspect
import tempfile
import importlib.util

# --- EDIT THESE ----------------------------------------------------------
REPO = "/absolute/path/to/repo"
MODULE_FILE = "module_under_test.py"   # filename inside REPO
MODULE_NAME = "mut"                    # what to call it in this script
ALLOWED_IMPORTS = {"re", "pathlib", "json", "os", "typing"}
# -------------------------------------------------------------------------

check_failed = 0


def check(name, cond):
    global check_failed
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}")
    if not cond:
        check_failed += 1


def load_module():
    spec = importlib.util.spec_from_file_location(
        MODULE_NAME, os.path.join(REPO, MODULE_FILE)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    m = load_module()

    # --- public surface ---
    check("has public function(s)", hasattr(m, "your_public_fn"))

    # --- behavior (edit: exercise the CHANGED paths specifically) ---
    check("empty input -> empty", m.your_public_fn("") == [])

    # --- filesystem behavior under tempfile ---
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "real.md"), "w").write("x")
        check("local exists -> True", m.your_public_fn("real.md", d) is True)

    # --- static constraints via AST (never substring search) ---
    src = inspect.getsource(m)
    tree = ast.parse(src)

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[0])
    check("stdlib-only imports", all(i in ALLOWED_IMPORTS for i in imports))

    has_forbidden_import = any(
        (isinstance(n, ast.Import) and any(a.name == "argparse" for a in n.names))
        or (isinstance(n, ast.ImportFrom) and n.module == "argparse")
        for n in ast.walk(tree)
    )
    check("no forbidden import", not has_forbidden_import)

    print()
    if check_failed:
        print(f"VERIFICATION FAILED: {check_failed} check(s) failed")
        sys.exit(1)
    print("VERIFICATION OK: all ad-hoc checks passed")


if __name__ == "__main__":
    main()
