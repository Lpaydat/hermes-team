# Mining Claude Code Session History

When the user references work that "Claude Code did" or "was already built/tested",
find the Claude Code conversation history to recover the original context.

## Where Claude Code stores conversations

```
~/.claude/projects/<encoded-project-path>/<session-uuid>.jsonl
```

The project path is encoded by replacing `/` with `-` and prepending `-`:
```
/home/lpaydat/.hermes-teams/ → -home-lpaydat--hermes-teams/
```

Multiple session files may exist per project. File size indicates depth:
- `< 1 MB` — short session, probably not the one
- `1–3 MB` — medium session
- `3+ MB` — major session, likely where the work happened

## Parsing JSONL sessions

Each line is a JSON object. Key types:

| `type` | Meaning |
|--------|---------|
| `user` | User message (in `.message.content`) |
| `assistant` | Claude's response (in `.message.content`) |
| `attachment` | File/command attachment |
| `file-history-snapshot` | Checkpoint |

Content extraction:
```python
import json

with open(session_path) as f:
    for line in f:
        entry = json.loads(line)
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", {})
        content = msg.get("content", "")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "".join(
                p["text"] for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
```

**Skip** entries starting with `<command-name>`, `<local-command-caveat>`, or
`<task-notification>` — those are UI/command artifacts, not user intent.

## Finding the right session

### By keyword frequency

Read the whole file as text and count keyword hits:
```python
content = open(session_path).read()
for kw in ["architect", "gate", "ADR", "test3", "edge case"]:
    print(f"  {kw}: {content.lower().count(kw.lower())}")
```

High hit counts on domain-specific terms (board names, skill names, tier labels)
identify the session where that work happened.

### By user message scan

Extract only `type=user` messages, filter for domain keywords, and read the
first 400 chars of each match. This reveals the user's intent flow.

### By task-notification scan

`<task-notification>` entries show subagent completions:
```
<summary>Agent "Implement 1y1.1 architect profile" finished</summary>
<summary>Agent "Implement 1y1.4 architecture gate" finished</summary>
```

These map directly to the pipeline beads that built the feature.

## Pitfall: first message is often empty

The first few lines of a JSONL are often `mode`, `file-history-snapshot`, or
`attachment` entries with no readable content. Skip to the first `type=user`
entry with actual text content.
