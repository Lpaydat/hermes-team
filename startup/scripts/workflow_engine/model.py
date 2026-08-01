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


@dataclass
class Workflow:
    """A declarative workflow definition."""
    id: str
    name: str
    description: str = ""
    trigger: Trigger | None = None
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

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
        if isinstance(raw_edges, list):
            for e in raw_edges:
                if isinstance(e, dict) and "from" in e and "to" in e:
                    edges.append(Edge(
                        from_node=e["from"],
                        to_node=e["to"],
                        condition=e.get("condition"),
                    ))

        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            trigger=trigger,
            nodes=nodes,
            edges=edges,
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

    # ${var} != 'value'  (exact string inequality)
    m = re.match(r"^\s*\$\{(.+?)\}\s*!=\s*'(.+?)'\s*$", clause)
    if m:
        return str(context.get(m.group(1))) != m.group(2)

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
