#!/usr/bin/env python3
"""
Reusable adversarial break-it probe for a MARKUP / TEXT-TRANSFORM spec — any
tool that takes structured/inline-formatted input and emits HTML (or another
markup) as output. Examples: Markdown→HTML, RST→HTML, BBCode→HTML,
AsciiDoc→HTML, textile, wiki markup renderers.

Designed for specs where the SUT exposes a public convert(text)->str and/or a
CLI entry point. The SUT is imported via sys.path; it is never modified.

It exercises the failure modes most likely to survive both dev and verify
suites on a markup renderer — these are DISTINCT from codec round-trips
(library-breakit.py) and from CLI delimiter injection (cli-breakit.py):

  1.  XSS / HTML injection in input text (the #1 risk for any HTML emitter)
  2.  HTML injection in link URLs (attribute breakout, javascript: scheme)
  3.  HTML injection in link TEXT (img/onerror inside anchor)
  4.  Escape-ordering bug: format-then-escape reinterprets injected HTML
  5.  Double-escape in code blocks and link URLs
  6.  Inline formatting leaking INTO fenced code blocks (should be verbatim)
  7.  Inline code content reformatted (bold/italic applied inside `code`)
  8.  Unclosed / malformed delimiter handling (no crash, graceful fallback)
  9.  Nested formatting interaction (bold-in-italic, code-in-bold, code-in-link)
  10. CRLF line-ending leakage (\\r surviving into output paragraphs)
  11. Control characters (0x01-0x1F, 0x7F) must not crash
  12. Empty / whitespace-only input produces a valid (empty) document

Usage:
  1. Set SUT_PATH to the dir containing the SUT (md2html.py, etc.).
  2. Set SUT_MODULE and SUT_CONVERT to the public convert function name.
  3. Set MARKERS to the inline delimiters the spec defines.
  4. Set HAS_LINKS / HAS_CODE_BLOCKS / HAS_HEADINGS etc. to match the spec.
  5. Run: python3 markup-breakit.py   (exits 1 on any FAIL)

Notes:
  - This probe asserts on SAFETY INVARIANTS (no raw <script>, no unescaped
    href breakout) and STRUCTURAL INVARIANTS (code blocks verbatim, no crash),
    NOT on exact rendered HTML — exact output varies by spec convention
    (<strong> vs <b>, class= vs no class). Adapt the expected strings.
  - For exact-output assertions, add spec-specific checks after the generic
    probes.
"""
import importlib
import os
import sys

# --- CONFIG: adapt these for the board under audit ---------------------------
SUT_PATH = "/home/lpaydat/.hermes-teams/startup/kanban/boards/livetest-unbias-6/workspaces/t_1450d0ea"
SUT_MODULE = "md2html"
SUT_CONVERT = "convert"          # public function: text -> html-str
SUT_CLI = os.path.join(SUT_PATH, "md2html.py")  # CLI entry script (or None)

# Inline delimiters the spec defines (for malformed/nested probes):
MARKERS = {"bold": "**", "italic": "*", "code": "`"}

# Feature flags — set False if the spec doesn't define that element:
HAS_HEADINGS = True       # # / ## / ###
HAS_LINKS = True          # [text](url)
HAS_CODE_BLOCKS = True    # ``` ... ```
HAS_LISTS = True          # - / 1.
HAS_BLOCKQUOTES = True    # > quote
HAS_HR = True             # ---
# -----------------------------------------------------------------------------


sys.path.insert(0, SUT_PATH)
mod = importlib.import_module(SUT_MODULE)
convert = getattr(mod, SUT_CONVERT)

results = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((name, status))
    tag = f"  [{status}] {name}"
    if detail and status == "FAIL":
        tag += f"  ::  {detail}"
    print(tag)


def _doc_ok(out):
    """Every convert() output must be a non-crashing string with a doctype-ish
    wrapper. Adapt if the spec defines a different skeleton."""
    return isinstance(out, str) and ("<html" in out.lower() or "<body" in out.lower())


# === 1. XSS / HTML injection in input text ===================================
def probe_xss_in_text():
    """Raw <script> in input must NOT survive as a live tag in output."""
    out = convert("<script>alert(1)</script>")
    check("no live <script> tag in output", "<script>" not in out,
          f"output contains raw <script>: {out[out.find('<script')-5:out.find('<script')+20]!r}")
    check("script tag escaped or stripped", "script" in out.lower(),
          "script entirely absent — may be over-stripped")


def probe_html_entity_injection():
    """<img onerror=...> in input must not become a live tag."""
    out = convert('text <img src=x onerror=alert(1)> more')
    check("no live <img> tag in output", "<img" not in out, f"raw img tag survived: {out!r}")


# === 2-3. HTML injection in link URLs and link text ==========================
def probe_xss_in_link_url():
    if not HAS_LINKS:
        results.append(("link XSS (N/A)", "SKIP")); return
    # javascript: URL — the converter should at minimum not crash; whether it
    # strips the scheme is spec-dependent. We assert no crash + valid HTML.
    out = convert("[click](javascript:alert(1))")
    check("javascript: URL no crash", _doc_ok(out))
    # Attribute breakout: a quote in the URL must not escape the href attribute
    out = convert('[t](a"onmouseover="alert(1))')
    # The dangerous pattern is: href="a"onmouseover="..." — a raw quote
    # immediately closing the attribute value. Check no unescaped quote inside.
    if '<a ' in out:
        anchor = out[out.find("<a"):out.find("</a>") + 4]
        # After the href=" there should be no raw " until the closing "
        check("no attribute breakout via quote in URL",
              "&quot;" in anchor or anchor.count('"') % 2 == 0,
              f"odd quote count in anchor: {anchor!r}")


def probe_xss_in_link_text():
    if not HAS_LINKS:
        results.append(("link-text XSS (N/A)", "SKIP")); return
    out = convert("[<img src=x onerror=alert(1)>](url)")
    check("no live <img> in link text", "<img" not in out)
    out2 = convert("[<b>bold link</b>](url)")
    check("raw <b> in link text escaped", "<b>bold" not in out2 or "&lt;b&gt;" in out2,
          "raw <b> survived into link text — HTML not escaped before link rendering")


# === 4. Escape-ordering: format-then-escape reinterprets injected HTML =======
def probe_escape_before_format():
    """The critical invariant: escaping MUST happen BEFORE inline formatting.
    If formatting runs first, '**<script>**' could produce '<strong><script>'
    before escaping — but then escaping would neutralize the <script>. The
    REAL danger is when escaping runs AFTER formatting and re-escapes the
    generated tags (<strong> -> &lt;strong&gt;), breaking output. Check that
    generated tags survive intact."""
    out = convert("**bold**")
    check("generated <strong> not re-escaped", "<strong>" in out and "&lt;strong&gt;" not in out,
          "formatting output was escaped — escape ran AFTER format (broken order)")
    out = convert("*italic*")
    check("generated <em> not re-escaped", "<em>" in out and "&lt;em&gt;" not in out)


# === 5. Double-escape in code blocks and URLs ================================
def probe_double_escape_code_block():
    if not HAS_CODE_BLOCKS:
        results.append(("code double-escape (N/A)", "SKIP")); return
    out = convert("```\na & b\n```")
    check("no double-escape of & in code block", "&amp;amp;" not in out,
          "code block content double-escaped")
    check("single-escape of & in code block", "&amp;" in out or "a & b" in out)


def probe_double_escape_url():
    if not HAS_LINKS:
        results.append(("URL double-escape (N/A)", "SKIP")); return
    out = convert("[t](a&b)")
    check("no double-escape of & in URL", "&amp;amp;" not in out,
          "URL ampersand double-escaped")
    # The URL should be attribute-safe: & -> &amp; (single), " -> &quot;
    out2 = convert('[t](a"b)')
    check("quote in URL escaped for attribute", "&quot;" in out2 or "&#x27;" in out2 or '\\"' in out2,
          "raw quote in URL — attribute-unsafe")


# === 6. Inline formatting must NOT apply inside fenced code blocks ============
def probe_inline_not_in_code_block():
    if not HAS_CODE_BLOCKS:
        results.append(("inline-in-codeblock (N/A)", "SKIP")); return
    out = convert("```\n**bold** *italic* `code`\n```")
    check("no <strong> inside code block", "<strong>" not in out,
          "bold applied inside fenced code block — should be verbatim")
    check("no <em> inside code block", "<em>" not in out,
          "italic applied inside fenced code block")
    check("raw markers survive in code block", "**bold**" in out,
          "raw ** lost from code block content")


# === 7. Inline code content must not be reformatted ==========================
def probe_inline_code_not_reformatted():
    out = convert("`**notbold**`")
    check("no <strong> inside inline code", "<strong>" not in out,
          "bold applied to inline code content — should be literal")
    check("raw ** survives inside inline code", "**notbold**" in out,
          "inline code content lost its ** markers")


# === 8. Unclosed / malformed delimiters ======================================
def probe_unclosed_delimiters():
    """Unclosed bold/italic/code/link must not crash and must not produce
    unclosed HTML tags that break document structure."""
    for label, inp in [
        ("unclosed bold", "**unclosed"),
        ("unclosed italic", "*unclosed"),
        ("unclosed code", "unclosed `code"),
        ("unclosed link", "[text](url"),
        ("unclosed link text", "[text only"),
    ]:
        out = convert(inp)
        check(f"{label}: no crash", _doc_ok(out), f"output: {out[:100]!r}")
    # Empty delimiters
    for label, inp in [
        ("empty bold", "a **** b"),
        ("empty code", "a `` b"),
        ("empty link", "[](url)"),
    ]:
        out = convert(inp)
        check(f"{label}: no crash", _doc_ok(out))


# === 9. Nested formatting interaction ========================================
def probe_nested_formatting():
    # Code inside bold — code should not be reformatted, bold should wrap
    out = convert("**a `b` c**")
    check("code inside bold: both render", "<strong>" in out.replace("&lt;strong&gt;","X") and "`b`" not in out or "<code>" in out)
    # Bold inside italic or vice versa
    out = convert("***both***")
    check("triple-asterisk no crash", _doc_ok(out))
    if HAS_LINKS:
        # Code inside link text (common recursion bug — code span lost)
        out = convert("[a `b` c](url)")
        check("code span survives inside link text", "<code>" in out and out.count("<a ") >= 1,
              "inline code lost when inside link text — _render_inline recursion bug")


# === 10. CRLF line-ending leakage ============================================
def probe_crlf():
    """If the converter splits only on \\n, \\r leaks into output text."""
    out = convert("# Title\r\n\r\nParagraph\r\n")
    # \r should not appear literally inside <p> or <h> content
    # (It may appear if the spec explicitly preserves it, but it's a yellow flag.)
    has_leaked_cr = "\r" in out and "<p>" in out
    check("no \\r leaked into paragraph text", not has_leaked_cr,
          "\\r survived into output — CRLF not normalized (spec may allow; note as edge)")


# === 11. Control characters must not crash ===================================
def probe_control_chars():
    for c in list(range(0x01, 0x20)) + [0x7F]:
        out = convert("a" + chr(c) + "b")
        if not _doc_ok(out):
            check(f"control char 0x{c:02x}: no crash", False,
                  f"crashed on 0x{c:02x}")
            return
    check("all control chars 0x01-0x1F + 0x7F: no crash", True)
    # Null byte specifically
    out = convert("hello\x00world")
    check("null byte: no crash", _doc_ok(out))


# === 12. Empty / whitespace input ============================================
def probe_empty_input():
    out = convert("")
    check("empty input: valid doc", _doc_ok(out), f"got: {out!r}")
    out = convert("   \n   \n   ")
    check("whitespace-only: valid doc", _doc_ok(out))
    out = convert("\n")
    check("single newline: valid doc", _doc_ok(out))


if __name__ == "__main__":
    probes = [
        probe_xss_in_text,
        probe_html_entity_injection,
        probe_xss_in_link_url,
        probe_xss_in_link_text,
        probe_escape_before_format,
        probe_double_escape_code_block,
        probe_double_escape_url,
        probe_inline_not_in_code_block,
        probe_inline_code_not_reformatted,
        probe_unclosed_delimiters,
        probe_nested_formatting,
        probe_crlf,
        probe_control_chars,
        probe_empty_input,
    ]
    for p in probes:
        print(f"\n=== {p.__name__} ===")
        try:
            p()
        except Exception as e:
            results.append((p.__name__, "CRASH"))
            print(f"  [CRASH] {p.__name__}: {type(e).__name__}: {e}")

    fails = [n for n, s in results if s == "FAIL"]
    crashes = [n for n, s in results if s == "CRASH"]
    skips = [n for n, s in results if s == "SKIP"]
    passed = sum(1 for _, s in results if s == "PASS")
    total = len(results)
    print(f"\n{passed}/{total} passed" +
          (f", {len(fails)} FAIL" if fails else "") +
          (f", {len(crashes)} CRASH" if crashes else "") +
          (f", {len(skips)} SKIP" if skips else ""))
    if fails:
        print("FAILURES: " + ", ".join(fails))
    if crashes:
        print("CRASHES: " + ", ".join(crashes))
    sys.exit(1 if (fails or crashes) else 0)
