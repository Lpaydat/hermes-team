"""Tool handlers — kanban_group: deterministic group wiring (milestone barriers).

Pure shape, per SPEC.md: creates marker cards + dependency links, never
executes, spawns, or completes real work. Cards own "what"; workflows own
"how" — this tool only wires the gate between them.

Implementation baseline: kanban_chains' hardened subprocess layer (150s
timeouts outlasting the CLI's 120s busy_timeout, no-raise, retry with
backoff) and its verified-link discipline — a link that silently fails to
land is a broken barrier, so every link is re-read from the child card
before success is reported.
"""

import json
import logging
import subprocess

logger = logging.getLogger(__name__)

GATE_LANE = "workflow-gate"


def _get_board(explicit=None):
    import os
    return (explicit or "").strip() or os.environ.get("HERMES_KANBAN_BOARD", "startup")


def _run_kanban(args_list, board=None):
    """Run a hermes kanban command, return (success, output_text).

    Lock-race hardening (proven 2026-08-15, copied from kanban_chains):
    the CLI's own busy_timeout is 120s, so subprocess timeouts must
    outlast it or queued writes die as TimeoutExpired crashes. Transient
    failures (timeout / 'locked') retry with backoff before giving up.
    """
    import os, time as _time
    cmd = ["hermes", "kanban", "--board", _get_board(board)] + args_list
    env = os.environ.copy()
    attempts = [
        (0.0, 150),   # outlast the CLI's 120s busy_timeout
        (2.0, 150),
        (5.0, 150),
    ]
    last_err = ""
    for i, (backoff, tmo) in enumerate(attempts):
        if backoff:
            _time.sleep(backoff)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=tmo, env=env)
        except subprocess.TimeoutExpired:
            last_err = f"timeout after {tmo}s: {' '.join(args_list[:3])}"
            continue
        if result.returncode == 0 and result.stdout.strip():
            return True, result.stdout.strip()
        if result.returncode == 0:
            # rc=0 with EMPTY stdout: the CLI's handled error paths can exit
            # 0 with the message on stderr only (observed: 'kanban: unknown
            # task(s)', missing board, link cycle ValueError). Every kanban
            # SUCCESS prints output — treat silent rc=0 as a failure.
            return False, (result.stderr or "").strip()[:300] or "rc=0 but no output"
        last_err = (result.stderr or result.stdout or "").strip()[:300]
        if "locked" in last_err.lower():
            continue  # transient — retry
        return False, last_err
    return False, f"kanban {' '.join(args_list[:3])} failed after {len(attempts)} attempts: {last_err}"


def _run_kanban_json(args_list, board=None):
    """Run a hermes kanban command with --json, return parsed JSON or {'error': …}."""
    ok, out = _run_kanban(args_list + ["--json"], board=board)
    if not ok:
        return {"error": out}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"error": f"non-JSON output: {out[:200]}"}


def _profile_ok(name):
    """True when `name` is a real profile or the workflow-gate control lane.

    Degrades open (True) when hermes_cli isn't importable OR no profiles
    root exists (throwaway/HERMES_HOME-isolated boards have no team) — the
    plugin then behaves like kanban_chains (unknown assignees never spawn).
    """
    if name == GATE_LANE:
        return True
    try:
        from hermes_cli import profiles as _p
        if not _p._get_profiles_root().is_dir():
            return True  # no team configured — cannot validate, degrade open
        return bool(_p.profile_exists(name))
    except Exception:
        return True


class _Invalid(Exception):
    """Boundary-validation failure — surfaces as a structured bad_args error."""


# ── normalization ─────────────────────────────────────────────────────────────


def _normalize_members(raw):
    if not raw or not isinstance(raw, list):
        raise _Invalid("members is required and must be a non-empty list")
    members = []
    for i, m in enumerate(raw):
        if isinstance(m, str):
            card, done = m.strip(), m.strip()
        elif isinstance(m, dict):
            card = (m.get("card") or "").strip()
            done = (m.get("done") or "").strip() or card
        else:
            raise _Invalid(f"members[{i}]: expected a card id or {{card, done}}")
        if not card:
            raise _Invalid(f"members[{i}]: 'card' is required")
        members.append({"card": card, "done": done})
    return members


def _normalize_stages(raw, label):
    """pre/post → list of stages; each stage a list of steps.

    A bare dict is one single-step stage; a sub-list is a parallel stage.
    Each step is {gate: id} (existing card) or a create spec
    ({assignee, title, body?, skills?/skill?, priority?}).
    """
    stages = []
    for i, stage in enumerate(raw or []):
        if isinstance(stage, dict):
            stage = [stage]
        if not isinstance(stage, list) or not stage:
            raise _Invalid(f"{label}[{i}] must be a step object or a non-empty sub-list of parallel steps")
        steps = []
        for j, step in enumerate(stage):
            if not isinstance(step, dict):
                raise _Invalid(f"{label}[{i}][{j}] must be an object")
            gate = (step.get("gate") or "").strip()
            if gate:
                steps.append({"gate": gate})
                continue
            assignee = (step.get("assignee") or "").strip()
            title = (step.get("title") or "").strip()
            if not assignee:
                raise _Invalid(f"{label}[{i}][{j}]: 'assignee' is required for created steps (or use {{gate: id}} to wait on an existing card)")
            if not title:
                raise _Invalid(f"{label}[{i}][{j}]: 'title' is required for created steps")
            skills = step.get("skills")
            if not skills and step.get("skill"):
                skills = [step["skill"]]
            steps.append({
                "create": {
                    "assignee": assignee,
                    "title": title,
                    "body": step.get("body") or "",
                    "skills": skills or [],
                    "priority": step.get("priority"),
                }
            })
        stages.append(steps)
    return stages


def _err(code, message, repair, key=None, partial=None):
    out = {
        "status": "error",
        "group_key": key,
        "board": _get_board(),
        "pre": [], "members": [], "post": [], "links": [],
        "graph": "",
        "error": {"code": code, "message": message, "repair": repair},
    }
    if partial:
        out.update(partial)
    return json.dumps(out, indent=2)


# ── stage resolution (create with idempotency keys) ──────────────────────────


def _resolve_stages(stages, label, key, board, known_ids):
    """Materialize every stage step to a card id.

    Created steps carry deterministic idempotency keys
    (group:<key>:<label>:<i>:<j>) so a re-invoke with the same group key
    resolves to the SAME cards — retry is always safe, zero duplicates.
    `known_ids` (board snapshot) marks pre-existing ids as 'recovered'.
    """
    resolved = []
    for i, steps in enumerate(stages):
        row = []
        for j, step in enumerate(steps):
            if "gate" in step:
                row.append({"card": step["gate"], "origin": "existing"})
                continue
            spec = step["create"]
            cmd = [
                "create", spec["title"],
                "--assignee", spec["assignee"],
                "--idempotency-key", f"group:{key}:{label}:{i}:{j}",
            ]
            if spec["body"]:
                cmd += ["--body", spec["body"]]
            for s in spec["skills"]:
                cmd += ["--skill", s]
            if spec["priority"] is not None:
                cmd += ["--priority", str(spec["priority"])]
            res = _run_kanban_json(cmd, board=board)
            cid = res.get("id") if isinstance(res, dict) else None
            if not cid:
                return None, _err(
                    "create_failed",
                    f"failed to create {label}[{i}][{j}] ({spec['title']}): {res.get('error', res)}",
                    "RETRY IS SAFE — re-call group_cards with identical arguments; "
                    "idempotency keys resolve to the same cards, no duplicates.",
                    key=key, partial={"pre": [r for r in resolved], "post": []},
                )
            row.append({"card": cid, "origin": "recovered" if cid in known_ids else "created"})
        resolved.append(row)
    return resolved, None


# ── main handler ─────────────────────────────────────────────────────────────


def group_cards(args: dict, **kwargs) -> str:
    """Wire a deterministic group: pre stages → members (unlock AND) → post fan-in."""
    import os

    key = (args.get("key") or "").strip()
    if not key:
        return _err("bad_args", "key is required — it anchors idempotency", "Pass a stable group key (e.g. 'm2'); re-invokes with the same key recover the same cards.")
    if any(ch.isspace() for ch in key):
        return _err("bad_args", f"key '{key}' must not contain whitespace (it is embedded in CLI args and idempotency keys)", "Use a compact key like 'm2' or 'release-1'. RETRY IS SAFE.", key=key)
    board = _get_board(args.get("board"))
    try:
        members = _normalize_members(args.get("members"))
        pre = _normalize_stages(args.get("pre"), "pre")
        post = _normalize_stages(args.get("post"), "post")
    except _Invalid as e:
        return _err("bad_args", str(e), "Fix the arguments and re-call. RETRY IS SAFE (idempotent).", key=key)
    await_caller = bool(args.get("await_caller"))
    my_card_id = kwargs.get("task_id") or os.environ.get("HERMES_KANBAN_TASK")
    if await_caller and not my_card_id:
        return _err("bad_args", "await_caller requires a calling card", "Set HERMES_KANBAN_TASK or drop await_caller.", key=key)

    # 1. Profile validation first — pure local check, no board access, so a
    #    typo'd assignee is rejected before anything is created.
    for label, stages in (("pre", pre), ("post", post)):
        for i, steps in enumerate(stages):
            for j, step in enumerate(steps):
                if "create" in step and not _profile_ok(step["create"]["assignee"]):
                    return _err("unknown_profile", f"{label}[{i}][{j}] assignee '{step['create']['assignee']}' is not a real profile (nor '{GATE_LANE}')", "Use a real profile name from the team, or the workflow-gate lane for markers. RETRY IS SAFE.", key=key)

    # 2. Board snapshot — validates every referenced id exists AND detects
    #    recovery (a card id already present pre-invoke was created by an
    #    earlier run of this same group key).
    snap = _run_kanban_json(["list"], board=board)
    if not isinstance(snap, list):
        return _err("board_unavailable", f"cannot list board '{board}': {snap.get('error', snap) if isinstance(snap, dict) else snap}", "Check the board slug / HERMES_KANBAN_BOARD and re-call. RETRY IS SAFE.", key=key)
    known = {t.get("id"): t.get("status") for t in snap if isinstance(t, dict)}

    for m in members:
        for ref in (m["card"], m["done"]):
            if ref not in known:
                return _err("unknown_card", f"member card '{ref}' does not exist on board '{board}'", "Create the member cards first, then re-call group_cards. RETRY IS SAFE.", key=key)
    for label, stages in (("pre", pre), ("post", post)):
        for i, steps in enumerate(stages):
            for j, step in enumerate(steps):
                if "gate" in step and step["gate"] not in known:
                    return _err("unknown_card", f"{label}[{i}][{j}] gate '{step['gate']}' does not exist on board '{board}'", "Fix the gate id and re-call. RETRY IS SAFE.", key=key)

    # 3. Materialize stages (creates are idempotent by key).
    pre_stages, err = _resolve_stages(pre, "pre", key, board, known)
    if err:
        return err
    post_stages, err = _resolve_stages(post, "post", key, board, known)
    if err:
        payload = json.loads(err)
        payload["pre"] = pre_stages  # pre cards already resolved — report them
        return json.dumps(payload, indent=2)

    # 3. Compute the link set (parent, child) — deduped, order-stable.
    pairs = []

    def _link(parent, child):
        if (parent, child) not in pairs and parent != child:
            pairs.append((parent, child))

    for i in range(1, len(pre_stages)):
        for parent in pre_stages[i - 1]:
            for child in pre_stages[i]:
                _link(parent["card"], child["card"])
    if pre_stages:
        for parent in pre_stages[-1]:
            for m in members:
                _link(parent["card"], m["card"])
    if post_stages:
        for m in members:
            for child in post_stages[0]:
                _link(m["done"], child["card"])
        for i in range(1, len(post_stages)):
            for parent in post_stages[i - 1]:
                for child in post_stages[i]:
                    _link(parent["card"], child["card"])

    # 4. Link all — kernel rejects cycles; surface them as structured errors.
    link_cmd_failures = []
    for p, c in pairs:
        ok, out = _run_kanban(["link", p, c], board=board)
        if not ok:
            if "cycle" in out.lower():
                return _err(
                    "cycle",
                    f"linking {p} -> {c} would create a dependency cycle — the group shape loops back on itself",
                    "Remove the reference that closes the loop and re-call group_cards with the same key. "
                    "No real work was touched; marker cards created so far are keyed and harmless.",
                    key=key,
                    partial={"pre": pre_stages, "members": members, "post": post_stages},
                )
            link_cmd_failures.append((p, c, out))

    # 5. await_caller — park the calling card until the group's terminus
    #    (last post stage, else every member done-marker) completes.
    if await_caller:
        terminals = [s["card"] for s in post_stages[-1]] if post_stages else [m["done"] for m in members]
        for t in terminals:
            _link(t, my_card_id)
        for p, c in pairs:
            if c == my_card_id:
                ok, out = _run_kanban(["link", p, c], board=board)
                if not ok and "cycle" in out.lower():
                    return _err("cycle", f"linking {p} -> {c} would create a dependency cycle", "Fix the shape and re-call. RETRY IS SAFE.", key=key)
        reason = f"waiting_for_group:{key}"
        ok, block_out = _run_kanban(["block", my_card_id, reason, "--kind", "dependency"], board=board)
        if not ok:
            return _err("block_failed", f"park of caller {my_card_id} failed: {block_out}",
                        f"Run: hermes kanban --board {board} block {my_card_id} {reason} --kind dependency",
                        key=key, partial={"pre": pre_stages, "members": members, "post": post_stages, "links": []})
        # Verify the park took (2026-08-15 strand: rc=0 yet write never landed).
        status_now = None
        for attempt in (1, 2):
            show = _run_kanban_json(["show", my_card_id], board=board)
            status_now = (show.get("task", show) or {}).get("status") if isinstance(show, dict) else None
            if status_now == "todo":
                break
            if attempt == 1:
                _run_kanban(["block", my_card_id, reason, "--kind", "dependency"], board=board)
        if status_now != "todo":
            return _err(
                "park_unverified",
                f"park of caller {my_card_id} did not take effect (status={status_now}, expected todo)",
                f"Links are in place. ONE call only: hermes kanban --board {board} block {my_card_id} {reason} --kind dependency "
                "(NEVER a plain block — it is sticky and never auto-promotes). Do NOT re-call group_cards.",
                key=key, partial={"pre": pre_stages, "members": members, "post": post_stages, "links": []},
            )

    # 6. Verify every link landed — re-read each child's parents.
    links = []
    parents_cache = {}
    verify_failures = []
    for p, c in pairs:
        if c not in parents_cache:
            show = _run_kanban_json(["show", c], board=board)
            parents_cache[c] = (show.get("parents") or []) if isinstance(show, dict) else []
        ok = p in parents_cache[c]
        links.append({"parent": p, "child": c, "verified": ok})
        if not ok:
            verify_failures.append((p, c))

    recovered = any(
        step["origin"] == "recovered"
        for stages in (pre_stages, post_stages)
        for row in stages for step in row
    )
    status = "recovered" if recovered else "wired"

    # Warnings — honest reporting of members the barrier cannot govern.
    warnings = []
    for m in members:
        st = known.get(m["card"])
        if st not in ("todo", "ready", None):
            warnings.append(f"member {m['card']} is already '{st}' — the barrier cannot hold work that started or finished before wiring")

    if verify_failures:
        repair = "; ".join(
            f"hermes kanban --board {board} link {p} {c}" for p, c in verify_failures
        )
        out = {
            "status": "error",
            "group_key": key,
            "board": board,
            "pre": pre_stages, "members": members, "post": post_stages,
            "links": links,
            "graph": _mermaid(pre_stages, members, post_stages, my_card_id if await_caller else None),
            "error": {
                "code": "link_unverified",
                "message": f"{len(verify_failures)} link(s) did not land: " + ", ".join(f"{p}->{c}" for p, c in verify_failures),
                "repair": f"{repair} — or simply re-call group_cards with the SAME arguments (idempotent, safe).",
            },
            "warnings": warnings,
        }
        if link_cmd_failures:
            out["link_command_failures"] = [[p, c, why] for p, c, why in link_cmd_failures]
        return json.dumps(out, indent=2)

    graph = _mermaid(pre_stages, members, post_stages, my_card_id if await_caller else None)
    msg = (f"Group '{key}' {status}: {len(members)} member(s), "
           f"{sum(len(r) for r in pre_stages)} pre step(s), {sum(len(r) for r in post_stages)} post step(s), "
           f"{len(links)} link(s) all verified.")
    if await_caller:
        msg += f" Caller {my_card_id} parked (dependency) until the group terminus completes."
    return json.dumps({
        "status": status,
        "group_key": key,
        "board": board,
        "pre": pre_stages,
        "members": members,
        "post": post_stages,
        "links": links,
        "graph": graph,
        "message": msg,
        "warnings": warnings,
    }, indent=2)


def _mermaid(pre_stages, members, post_stages, caller):
    """Real links only — no inferred edges. Member labels carry the done-marker."""
    lines = ["graph TD"]
    for m in members:
        label = m["card"] if m["done"] == m["card"] else f"{m['card']} (done: {m['done']})"
        lines.append(f'  {m["card"]}["member {label}"]')
    for stages, label in ((pre_stages, "pre"), (post_stages, "post")):
        for i, row in enumerate(stages):
            for step in row:
                lines.append(f'  {step["card"]}["{label}[{i}] {step["origin"]}"]')
    for stages in (pre_stages, post_stages):
        for i in range(1, len(stages)):
            for parent in stages[i - 1]:
                for child in stages[i]:
                    lines.append(f'  {parent["card"]} --> {child["card"]}')
    if pre_stages:
        for parent in pre_stages[-1]:
            for m in members:
                lines.append(f'  {parent["card"]} --> {m["card"]}')
    if post_stages:
        for m in members:
            for child in post_stages[0]:
                lines.append(f'  {m["done"]} --> {child["card"]}')
    if caller:
        terminals = [s["card"] for s in post_stages[-1]] if post_stages else [m["done"] for m in members]
        for t in terminals:
            lines.append(f"  {t} --> {caller}")
    return "\n".join(lines)
