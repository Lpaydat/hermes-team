## H — G + exploration[] schema field

### The problem G couldn't solve

G proved schema enforcement works for evidence depth (verdicts[]=9/10, checks[]=9/10).
But G missed the identical stale-label bug E caught. The structured format
suppressed exploratory behavior — QA checked .driver/ docs for existence
("docs created with discovery content") but never inspected their content.

### The fix: exploration[] as required schema field

H adds `exploration[]` to qa-quick's output schema as a required field:

```json
"exploration": {
  "type": "array",
  "items": {
    "type": "object",
    "required": ["probe", "result", "finding"],
    "properties": {
      "probe": {"type": "string"},
      "result": {"type": "string"},
      "finding": {"type": "string"}
    }
  }
}
```

The body instructs: "For EVERY file in the merge delta (run `git diff --name-only`
to get the list), inspect its CONTENT, not just its existence."

### Result

H's exploration[] produced 3 probes:
1. "inspected .driver/*.md content" → "found stale QA-AB-A / repo-a labels"
   → finding: "Note (P4) -> filed as t_0a9d8e1c"
2. "checked for hardcoded paths" → "clean"
3. "verified no hidden entrypoints" → "clean"

H filed a real finding card (t_0a9d8e1c) — the same bug G missed.

### Three-round proof: F → G → H

| Version | Approach | Evidence | Security | Exploration | Findings |
|---------|----------|----------|----------|-------------|----------|
| F | Body text (structured table) | 3/10 (ignored) | 2/10 (ignored) | Suppressed | 0 (false neg) |
| G | Schema: verdicts[] + checks[] | 9/10 | 9/10 | Suppressed | 0 (false neg) |
| H | Schema: verdicts[] + checks[] + exploration[] | 9/10 | 9/10 | Enforced | 1 (real) |

Lesson: schema enforcement must cover ALL three axes — evidence, security,
exploration. Enforcing evidence and security without exploration creates
a completeness trap: the agent fills the required fields, declares done,
and skips the open-ended discovery that catches real bugs.
