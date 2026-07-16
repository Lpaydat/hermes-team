"""context_graph plugin — a SQLite-backed graph for dynamic project context.

Replaces monolithic CONTEXT.md with a queryable graph:
- Nodes: decisions, facts, terms, artifacts (with status + content + multi-topic tags).
- Edges: blocks, relates_to, caused_by, supersedes, part_of, references (typed).
- Queries: frontier (work queue), pull (topic subgraph), context (node neighborhood).

Multi-topic: one decision tagged auth+data-store+security → retrieved by ALL three
pull() queries. No duplication. No "which file?" ambiguity.

Tools registered:
  graph_frontier     — open decision/fact nodes with no open blockers
  graph_pull         — topic subgraph (multi-topic retrieval)
  graph_context      — node + its neighborhood (focused context)
  graph_add_node     — create a node (with optional multi-topic tags)
  graph_add_edge     — create a typed edge
  graph_resolve_node — mark resolved + record the answer
  graph_tree         — recursive dependency tree
  graph_stats        — node/edge/topic counts
  graph_remaining    — ALL open decision/fact nodes (the grill backlog; empty == done)
"""

import logging
import os
import subprocess

from . import schemas, tools
from . import context_graph as cg

logger = logging.getLogger(__name__)

# The deployment startup root — the HERMES_HOME the kanban CLI must target. The
# kanban CLI inherits the hook process's env; without an explicit HERMES_HOME it
# can silently fall back to a stale ~/.hermes default and the card lands in the
# wrong team (the misroute that broke offline delivery when the intercom broker
# lost this env var — see _shared/intercom/broker/spawner.py). Resolved from
# this file's realpath so it follows the per-profile symlink back to the
# canonical plugin dir — same resolve() discipline as cg.DB_PATH.
_STARTUP_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Sessions that touched the context_graph toolset during their lifetime.
# Populated by the post_tool_call hook (_on_post_tool_call) on every graph_*
# tool call and drained by on_session_end. Hermes' on_session_end kwargs do
# NOT carry the session's tool-call list, so "touched the graph" is observed
# here over the session's lifetime instead. (Mirrors the shipped disk-cleanup
# plugin's track-in-post_tool_call / drain-in-on_session_end pattern.)
_GRAPH_TOUCHED_SESSIONS: set = set()
_GRAPH_TOOL_PREFIX = "graph_"


def register(ctx):
    """Wire the context_graph tools."""
    # initialize the DB on first load
    cg.init_db()

    tools_to_register = [
        ("graph_frontier",     schemas.GRAPH_FRONTIER,     tools.graph_frontier),
        ("graph_pull",         schemas.GRAPH_PULL,         tools.graph_pull),
        ("graph_context",      schemas.GRAPH_CONTEXT,      tools.graph_context),
        ("graph_add_node",     schemas.GRAPH_ADD_NODE,     tools.graph_add_node),
        ("graph_add_edge",     schemas.GRAPH_ADD_EDGE,     tools.graph_add_edge),
        ("graph_resolve_node", schemas.GRAPH_RESOLVE_NODE, tools.graph_resolve_node),
        ("graph_tree",         schemas.GRAPH_TREE,         tools.graph_tree),
        ("graph_stats",        schemas.GRAPH_STATS,        tools.graph_stats),
        ("graph_remaining",    schemas.GRAPH_REMAINING,    tools.graph_remaining),
    ]

    for name, schema, handler in tools_to_register:
        ctx.register_tool(
            name=name,
            toolset="context_graph",
            schema=schema,
            handler=handler,
        )

    ctx.register_hook("on_session_end", _on_session_end)
    ctx.register_hook("post_tool_call", _on_post_tool_call)

    logger.info("context_graph plugin registered (%d tools)", len(tools_to_register))


def _on_post_tool_call(tool_name: str = "", session_id: str = "", **_) -> None:
    """Track whether this session touched the context_graph toolset.

    Hermes fires post_tool_call for every tool call with ``tool_name`` +
    ``session_id``. A grill session makes graph_* calls; we record the
    session_id so the on_session_end hook can distinguish grill sessions from
    unrelated ones (chart sessions, PO work that never touched the graph).
    """
    if session_id and tool_name.startswith(_GRAPH_TOOL_PREFIX):
        _GRAPH_TOUCHED_SESSIONS.add(session_id)


def is_grill_session(session_id: str) -> bool:
    """B2 detection: is ``session_id`` a mid-grill session?

    True iff BOTH:
      1. the session touched the graph (made >=1 graph_* tool call), AND
      2. an open grill root exists (type='root' AND status='open') — a grill
         in progress. A grill that is GRILL COMPLETE has its root resolved,
         so there is no open root and this returns False.

    Detection only — B3/B4 consume a True result to drive transitions.
    """
    if not session_id or session_id not in _GRAPH_TOUCHED_SESSIONS:
        return False
    try:
        return cg.has_open_root()
    except Exception:
        logger.debug("has_open_root check failed", exc_info=True)
        return False


def _get_open_root():
    """Return the open grill root node (type='root', status='open'), or None.

    is_grill_session already confirmed an open root exists (via has_open_root);
    this fetches the row so the next-branch transition can derive the venture
    slug for the continuation card. Reads via cg._get_db() — the graph module's
    connection factory (package-internal, same unit).
    """
    try:
        conn = cg._get_db()
        row = conn.execute(
            "SELECT id, type, status, title, content FROM graph_nodes "
            "WHERE type='root' AND status='open' ORDER BY created_at LIMIT 1"
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        logger.debug("open-root lookup failed", exc_info=True)
        return None


def _venture_slug_from_root(root):
    """Derive the venture slug from an open grill root node.

    Per decision-tree-grill: the root is tagged with the venture <slug> as a
    topic (so the whole tree recovers via graph_pull('<slug>')). Prefer the
    root's first topic; fall back to its content. Returns '' if neither yields
    a slug (the card still fires; recovery is best-effort).
    """
    if not root:
        return ""
    try:
        conn = cg._get_db()
        topics = [
            r["topic"]
            for r in conn.execute(
                "SELECT topic FROM node_topics WHERE node_id=? ORDER BY topic",
                (root["id"],),
            ).fetchall()
        ]
        conn.close()
    except Exception:
        logger.debug("root topic lookup failed", exc_info=True)
        topics = []
    if topics:
        return topics[0]
    return (root.get("content") or "").strip()


def _has_running_card(card_marker, venture_slug):
    """SERIALIZE GUARD: is there ALREADY a RUNNING kanban card of the matching
    type + venture on hermes-hq?

    Root cause this fixes (B3/B4 follow-up): every grill session-end created a
    [grill-loop] / [chart] card, so CONCURRENT session-ends spawned MULTIPLE
    cards for the SAME venture → they collided on the same VB (intercom
    contention) → decisions never resolved → infinite loop. This guard makes
    card creation idempotent per venture: before creating, we check the board
    for a RUNNING card carrying ``card_marker`` (e.g. '[grill-loop]') AND
    ``venture_slug``. If one exists → the caller SKIPS (log + return) instead
    of spawning a duplicate. Only ONE grill-loop (and ONE chart) per venture
    at a time → no parallel collision.

    Shells out to ``hermes kanban list`` (subprocess.run) with the SAME pinned
    env as the create helpers (HERMES_HOME -> startup root,
    HERMES_KANBAN_BOARD -> hermes-hq — the ``--board`` flag and the env var
    resolve identically; the env pin mirrors the existing create helpers). A
    running card line looks like (see kanban._fmt_task_line):

        ● t_xxx  running  product-owner  [grill-loop] gitpulse: ...

    so a running line carries BOTH the '●' icon and the literal status word
    'running'. A line matches iff it is RUNNING (contains '●' OR 'running')
    AND contains ``card_marker`` AND contains ``venture_slug``. Done/blocked
    cards do NOT match → a finished loop never blocks the next.

    Fire-and-log: any subprocess failure (raise or non-zero exit) is swallowed
    and treated as 'no running card' → the caller proceeds to create. A
    transient kanban-list failure must not block the grill->map transition.
    Returns True if a matching RUNNING card exists, False otherwise.
    """
    env = dict(os.environ)
    env["HERMES_HOME"] = _STARTUP_ROOT
    env["HERMES_KANBAN_BOARD"] = "hermes-hq"
    cmd = ["hermes", "kanban", "list"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, env=env, timeout=60
        )
    except Exception:
        logger.debug(
            "context_graph: running-card list raised for %s %s",
            card_marker, venture_slug, exc_info=True,
        )
        return False
    if result.returncode != 0:
        logger.debug(
            "context_graph: running-card list FAILED (rc=%s) for %s %s: %s",
            result.returncode, card_marker, venture_slug,
            (result.stderr or "").strip(),
        )
        return False
    for line in (result.stdout or "").splitlines():
        is_running = ("●" in line) or ("running" in line)
        if is_running and (card_marker in line) and (venture_slug in line):
            return True
    return False


def _create_next_branch_card(venture_slug, remaining_count):
    """Create a next-branch kanban card on hermes-hq: a fresh PO session to
    continue the grill (recover the graph + grill the top open nodes). Shared by
    B3 (non-empty backlog) and B4 (the empty-backlog transition).

    Shells out to the hermes kanban CLI (subprocess.run), mirroring the intercom
    broker's spawner pattern. HERMES_HOME is pinned to the startup root and
    HERMES_KANBAN_BOARD to hermes-hq — the persisted current-board could be
    anything (a smoke board, a venture board), so pinning is the deterministic,
    anti-misroute choice (same philosophy as the broker's _resolve_hermes_home).

    Fire-and-log: a session-end hook must not crash on a card-creation failure,
    so exceptions / non-zero exit are logged, not raised. Returns the CLI stdout
    on success, None on failure (the hook ignores the return).

    SERIALIZE GUARD (B3/B4 follow-up): a [grill-loop] card is created ONLY if no
    RUNNING [grill-loop] card already exists for this venture. Concurrent grill
    session-ends used to each spawn one → parallel cards collided on the same VB
    (intercom contention) → decisions never resolved → infinite loop. See
    _has_running_card. Guard first; on a running duplicate, log + return None.
    """
    if _has_running_card("[grill-loop]", venture_slug):
        logger.info(
            "context_graph: grill-loop already running for %s, skipping duplicate",
            venture_slug or "(unknown venture)",
        )
        return None
    title = (
        f"[grill-loop] {venture_slug}: continue grill — "
        f"{remaining_count} open nodes remain"
    )
    body = (
        f"Recover the graph FIRST (graph_pull('{venture_slug}') -> type=root -> "
        "graph_tree(root) -> graph_frontier()), then grill VB over intercom on the "
        "TOP open decision nodes — do NOT re-do resolved nodes. End when the branch "
        "is done; the plugin continues."
    )
    env = dict(os.environ)
    env["HERMES_HOME"] = _STARTUP_ROOT
    env["HERMES_KANBAN_BOARD"] = "hermes-hq"
    cmd = [
        "hermes", "kanban", "create", title,
        "--assignee", "product-owner",
        "--skill", "decision-tree-grill",
        "--body", body,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, env=env, timeout=60
        )
    except Exception:
        logger.error(
            "context_graph: next-branch card creation raised for %s",
            venture_slug, exc_info=True,
        )
        return None
    if result.returncode != 0:
        logger.error(
            "context_graph: next-branch card creation FAILED (rc=%s) for %s: %s",
            result.returncode, venture_slug, (result.stderr or "").strip(),
        )
        return None
    logger.info(
        "context_graph: created next-branch card for %s (%d open nodes remain): %s",
        venture_slug, remaining_count, (result.stdout or "").strip(),
    )
    return (result.stdout or "").strip() or None


def _create_chart_card(venture_slug):
    """Create the chart kanban card on hermes-hq: the grill->map transition.

    The terminal transition. Fires when a grill session ends with an EMPTY
    graph_remaining() — the grill is genuinely exhausted — so the venture moves
    from grilling (deciding) to CHARTING the wayfinding map. The card hands off
    to the product-owner with BOTH the wayfinding-auto + wayfinder skills: chart
    the destination, spin the wayfinder:map epic, and break it into child tickets
    — from the brief AND the pinned graph (term nodes + resolved decisions).

    Sibling of _create_next_branch_card (B3) — same kanban-CLI / pinned-env /
    fire-and-log discipline (HERMES_HOME -> startup root, HERMES_KANBAN_BOARD ->
    hermes-hq). Returns the CLI stdout on success, None on failure (the hook
    ignores the return).

    SERIALIZE GUARD (B3/B4 follow-up): a [chart] card is created ONLY if no
    RUNNING [chart] card already exists for this venture — same parallelism fix
    as the grill-loop guard, so concurrent exhausted-backlog session-ends don't
    each spawn a chart card and collide on the same venture. See
    _has_running_card. Guard first; on a running duplicate, log + return None.
    """
    if _has_running_card("[chart]", venture_slug):
        logger.info(
            "context_graph: chart already running for %s, skipping duplicate",
            venture_slug or "(unknown venture)",
        )
        return None
    title = f"[chart] {venture_slug}: chart the wayfinding map"
    body = (
        "CHART-THE-MAP card. SHARED LANGUAGE: graph_pull('{slug}') returns the "
        "grill's pinned term nodes (type=term) + resolved decisions. ADRs under "
        "docs/ventures/{slug}/docs/adr/. Chart from BOTH the brief + the graph. "
        "DO: name the destination; create the map epic (wayfinder:map); create "
        "the child tickets. COMPLETE — chart only, resolve nothing."
    ).format(slug=venture_slug)
    env = dict(os.environ)
    env["HERMES_HOME"] = _STARTUP_ROOT
    env["HERMES_KANBAN_BOARD"] = "hermes-hq"
    cmd = [
        "hermes", "kanban", "create", title,
        "--assignee", "product-owner",
        "--skill", "wayfinding-auto",
        "--skill", "wayfinder",
        "--body", body,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, env=env, timeout=60
        )
    except Exception:
        logger.error(
            "context_graph: chart card creation raised for %s",
            venture_slug, exc_info=True,
        )
        return None
    if result.returncode != 0:
        logger.error(
            "context_graph: chart card creation FAILED (rc=%s) for %s: %s",
            result.returncode, venture_slug, (result.stderr or "").strip(),
        )
        return None
    logger.info(
        "context_graph: created chart card for %s (grill exhausted -> map): %s",
        venture_slug, (result.stdout or "").strip(),
    )
    return (result.stdout or "").strip() or None


def _on_session_end(session_id: str = "", **kw) -> None:
    """Session-end lifecycle hook (B2 detection + B3/B4 transitions).

    Detects whether the ended session was a mid-grill session (touched the
    graph AND an open grill root exists). Non-grill sessions are a no-op.

    B3 transition: if it IS a mid-grill session AND graph_remaining() is
    NON-EMPTY (open decision/fact nodes remain), create a next-branch kanban
    card on hermes-hq — a fresh PO session to recover the graph + continue the
    grill on the top open nodes. This is how the grill loops across sessions.

    B4 transition: if it IS a mid-grill session AND graph_remaining() is EMPTY,
    the grill is genuinely exhausted — create the chart card instead (the
    grill->map transition): hand off to the PO with wayfinding-auto + wayfinder
    to chart the wayfinding map. Terminal.

    Hermes fires on_session_end with kwargs {session_id, completed,
    interrupted, model, platform, reason, and sometimes task_id / turn_id /
    api_request_id}. None of those carry the session's tool-call list, so
    "touched the graph" is read from the post_tool_call tracker
    (_GRAPH_TOUCHED_SESSIONS) populated over the session's lifetime.
    """
    grill = is_grill_session(session_id)
    if grill:
        logger.info(
            "context_graph: grill session detected (session_id=%s) — mid-grill, "
            "open root exists",
            session_id,
        )
        # B3/B4 branch on the backlog:
        #   NON-empty -> B3: continue the grill in a fresh PO session.
        #   EMPTY     -> B4: the grill is genuinely exhausted -> create the
        #               chart card (the grill->map transition). Terminal.
        try:
            remaining = cg.graph_remaining()
        except Exception:
            logger.debug("graph_remaining query failed", exc_info=True)
            remaining = []
        if remaining:
            root = _get_open_root()
            slug = _venture_slug_from_root(root)
            logger.info(
                "context_graph: non-empty backlog (%d open nodes) at grill "
                "session-end — creating next-branch card for %s",
                len(remaining), slug or "(unknown venture)",
            )
            _create_next_branch_card(slug, len(remaining))
        else:
            # B4: EMPTY backlog -> grill exhausted -> chart the wayfinding map.
            root = _get_open_root()
            slug = _venture_slug_from_root(root)
            logger.info(
                "context_graph: EMPTY backlog at grill session-end — grill "
                "exhausted, creating chart card for %s (grill->map transition)",
                slug or "(unknown venture)",
            )
            _create_chart_card(slug)
    else:
        logger.debug(
            "context_graph: session %s not a mid-grill session (touched_graph=%s)",
            session_id,
            session_id in _GRAPH_TOUCHED_SESSIONS,
        )
    # Drain the per-session tracker either way (mirrors disk-cleanup's bucket
    # drain) so it never leaks across sessions.
    _GRAPH_TOUCHED_SESSIONS.discard(session_id)
    return None
