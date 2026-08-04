"""Workflow definition model — a workflow is a JSON file with nodes and edges."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import json
import re
from typing import Any


@dataclass
class Trigger:
    """What starts this workflow."""
    source: str          # "card_completed" | "bead_ready" | "manual"
    condition: dict      # filter params, e.g. {"assignee": "qa", "metadata.verdict": "PASS"}


@dataclass
class NodeInput:
    """What a node needs to run."""
    schema: dict         # JSON Schema the input must conform to
    sources: dict        # variable bindings, e.g. {"spec_path": "${nodes.plan.output.spec_path}"}


@dataclass
class NodeOutput:
    """What a node must produce."""
    schema: dict         # JSON Schema the output metadata must conform to


@dataclass
class Node:
    """A single step in the workflow.

    type: "task" (default) — creates a kanban card for a profile to execute.
    type: "subworkflow" — starts a child workflow instance and blocks until it completes.
    """
    id: str
    profile: str         # which agent profile runs this (e.g. "verifier")
    skill: str           # which skill to load (e.g. "adversarial-review")
    body_template: str   # card body template with ${} variables
    title_template: str = ""  # custom card title for foreach nodes (supports ${item}, ${item.field})
    input: NodeInput | None = None
    output: NodeOutput | None = None
    card_mode: str = "template"  # "template" | "delegate" | "chain"
    depends_on: list[str] = field(default_factory=list)
    condition: str | None = None  # if set, node only runs when this evaluates true
    foreach: str | None = None     # if set, iterate over a list (e.g. "${nodes.tickets.output.beads}")
    type: str = "task"             # "task" | "subworkflow" | "command" | "wait"
    workflow_ref: str = ""         # for type="subworkflow": child workflow template ID
    input_mapping: dict = field(default_factory=dict)   # params to pass to child workflow
    output_mapping: dict = field(default_factory=dict)  # child outputs to map back to parent
    command: str = ""              # for type="command": shell command to run (supports ${} vars)
    wait_condition: str = ""       # for type="wait": condition string to poll each tick


@dataclass
class Edge:
    """An explicit edge between two nodes with an optional condition.

    Edges can be declared explicitly in the JSON template:
      "edges": [
        {"from": "check", "to": "ship", "condition": "${nodes.check.output.verdict} == 'PASS'"},
        {"from": "check", "to": "fix", "condition": "${nodes.check.output.verdict} == 'FAIL'" }
      ]

    Or implicitly via Node.depends_on + Node.condition (backwards compatible).
    Explicit edges take precedence when present.
    """
    from_node: str
    to_node: str
    condition: str | None = None  # if set, edge only active when this evaluates true
    is_back_edge: bool = False            # computed: both endpoints in same SCC
    max_iterations: int | None = None     # explicit iteration cap for back-edges


# Regex detecting an iteration cap in a back-edge condition clause:
#   ${...iteration...} <op> <number>   OR   ${...iteration...} >= <number>
_ITERATION_RE = re.compile(r"\$\{.*iteration.*\}\s*[<>=]")


def bfs_reachable(edges, seed_ids, all_node_ids):
    """Forward BFS from seed nodes following all edges. Returns reachable set."""
    visited = set(seed_ids)
    queue = list(seed_ids)
    while queue:
        cur = queue.pop(0)
        for e in edges:
            if e.from_node == cur and e.to_node not in visited and e.to_node in all_node_ids:
                visited.add(e.to_node)
                queue.append(e.to_node)
    return visited


def compute_exit_nodes(nodes, edges):
    """Nodes with no outgoing edges."""
    has_outgoing = {e.from_node for e in edges}
    return [n for n in nodes if n.id not in has_outgoing]


def tarjan_scc(nodes: list[str], edges: list[tuple[str, str]]) -> list[set[str]]:
    """Compute strongly-connected components via Tarjan's algorithm.

    Returns a list of sets; each set is the node ids in one SCC. Single-node
    SCCs (no self-loop) are included. Iterative (no recursion) so it won't
    blow the stack on large cyclic graphs.
    """
    # Build adjacency list.
    graph: dict[str, list[str]] = {n: [] for n in nodes}
    for src, dst in edges:
        if src in graph:  # only count edges whose endpoints are known nodes
            graph[src].append(dst)

    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    result: list[set[str]] = []

    def strongconnect(start: str) -> None:
        # Iterative DFS with explicit work stack. Each frame is
        # (node, iterator-over-its-neighbors).
        work: list[tuple[str, Any]] = [(start, iter(graph[start]))]
        indices[start] = index_counter[0]
        lowlinks[start] = index_counter[0]
        index_counter[0] += 1
        stack.append(start)
        on_stack.add(start)

        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in graph:
                    continue  # dangling edge target; skip
                if w not in indices:
                    indices[w] = index_counter[0]
                    lowlinks[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(graph[w])))
                    advanced = True
                    break
                elif w in on_stack:
                    lowlinks[v] = min(lowlinks[v], indices[w])
            if advanced:
                continue
            # All neighbors of v processed — check if v is an SCC root.
            if lowlinks[v] == indices[v]:
                comp: set[str] = set()
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.add(w)
                    if w == v:
                        break
                result.append(comp)
            work.pop()
            if work:
                parent = work[-1][0]
                lowlinks[parent] = min(lowlinks[parent], lowlinks[v])

    for node in nodes:
        if node not in indices:
            strongconnect(node)

    return result


def annotate_back_edges(edges: list[Edge], nodes: list[Node]) -> None:
    """Mark is_back_edge using DFS discovery order.

    A back-edge is an edge that points from a descendant to an ancestor
    in the DFS tree (i.e., the target was discovered before the source
    AND there is a path from target back to source). In a 2-node cycle
    (A→B, B→A), the DFS visits A first, then B. Edge A→B is a tree/forward
    edge (not a back-edge). Edge B→A is a back-edge (A is an ancestor of B).

    This is more precise than SCC membership: it marks only the edge that
    CLOSES the cycle, not the forward edge.
    """
    node_ids = [n.id for n in nodes]
    id_set = set(node_ids)

    # DFS to compute discovery times.
    graph: dict[str, list[str]] = {n: [] for n in node_ids}
    for edge in edges:
        if edge.from_node in graph:
            graph[edge.from_node].append(edge.to_node)

    discovered: dict[str, int] = {}  # node → discovery order
    on_stack: set[str] = set()       # nodes on the current DFS path
    counter = [0]

    def dfs(start: str):
        stack: list[tuple[str, list[str]]] = [(start, list(graph.get(start, [])))]
        discovered[start] = counter[0]
        counter[0] += 1
        on_stack.add(start)

        while stack:
            node, neighbors = stack[-1]
            if not neighbors:
                on_stack.discard(node)
                stack.pop()
                continue
            nxt = neighbors.pop(0)
            if nxt not in id_set:
                continue
            if nxt not in discovered:
                discovered[nxt] = counter[0]
                counter[0] += 1
                on_stack.add(nxt)
                stack.append((nxt, list(graph.get(nxt, []))))
            # If nxt is already discovered and on the current DFS path,
            # it's a back-edge ancestor — but the edge annotation is done below.

    for nid in node_ids:
        if nid not in discovered:
            dfs(nid)

    # Annotate edges: back-edge iff target discovered before source AND
    # target is an ancestor of source (reachable via DFS path from target to source).
    # For simplicity, use the SCC approach but only mark edges where
    # target discovery <= source discovery (target was seen first).
    # This correctly marks B→A as back-edge (A discovered first) but not A→B.
    for edge in edges:
        if edge.from_node not in discovered or edge.to_node not in discovered:
            continue
        # Back-edge: target was discovered before source (ancestor → source)
        # AND both are in the same cycle. We check cycle membership via SCC
        # but only mark edges going "backward" in DFS order.
        src_disc = discovered[edge.from_node]
        dst_disc = discovered[edge.to_node]
        if dst_disc <= src_disc and edge.from_node == edge.to_node:
            # Self-loop: always a back-edge
            edge.is_back_edge = True
        elif dst_disc < src_disc:
            # This edge goes back to an earlier-discovered node.
            # Verify it's a real cycle (not just a cross-edge) by checking
            # that there's a forward path from dst to src.
            # For our small graphs, SCC membership is the right check.
            sccs = tarjan_scc(node_ids, [(e.from_node, e.to_node) for e in edges])
            node_to_comp: dict[str, int] = {}
            for ci, comp in enumerate(sccs):
                for nid in comp:
                    node_to_comp[nid] = ci
            fc = node_to_comp.get(edge.from_node)
            tc = node_to_comp.get(edge.to_node)
            if fc is not None and tc is not None and fc == tc:
                if len(sccs[fc]) > 1 or edge.from_node == edge.to_node:
                    edge.is_back_edge = True

def _validate_template_graph(
    nodes: list[Node],
    edges: list[Edge],
    declared_entry_nodes: list[str],
    exit_condition: str | None,
    nodes_by_id: dict[str, Node],
) -> None:
    """Run the load-time structural validation gates.

    Raises ValueError on the first failure. Called from Workflow.from_dict()
    after edges are parsed and back-edges annotated.

    Gates:
      a. Reachability — every node reachable from an entry node.
      b. Exit-node existence — unless exit_condition declared.
      c. Back-edge termination — every back-edge has an iteration cap.
    """
    node_ids = set(nodes_by_id)

    # --- (a) Reachability -------------------------------------------------
    # Determine entry nodes: declared ones win; otherwise nodes with no
    # incoming NON-BACK-EDGE. Back-edges can't be traversed on the first pass
    # (they only fire after a reset), so they don't count for reachability.
    if declared_entry_nodes:
        seeds = [n for n in declared_entry_nodes if n in node_ids]
    else:
        has_incoming = {e.to_node for e in edges if not e.is_back_edge}
        seeds = [n.id for n in nodes
                 if n.id not in has_incoming and not n.depends_on]

    # BFS forward over explicit edges using shared helper.
    reachable = bfs_reachable(edges, seeds, node_ids)

    unreachable = node_ids - reachable
    if unreachable:
        raise ValueError(
            f"Template validation: unreachable nodes (no path from any entry "
            f"node): {sorted(unreachable)}"
        )

    # --- (b) Exit-node existence -----------------------------------------
    if not exit_condition:
        has_outgoing = {e.from_node for e in edges}
        exit_nodes = [n.id for n in nodes
                      if n.id not in has_outgoing]
        if not exit_nodes:
            raise ValueError(
                "Template validation: graph has no exit node (no node lacks "
                "outgoing edges) and no 'exit_condition' declared — the "
                "workflow can never terminate."
            )

    # --- (c) Back-edge termination ---------------------------------------
    # In a cycle, at least ONE edge must have an iteration cap. We check per
    # SCC group: if no edge in the group has max_iterations or an iteration
    # condition, reject. This allows the forward edge (build→review) to lack
    # a cap as long as the reset edge (review→build) has one.
    back_edges = [e for e in edges if e.is_back_edge]
    # Group back-edges by their SCC (approximated by the set of node pairs)
    # Since all back-edges in the same SCC share the same cycle, we can check
    # that the union of their caps covers the cycle.
    for edge in back_edges:
        has_iter_cond = bool(edge.condition and _ITERATION_RE.search(edge.condition))
        if edge.max_iterations is not None or has_iter_cond:
            continue  # this edge has a cap — cycle is bounded
        # Check if a sibling edge in the same cycle has a cap
        siblings = [s for s in back_edges
                     if s.from_node == edge.to_node and s.to_node == edge.from_node]
        sibling_capped = any(
            s.max_iterations is not None
            or (s.condition and _ITERATION_RE.search(s.condition))
            for s in siblings
        )
        if not sibling_capped:
            raise ValueError(
                f"Template validation: back-edge {edge.from_node!r}→"
                f"{edge.to_node!r} has no iteration cap — set a "
                f"'max_iterations' field or a condition referencing "
                f"${{...iteration...}} on at least one edge in the cycle "
                f"to prevent infinite loops."
            )


@dataclass
class Workflow:
    """A declarative workflow definition."""
    id: str
    name: str
    description: str = ""
    trigger: Trigger | None = None
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    # Explicit entry nodes — bypasses the implicit "no-incoming-edge" entry
    # detection. A node listed here is considered reachable even if it has
    # incoming edges (or if no node has zero incoming edges, e.g. a pure cycle).
    declared_entry_nodes: list[str] = field(default_factory=list)
    # Explicit exit condition — if set, suppresses the "must have >=1 exit
    # node (no outgoing edges)" validation gate.
    exit_condition: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> Workflow:
        # Preserve TypeError for None input (data["id"] on None raises TypeError)
        wf_id = data["id"]

        # No-underscore invariant: workflow IDs must not contain "_".
        # The engine's self-trigger guard parses engine card idempotency keys
        # by splitting the instance segment on "_"
        # (["wf", <ts>, <wf.id chunks...>, <uuid>]); an underscore in the
        # workflow ID would break that parse and can cause infinite trigger
        # loops. Reject early at parse time.
        if "_" in wf_id:
            raise ValueError(
                f"Workflow id must not contain underscores (got {wf_id!r}); "
                "the self-trigger guard relies on this invariant."
            )

        trigger = None
        if "trigger" in data:
            t = data["trigger"]
            trigger = Trigger(source=t["source"], condition=t.get("condition", {}))

        nodes = []
        raw_nodes = data.get("nodes", [])
        if not isinstance(raw_nodes, list):
            raise TypeError(f"'nodes' must be a list, got {type(raw_nodes).__name__}")

        for n in raw_nodes:
            if not isinstance(n, dict):
                raise TypeError(f"Each node must be a dict, got {type(n).__name__}")
            if "id" not in n:
                raise KeyError("Node missing required field: 'id'")
            if "profile" not in n:
                raise KeyError("Node missing required field: 'profile'")

            inp = None
            if "input" in n and isinstance(n["input"], dict):
                inp = NodeInput(
                    schema=n["input"].get("schema", {}),
                    sources=n["input"].get("sources", {}),
                )
            out = None
            if "output" in n and isinstance(n["output"], dict):
                out = NodeOutput(schema=n["output"].get("schema", {}))

            deps = n.get("depends_on", [])
            if not isinstance(deps, list):
                raise TypeError(f"Node '{n['id']}': depends_on must be list, got {type(deps).__name__}")

            nodes.append(Node(
                id=n["id"],
                profile=n["profile"],
                skill=n.get("skill", ""),
                body_template=n.get("body_template", ""),
                title_template=n.get("title_template", ""),
                input=inp,
                output=out,
                card_mode=n.get("card_mode", "template"),
                depends_on=deps,
                condition=n.get("condition"),
                foreach=n.get("foreach"),
                type=n.get("type", "task"),
                workflow_ref=n.get("workflow_ref", ""),
                input_mapping=n.get("input_mapping", {}),
                output_mapping=n.get("output_mapping", {}),
                command=n.get("command", ""),
                wait_condition=n.get("wait_condition", ""),
            ))

        # Parse explicit edges if present
        edges = []
        raw_edges = data.get("edges", [])
        has_explicit_edges = isinstance(raw_edges, list) and len(raw_edges) > 0
        if isinstance(raw_edges, list):
            for e in raw_edges:
                if isinstance(e, dict) and "from" in e and "to" in e:
                    max_iter = e.get("max_iterations")
                    edges.append(Edge(
                        from_node=e["from"],
                        to_node=e["to"],
                        condition=e.get("condition"),
                        max_iterations=int(max_iter) if max_iter is not None else None,
                    ))

        # Back-edge detection: annotate each edge with is_back_edge based on
        # Tarjan SCC over the edge set. Zero cost for acyclic templates (every
        # SCC is a singleton → no edge marked).
        annotate_back_edges(edges, nodes)

        # Load-time structural validation (reachability, exit-node existence,
        # back-edge termination). Only enforced on templates that opt into the
        # explicit-edge graph model — legacy depends_on templates keep their
        # existing parse-time behavior (backward compatible).
        declared_entry_nodes = list(data.get("entry_nodes", []))
        exit_condition = data.get("exit_condition")
        if has_explicit_edges and nodes:
            nodes_by_id = {n.id: n for n in nodes}
            _validate_template_graph(
                nodes, edges, declared_entry_nodes, exit_condition, nodes_by_id
            )

        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            trigger=trigger,
            nodes=nodes,
            edges=edges,
            declared_entry_nodes=declared_entry_nodes,
            exit_condition=exit_condition,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> Workflow:
        data = json.loads(Path(path).read_text())
        return cls.from_dict(data)

    def get_node(self, node_id: str) -> Node | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def entry_nodes(self) -> list[Node]:
        """Nodes with no dependencies."""
        return [n for n in self.nodes if not n.depends_on]

    def to_mermaid(self) -> str:
        """Render the workflow as a mermaid graph.

        Node shapes encode type:
          [] = task, (()) = subworkflow, {{}} = foreach
        Node labels show id + profile.
        Trigger info appears as a comment above the graph.
        """
        lines = ["graph TD"]

        # Trigger info as comment
        if self.trigger:
            cond_str = ", ".join(f"{k}={v}" for k, v in self.trigger.condition.items())
            lines.insert(0, f"%% trigger: {self.trigger.source} ({cond_str})")

        for node in self.nodes:
            label = f"{node.id}\\n{node.profile}"
            if node.skill:
                label += f" [{node.skill}]"
            if node.type == "subworkflow":
                lines.append(f"    {node.id}(({label}))")
            elif node.type == "command":
                lines.append(f"    {node.id}[{label} ●]")  # square with dot marker
            elif node.type == "wait":
                lines.append(f"    {node.id}[/ {label} /]")  # parallelogram
            elif node.foreach:
                lines.append(f'    {node.id}{{{{{label}}}}}')
            else:
                lines.append(f"    {node.id}[{label}]")
        lines.append("")

        # Render edges: explicit edges take precedence, else implicit depends_on
        if self.edges:
            for edge in self.edges:
                edge_label = f"|{edge.condition}|" if edge.condition else ""
                lines.append(f"    {edge.from_node} -->{edge_label} {edge.to_node}")
        else:
            for node in self.nodes:
                for dep in node.depends_on:
                    edge_label = f"|{node.condition}|" if node.condition else ""
                    lines.append(f"    {dep} -->{edge_label} {node.id}")
        return "\n".join(lines)


def strip_template_var(expr: str) -> str:
    """Strip a ${...} template-variable wrapper, returning the inner key.

    "${nodes.plan.output.spec_path}" → "nodes.plan.output.spec_path"
    If the string isn't wrapped, returns it unchanged.
    """
    if expr.startswith("${") and expr.endswith("}"):
        return expr[2:-1]
    return expr


def resolve_template(template: str, context: dict) -> str:
    """Resolve ${variable} references in a template string.

    Supports dot-path resolution for dict values:
      ${item.slug} — if context has "item" = {"slug": "x"}, resolves to "x"

    Example: "Spec is at ${nodes.plan.output.spec_path}"
    With context = {"nodes.plan.output.spec_path": "/path/to/spec.md"}
    Returns: "Spec is at /path/to/spec.md"
    """
    result = template
    for key, value in context.items():
        if isinstance(value, dict):
            # Resolve dot-paths: ${key.field} → value["field"]
            for sub_key, sub_val in value.items():
                result = result.replace("${" + key + "." + sub_key + "}", str(sub_val))
            # Also resolve the whole dict as ${key} (string repr)
            result = result.replace("${" + key + "}", str(value))
        elif isinstance(value, list):
            # For lists of dicts, don't try to resolve — just string repr
            result = result.replace("${" + key + "}", str(value))
        else:
            result = result.replace("${" + key + "}", str(value))
    # Remove any unresolved variables
    result = re.sub(r"\$\{[^}]+\}", "", result)
    return result


def _evaluate_single_clause(clause: str, context: dict) -> bool:
    """Evaluate one atomic comparison clause (no AND/OR).

    Operators: == 'x', != 'x', exists, is empty, <, <=, >, >= (numeric-aware).
    Returns False on any unrecognized form (safe default).
    """
    # ${var} exists  (truthy check)
    m = re.match(r"^\s*\$\{(.+?)\}\s+exists\s*$", clause)
    if m:
        return bool(context.get(m.group(1)))

    # ${var} is empty  (falsy check)
    m = re.match(r"^\s*\$\{(.+?)\}\s+is empty\s*$", clause)
    if m:
        return not context.get(m.group(1))

    # ${var} == 'value'  (exact string equality)
    m = re.match(r"^\s*\$\{(.+?)\}\s*==\s*'(.+?)'\s*$", clause)
    if m:
        return str(context.get(m.group(1))) == m.group(2)

    # ${var} == value  (bare value: True/False/null/number/unquoted string)
    m = re.match(r"^\s*\$\{(.+?)\}\s*==\s*(\S+)\s*$", clause)
    if m:
        lhs = context.get(m.group(1))
        rhs_raw = m.group(2)
        # Boolean coercion: True/False/true/false
        if rhs_raw in ("True", "true"):
            return lhs is True or str(lhs).lower() == "true"
        if rhs_raw in ("False", "false"):
            return lhs is False or str(lhs).lower() == "false"
        # Null check
        if rhs_raw in ("null", "None"):
            return lhs is None
        # Fallback to string comparison
        return str(lhs) == rhs_raw

    # ${var} != 'value'  (exact string inequality)
    m = re.match(r"^\s*\$\{(.+?)\}\s*!=\s*'(.+?)'\s*$", clause)
    if m:
        return str(context.get(m.group(1))) != m.group(2)

    # ${var} != value  (bare value)
    m = re.match(r"^\s*\$\{(.+?)\}\s*!=\s*(\S+)\s*$", clause)
    if m:
        lhs = context.get(m.group(1))
        rhs_raw = m.group(2)
        if rhs_raw in ("True", "true"):
            return not (lhs is True or str(lhs).lower() == "true")
        if rhs_raw in ("False", "false"):
            return not (lhs is False or str(lhs).lower() == "false")
        if rhs_raw in ("null", "None"):
            return lhs is not None
        return str(lhs) != rhs_raw

    # Numeric comparisons: <, <=, >, >=
    # Right-hand side may be a bare number (e.g. ${x} < 3) or a quoted
    # string (e.g. ${x} <= '3'). Either is eligible for numeric coercion.
    m = re.match(r"^\s*\$\{(.+?)\}\s*(<=|>=|<|>)\s*(.+?)\s*$", clause)
    if m:
        var_path, op, rhs_raw = m.group(1), m.group(2), m.group(3)
        lhs_val = context.get(var_path)
        # Strip surrounding quotes from the RHS if present.
        rhs_raw = rhs_raw.strip()
        if len(rhs_raw) >= 2 and rhs_raw[0] in "'\"" and rhs_raw[-1] == rhs_raw[0]:
            rhs_raw = rhs_raw[1:-1]
        # Type coercion: attempt float() on both sides. If both succeed,
        # compare numerically; otherwise fall back to string comparison.
        # NB: lhs/rhs are always the SAME type (both float or both str),
        # so the comparison is type-safe at runtime even though the static
        # type is Any.
        lhs_str = "" if lhs_val is None else str(lhs_val)
        lhs: Any
        rhs: Any
        try:
            lhs = float(lhs_str)
            rhs = float(rhs_raw)
        except (TypeError, ValueError):
            lhs = lhs_str
            rhs = rhs_raw
        if op == "<":
            return lhs < rhs
        if op == "<=":
            return lhs <= rhs
        if op == ">":
            return lhs > rhs
        if op == ">=":
            return lhs >= rhs

    return False


def evaluate_condition(condition: str, context: dict) -> bool:
    """Evaluate a condition expression against the context.

    Grammar (no parentheses):
        condition := clause (OR clause)*
        clause    := atom (AND atom)*
        atom      := ${var} <op> <value>

    - ``AND`` binds tighter than ``OR`` (e.g. ``A AND B OR C AND D``
      groups as ``(A AND B) OR (C AND D)``).
    - Evaluation is left-to-right within a group; AND short-circuits on
      the first False atom, OR short-circuits on the first True group.
    - Atomic operators: ``== 'x'``, ``!= 'x'``, ``exists``, ``is empty``,
      ``<``, ``<=``, ``>``, ``>=``. Numeric operators attempt ``float()``
      coercion on both sides; if either fails they fall back to string
      comparison (never stringify-then-compare, which would make
      ``"10" < "3"`` True).
    - Unrecognized forms return False (safe default).
    """
    condition = condition.strip()
    if not condition:
        return False

    # OR groups: any group True → whole condition True.
    for or_group in condition.split(" OR "):
        or_group = or_group.strip()
        if not or_group:
            continue
        # AND clauses within a group: all must be True for the group.
        and_clauses = or_group.split(" AND ")
        group_true = True
        for clause in and_clauses:
            if not _evaluate_single_clause(clause.strip(), context):
                group_true = False
                break  # short-circuit AND
        if group_true:
            return True  # short-circuit OR
    return False
