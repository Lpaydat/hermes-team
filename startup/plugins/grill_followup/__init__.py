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
    #   3. ~/vault/ventures/<name>/             (venture-pipeline vault convention)
    # Search all three + the worker's cwd + HERMES_HOME.
    names = [n for n in (venture, slug) if n]
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
    # vault convention (~/vault/ventures/<name>/ — no "docs/" prefix)
    for name in names:
        p = os.path.join(vault, "ventures", name, "CONTEXT.md")
        if os.path.isfile(p):
            return p
    return None


def extract_open_questions(context_path: Optional[str]) -> str:
    """Extract the open-questions block from CONTEXT.md (the unresolved items).

    PO records these two ways, both matched (case-insensitive on "Open"):
      - a heading: ``## Open questions`` / ``## Open grill branches`` — block runs
        to the next ``## `` heading.
      - a bold line: ``**Open questions (parked...):**`` — block runs to the next
        blank line or heading/bold opener (the list ends there).
    Returns the block (opener + items), stripped; '' if missing or no open block.
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
            if re.match(r"^##\s*Open", line, re.IGNORECASE):
                in_section, bold = True, False
                section.append(line)
            elif re.match(r"^\*\*Open", line, re.IGNORECASE):
                in_section, bold = True, True
                section.append(line)
        else:
            # heading form ends at the next ## ; bold form ends at a blank line
            # or any new heading/bold opener.
            if re.match(r"^##\s", line) or (bold and (line.strip() == "" or re.match(r"^\*\*", line))):
                break
            section.append(line)
    while section and not section[-1].strip():
        section.pop()
    return "".join(section).strip()


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
        body = body.rstrip() + "\n\n" + open_questions + "\n"
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

        # Track: did this session grill VB?
        if is_grill_intercom(function_name, function_args):
            _session_grilled_vb = True
            return

        # On kanban_complete: if the session grilled VB, carry the grill forward.
        if function_name == "kanban_complete" and _session_grilled_vb:
            ctx_path = find_context_md(task.title, task.body)
            open_qs = extract_open_questions(ctx_path)
            spec = build_next_spec(
                task_title=task.title,
                task_body=task.body,
                open_questions=open_qs,
            )
            conn = kb.connect()
            try:
                kb.create_task(
                    conn,
                    title=spec["title"],
                    body=spec["body"],
                    assignee=spec["assignee"],
                    skills=spec["skills"],
                    created_by="grill_followup-plugin",
                    idempotency_key=spec["idempotency_key"],
                )
                logger.info(
                    "grill_followup: spawned next grill card for %s (open questions injected: %s)",
                    task_id,
                    bool(open_qs),
                )
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            _session_grilled_vb = False
    except Exception as exc:
        # never break the worker over a follow-up card
        logger.warning("grill_followup: hook failed: %s", exc, exc_info=True)


def register(ctx):
    """Wire the post_tool_call hook."""
    ctx.register_hook("post_tool_call", _on_post_tool_call)
