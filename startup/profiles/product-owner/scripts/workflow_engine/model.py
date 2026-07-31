"""Workflow definition model — a workflow is a JSON file with nodes and edges."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json


@dataclass
class Trigger:
    """What starts this workflow."""
    source: str          # "card_completed" | "bead_ready" | "manual" | "scheduled"
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
    """A single step in the workflow."""
    id: str
    profile: str         # which agent profile runs this (e.g. "verifier")
    skill: str           # which skill to load (e.g. "adversarial-review")
    body_template: str   # card body template with ${} variables
    input: NodeInput | None = None
    output: NodeOutput | None = None
    card_mode: str = "template"  # "template" | "delegate" | "chain"
    depends_on: list[str] = field(default_factory=list)
    condition: str | None = None  # if set, node only runs when this evaluates true
    foreach: str | None = None     # if set, iterate over a list (e.g. "${nodes.tickets.output.beads}")


@dataclass
class Workflow:
    """A declarative workflow definition."""
    id: str
    name: str
    description: str = ""
    trigger: Trigger | None = None
    nodes: list[Node] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> Workflow:
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
                input=inp,
                output=out,
                card_mode=n.get("card_mode", "template"),
                depends_on=deps,
                condition=n.get("condition"),
                foreach=n.get("foreach"),
            ))

        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            trigger=trigger,
            nodes=nodes,
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
        """Render the workflow as a mermaid graph."""
        lines = ["graph TD"]
        for node in self.nodes:
            lines.append(f"    {node.id}[{node.id}]")
        lines.append("")
        for node in self.nodes:
            for dep in node.depends_on:
                label = f"|{node.condition}|" if node.condition else ""
                lines.append(f"    {dep} -->{label} {node.id}")
        return "\n".join(lines)


def resolve_template(template: str, context: dict) -> str:
    """Resolve ${variable} references in a template string.

    Example: "Spec is at ${nodes.plan.output.spec_path}"
    With context = {"nodes.plan.output.spec_path": "/path/to/spec.md"}
    Returns: "Spec is at /path/to/spec.md"
    """
    result = template
    for key, value in context.items():
        result = result.replace("${" + key + "}", str(value))
    # Remove any unresolved variables
    import re
    result = re.sub(r"\$\{[^}]+\}", "", result)
    return result


def evaluate_condition(condition: str, context: dict) -> bool:
    """Evaluate a simple condition expression against the context.

    Supports:
      - "${var} == 'value'"  (equality check)
      - "${var} != 'value'"  (inequality check)
      - "${var} exists"      (truthy check)
      - "${var} is empty"    (falsy check)
    """
    import re

    # ${var} exists
    m = re.match(r"\$\{(.+?)\}\s+exists", condition)
    if m:
        return bool(context.get(m.group(1)))

    # ${var} is empty
    m = re.match(r"\$\{(.+?)\}\s+is empty", condition)
    if m:
        return not context.get(m.group(1))

    # ${var} == 'value'
    m = re.match(r"\$\{(.+?)\}\s*==\s*'(.+?)'", condition)
    if m:
        return str(context.get(m.group(1))) == m.group(2)

    # ${var} != 'value'
    m = re.match(r"\$\{(.+?)\}\s*!=\s*'(.+?)'", condition)
    if m:
        return str(context.get(m.group(1))) != m.group(2)

    return False
