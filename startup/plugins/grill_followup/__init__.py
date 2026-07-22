"""grill_followup — carry a venture grill forward across PO sessions.

When PO completes a venture-grill card AND grilled VB (intercom ask/send to
venture-builder) during that session, spawn the next grill card — same venture,
NO parent link, ready — with the venture's OPEN questions (parsed from
CONTEXT.md) injected into the body. PO sees concrete work (the open questions),
not a "duplicate" to close. When no open questions remain, PO finds nothing to
grill, completes without intercom, and the loop ends naturally.

Self-terminating (no intercom → no next card). Idempotent (idempotency_key by
slug). Fail-safe (never breaks the worker).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from typing import Optional

logger = logging.getLogger(__name__)

# Repo root derived from this plugin's real location (it lives at
# <repo>/startup/plugins/grill_followup). CONTEXT.md is at <repo>/docs/ventures,
# but the worker's HERMES_HOME is PROFILE-scoped (<repo>/startup/profiles/<p>),
# NOT the team home <repo>/startup — so HERMES_HOME/.. misses docs/ventures and
# the open-questions injection silently fails. The plugin path is stable, so this
# resolves CONTEXT.md regardless of HERMES_HOME/cwd.
_PLUGIN_FILE = os.path.realpath(__file__)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_PLUGIN_FILE))))

# Per-worker-process flag: did THIS grill session intercom VB? One grill card =
# one worker process, so this is session-scoped without explicit tracking.
_session_grilled_vb = False


# --- pure decisions (unit-tested) ---------------------------------------

def _extract_call(kw) -> tuple[str, object]:
    """Pull (function_name, function_args) from a post_tool_call payload.

    The emitter passes ``tool_name=`` and ``args=``; some callers pass
    ``function_name=``/``function_args=``. Read both.
    """
    function_name = kw.get("function_name") or kw.get("tool_name") or ""
    function_args = kw.get("function_args")
    if function_args is None:
        function_args = kw.get("args")
    return function_name, function_args


def is_grill_intercom(function_name: str, function_args) -> bool:
    """True iff this tool call is PO grilling VB — intercom ask/send to
    venture-builder (bare or cross-team ``team-x/venture-builder``)."""
    if function_name != "intercom":
        return False
    args = function_args
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = {}
    if not isinstance(args, dict):
        args = {}
    if args.get("action") not in ("ask", "send"):
        return False
    return "venture-builder" in str(args.get("to") or "")


def _extract_slug(body) -> str:
    m = re.search(r"venture-pitch/(\S+)", body or "")
    return (m.group(1) if m else "").strip()


def _venture_name_from_title(title: str) -> str:
    """'[grill] ScriptSync' -> 'scriptsync' (PO names the venture dir this way)."""
    name = re.sub(r"^\s*\[grill\]\s*", "", str(title or ""), flags=re.IGNORECASE)
    name = re.sub(r"\s*\(next\)\s*$", "", name, flags=re.IGNORECASE)
    return name.strip().lower()


def find_context_md(task_title: str, task_body) -> Optional[str]:
    """Locate the venture's CONTEXT.md. PO names the dir after the venture
    (docs/ventures/scriptsync/); fall back to the slug. Search cwd, HERMES_HOME,
    and the repo root (HERMES_HOME/..) so it resolves regardless of where the
    worker wrote it."""
    venture = _venture_name_from_title(task_title)
    slug = _extract_slug(task_body)
    home = os.environ.get("HERMES_HOME", "")
    # os.getcwd() raises OSError if the worker's cwd was deleted/unlinked (it
    # can happen mid-session) — guard it or the whole hook crashes + no next card.
    try:
        cwd = os.getcwd()
    except OSError:
        cwd = ""
    # PO writes CONTEXT.md inconsistently to THREE locations depending on which
    # convention it follows that session:
    #   1. <repo>/docs/ventures/<name>/        (grill skill's "docs/ventures/")
    #   2. <repo>/startup/docs/ventures/<name>/ (relative from HERMES_HOME=startup)
    #   3. ~/vault/<name>/             (venture-pipeline vault convention)
    # Search all three + the worker's cwd + HERMES_HOME.
    names = [n for n in (venture, slug) if n]
    # Canonical home (absolute-path fix): venture-grill writes CONTEXT.md to
    # ~/.venture-builder/<slug>/CONTEXT.md — absolute, so it survives the
    # scratch-workspace rmtree that destroyed ~10% of grill outputs. Searched
    # first (new canonical); the repo/vault roots below remain as fallbacks for
    # priors written before the fix.
    vb_home = os.path.expanduser("~/.venture-builder")
    for name in names:
        p = os.path.join(vb_home, name, "CONTEXT.md")
        if os.path.isfile(p):
            return p
    bases = []
    if _REPO_ROOT:
        bases.append(_REPO_ROOT)
        bases.append(os.path.join(_REPO_ROOT, "startup"))
    if cwd:
        bases.append(cwd)
    if home:
        bases.append(home)
        parent = os.path.dirname(home)
        if parent:
            bases.append(parent)
    vault = os.path.expanduser("~/vault")
    for base in bases:
        for name in names:
            p = os.path.join(base, "docs", "ventures", name, "CONTEXT.md")
            if os.path.isfile(p):
                return p
    # vault convention (~/vault/<name>/ — no "docs/" prefix)
    for name in names:
        p = os.path.join(vault, "ventures", name, "CONTEXT.md")
        if os.path.isfile(p):
            return p
    return None


# --- CONTEXT.md canonicalization (tool-level rescue) --------------------
# PO follows matt's grill-with-docs convention for WHERE to write CONTEXT.md,
# which a skill prompt cannot reliably override (directive #3). The convention
# may land the file in the worker's ephemeral scratch workspace, which is
# shutil.rmtree'd on kanban_complete (the ~10% loss). This post_tool_call hook
# fires AT WRITE TIME — before cleanup — so we copy every write_file/patch of a
# *CONTEXT.md to the canonical ~/.venture-builder/<slug>/ home. find_context_md
# (above) searches that root first, so the iteration loop + collection resolve
# to the surviving canonical copy regardless of where PO originally wrote.
_WRITE_TOOLS = frozenset({"write_file", "patch"})


def _canonical_target(slug: str) -> str:
    """expanduser at call time so tests can monkeypatch HOME."""
    return os.path.join(os.path.expanduser("~/.venture-builder"), slug, "CONTEXT.md")


def maybe_canonicalize_context_md(function_name, function_args, task_body) -> Optional[str]:
    """If this is a write_file/patch of a *CONTEXT.md, mirror it to the canonical
    ~/.venture-builder/<slug>/CONTEXT.md so it survives the scratch rmtree.
    Returns the target path on copy, else None. Fail-safe (never breaks worker)."""
    if function_name not in _WRITE_TOOLS:
        return None
    args = function_args
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            return None
    if not isinstance(args, dict):
        return None
    path = args.get("path")
    if not isinstance(path, str) or not path.rstrip("/").endswith("CONTEXT.md"):
        return None
    if not os.path.isfile(path):
        return None
    slug = _extract_slug(task_body)
    if not slug:
        return None
    target = _canonical_target(slug)
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(path, target)
        return target
    except Exception as exc:
        logger.warning("grill_followup: canonicalize CONTEXT.md failed: %s", exc)
        return None


_OPEN_HEADING_RE = re.compile(
    r"^##.*(?:"
    r"\bopen|hypoth|gate|kill|assumption|tbd|todo|"
    r"to[\s-]*be[\s-]*test|to[\s-]*test|to[\s-]*verif|"
    r"unverif|unresolved|next\s+step|follow[\s-]*up|parked|defer|risk"
    r")",
    re.IGNORECASE,
)


def extract_open_questions(context_path: Optional[str]) -> str:
    """Extract unresolved items from CONTEXT.md so the grill loop can carry
    them into the next iteration.

    PO records open items under semantically-rich headers per grill-with-docs'
    convention — NOT always a literal "Open questions" section. grilllive42
    terminated at 2 iter with 2 unmeasured hypotheses + 4 unpassed gates on
    disk, because the old parser only matched ``## Open`` and thus injected
    nothing. This recognizes any open-bearing section (hypotheses, gates,
    assumptions, TBD, risks, to-test, unresolved, next-steps, parked, deferred,
    follow-up) + the ``**Open ...`` bold form, and collects ALL such sections
    (not just the first).

    Heading-form sections run to the next ``## ``; a new ``##`` that is itself an
    open section continues the collection. Bold-form runs to a blank line or new
    heading/bold opener. Returns the concatenated block, stripped; '' if none.
    """
    if not context_path:
        return ""
    try:
        with open(context_path, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return ""
    section: list[str] = []
    in_section = False
    bold = False
    for line in lines:
        if not in_section:
            if _OPEN_HEADING_RE.match(line):
                in_section, bold = True, False
                section.append(line)
            elif re.match(r"^\*\*Open", line, re.IGNORECASE):
                in_section, bold = True, True
                section.append(line)
        else:
            if re.match(r"^##\s", line):
                # heading form ends here; if the new ## is itself open, keep collecting
                in_section = False
                if _OPEN_HEADING_RE.match(line):
                    in_section, bold = True, False
                    section.append(line)
            elif bold and (line.strip() == "" or re.match(r"^\*\*", line)):
                in_section = False
            else:
                section.append(line)
    while section and not section[-1].strip():
        section.pop()
    return "".join(section).strip()


_SCAN_TIMEOUT = 150  # seconds — scanner reads CONTEXT.md + reasons (~40s typical)


def parse_scan_output(raw: str) -> tuple[str, Optional[str]]:
    """Parse the scanner's output. Returns (status, question):
    - 'next'      -> question is the next grill focus (carry it forward)
    - 'converged' -> scanner declared the grill done (terminate the loop)
    - 'unclear'   -> malformed/empty -> caller falls back to mechanical extract

    The scan prompt's own format-spec lines ('NEXT: <single most...>') echo
    into stdout BEFORE the real answer. Skip placeholder lines (containing '<')
    and take the LAST NEXT:/CONVERGED: match (the scanner's final answer)."""
    if not raw:
        return ("unclear", None)
    last_next: Optional[str] = None
    last_converged = False
    for line in raw.splitlines():
        s = line.strip()
        if "<" in s:  # echoed prompt placeholder, not a real answer
            continue
        m = re.match(r"^NEXT:\s*(.+)$", s, re.IGNORECASE)
        if m:
            last_next = m.group(1).strip()
            continue
        if re.match(r"^CONVERGED:", s, re.IGNORECASE):
            last_converged = True
    if last_next:
        return ("next", last_next)
    if last_converged:
        return ("converged", None)
    return ("unclear", None)


def scan_for_next_question(slug: str) -> str:
    """Spawn a read-only grill-skill scanner (hermes chat, toolset=file so it
    cannot grill VB) over the venture's CONTEXT.md. Returns raw stdout (the
    NEXT:/CONVERGED: line lives somewhere in it). Fail-safe: '' on any error or
    timeout (caller falls back to the mechanical extract). Separation of
    incentives: PO-the-griller converges; this scanner's only job is to FIND the
    next gap, so it diverges where PO would stop."""
    import subprocess
    ctx_path = os.path.join(os.path.expanduser("~/.venture-builder"), slug, "CONTEXT.md")
    prompt = (
        "GRILL SCANNER (read-only — do NOT use intercom, do NOT grill anyone, "
        "do NOT write files).\n\n"
        f"Read: {ctx_path}\n\n"
        "This venture was just grilled for another iteration. Your ONLY job: "
        "decide whether the grill is GENUINELY done or whether there is a next "
        "unanswered question.\n\n"
        "Be RELENTLESS — default to finding a gap. Output CONVERGED only if "
        "EVERY load-bearing claim in CONTEXT.md is backed by actual evidence "
        "(not assertion, hypothesis, TBD, to-be-tested, or pending). An item "
        "that is defined-but-unverified is NOT resolved.\n\n"
        "Output EXACTLY one line, nothing else:\n"
        "  NEXT: <single most important unanswered question> — <why unanswered> "
        "— <evidence that would resolve it>\n"
        "  CONVERGED: <one sentence citing the evidence backing every "
        "load-bearing claim>"
    )
    try:
        env = dict(os.environ)
        if _REPO_ROOT:
            env["HERMES_HOME"] = os.path.join(_REPO_ROOT, "startup")
        proc = subprocess.run(
            ["hermes", "-p", "product-owner", "--accept-hooks",
             "--toolsets", "file", "--skills", "venture-grill",
             "chat", "-q", prompt],
            cwd=_REPO_ROOT or None, capture_output=True, text=True,
            timeout=_SCAN_TIMEOUT, env=env,
        )
        return proc.stdout or ""
    except Exception as exc:
        logger.warning("grill_followup: scan failed: %s", exc)
        return ""


_FORCE_DEEPER = (
    "EXPERIMENT MODE — the scanner judged this venture CONVERGED (claims "
    "evidence-backed), but the loop keeps drilling to observe behavior. Pick the "
    "single most important claim that is ASSUMED-but-not-independently-verified, "
    "OR the next risk without a pre-committed falsification test, and grill VB on "
    "it — push ONE layer deeper than the last iteration. Do NOT converge or "
    "declare done; surface the next falsifiable assumption."
)


def decide_carryover(task_title: str, task_body) -> str:
    """Decide the next-iteration carryover for a venture grill. Run the scanner
    (judgment over CONTEXT.md); on NEXT return the question. EXPERIMENT MODE: on
    CONVERGED (or unclear/no-gap) do NOT terminate — force a 'drill one layer
    deeper' question so the loop keeps going for observation. Unbounded — stop
    manually by completing/blocking the venture's grill cards."""
    slug = _extract_slug(task_body)
    if slug:
        status, question = parse_scan_output(scan_for_next_question(slug))
        if status == "next" and question:
            return question
        # 'converged' or 'unclear' -> do NOT terminate (experiment) -> fall through
    ctx_path = find_context_md(task_title, task_body)
    mech = extract_open_questions(ctx_path)
    if mech:
        return mech
    return _FORCE_DEEPER


def spawn_async_chain(task_title: str, task_body: str) -> None:
    """Detach async_chain.py (scan CONTEXT.md -> decide -> create next [grill]
    card). Non-blocking: fires after the worker exits, so the scanner's latency
    under ZAI quota load can't stall kanban_complete or hit max-runtime (the
    synchronous-in-hook failure that prevented iter-3+). Fail-safe."""
    slug = _extract_slug(task_body)
    if not slug:
        return
    env = dict(os.environ)
    env["HERMES_ASYNC_TITLE"] = str(task_title or "")
    env["HERMES_ASYNC_BODY"] = str(task_body or "")
    env["HERMES_ASYNC_SLUG"] = slug
    script = os.path.join(os.path.dirname(_PLUGIN_FILE), "async_chain.py")
    try:
        subprocess.Popen(
            [sys.executable, script],
            env=env,
            start_new_session=True,  # detach — survives the worker exiting
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except Exception as exc:
        logger.warning("grill_followup: spawn_async_chain failed: %s", exc)


def build_next_spec(
    *, task_title: str, task_body, open_questions: str = ""
) -> dict:
    """Spec for the next grill card: same venture, NO parent link (so PO can't
    look up prior work), clean title, open questions injected into the body, and
    an idempotency key by slug. create_task makes a no-parent task ``ready`` so
    the dispatcher runs it after this worker exits."""
    title = str(task_title or "").strip()
    if title.lower().endswith("(next)"):
        title = title[: -len("(next)")].rstrip()
    slug = _extract_slug(task_body)
    body = str(task_body or "")
    if open_questions:
        prefix = (
            "**ITERATION 2+ grill card.** A scanner found the question below still "
            "OPEN after the prior iteration. You MUST `intercom action=ask "
            "to=venture-builder` VB on it — the prior [grill] card being 'done' "
            "does NOT mean this question is answered, so do NOT `kanban_show` "
            "prior cards and close this as a duplicate re-fire. Grill the question, "
            "record the answer + its evidence status in CONTEXT.md, then "
            "kanban_complete.\n\n**NEXT QUESTION to grill VB on:**\n"
        )
        body = body.rstrip() + "\n\n" + prefix + open_questions + "\n"
    return {
        "title": title,
        "body": body,
        "assignee": "product-owner",
        "skills": ["venture-grill"],
        "idempotency_key": f"venture-grill-next-{slug}" if slug else None,
    }


# --- hook handler (kanban wiring; thin, guarded) ------------------------

def _on_post_tool_call(**kw) -> None:
    """post_tool_call hook.

    Tracks whether this venture-grill session grilled VB; on ``kanban_complete``,
    if it did, spawns the next grill card with the venture's open questions
    (from CONTEXT.md) injected into the body. Fail-safe: never breaks the worker.
    """
    global _session_grilled_vb
    try:
        function_name, function_args = _extract_call(kw)
        task_id = os.environ.get("HERMES_KANBAN_TASK") or kw.get("task_id") or ""
        if not task_id:
            return

        from hermes_cli import kanban_db as kb  # lazy: only inside the worker

        conn = kb.connect()
        try:
            task = kb.get_task(conn, task_id)
        finally:
            try:
                conn.close()
            except Exception:
                pass
        if task is None:
            return
        if "venture-grill" not in (task.skills or []):
            return

        # Tool-level CONTEXT.md rescue (directive #3): canonicalize every
        # write_file/patch of *CONTEXT.md to ~/.venture-builder/<slug>/ so it
        # survives the scratch rmtree that destroys ~10% of grill outputs.
        if function_name in _WRITE_TOOLS:
            maybe_canonicalize_context_md(function_name, function_args, task.body)

        # Track: did this session grill VB?
        if is_grill_intercom(function_name, function_args):
            _session_grilled_vb = True
            return

        # On kanban_complete: if the session grilled VB, carry the grill forward.
        if function_name == "kanban_complete" and _session_grilled_vb:
            # async: detach the scan+decide+create so its latency under ZAI load
            # can't stall kanban_complete or hit max-runtime before the next card
            # is created (the synchronous-in-hook failure that blocked iter-3+).
            spawn_async_chain(task.title, task.body)
            _session_grilled_vb = False
            return
    except Exception as exc:
        # never break the worker over a follow-up card
        logger.warning("grill_followup: hook failed: %s", exc, exc_info=True)


def register(ctx):
    """Wire the post_tool_call hook."""
    ctx.register_hook("post_tool_call", _on_post_tool_call)
