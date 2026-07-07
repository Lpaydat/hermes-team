# Beads Issue JSON Schema (bd list --json)

Discovered by inspecting `bd list --json` on a live project (bd v1.0.4).
Fields may vary slightly by beads version — always sanity-check on first use.

## Key fields for hygiene validation

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Issue ID, e.g. `tau-o4cc` or `proj-5c6` (prefix-`hash`) |
| `title` | string | Full title. May contain `[epic]`, `[bug]`, `[T2]` etc. as convention, but don't rely on these for typing. |
| `status` | string | `open`, `in_progress`, `blocked`, `closed`, `done`, `deferred`. Check against `closed`/`done` to filter active issues. |
| `priority` | int | 1-4 (P1 highest). |
| `issue_type` | string | **THIS is the type field**, not `type`. Values seen: `task`, `epic`, `bug`. Use this for epic detection. |
| `assignee` | string | Who is assigned. |
| `owner` | string | Project owner / beads owner. |
| `created_at` | ISO 8601 string | e.g. `2026-06-30T14:42:44Z`. |
| `updated_at` | ISO 8601 string | e.g. `2026-06-30T14:43:01Z`. **Use this for stale detection** (not `mtime`). |
| `started_at` | ISO 8601 string | When work was started (if `in_progress`). |
| `parent` | string or null | Parent issue ID for hierarchical children. Null/missing = top-level issue. |
| `labels` | array of strings | Issue labels/tags. Empty array = unlabeled. |
| `dependency_count` | int | Number of issues this one depends on. |
| `dependent_count` | int | Number of issues that depend on this one. |
| `comment_count` | int | Number of comments. Use as a proxy for activity before deferring. |

## Common pitfalls

- **`type` vs `issue_type`**: The JSON field is `issue_type`, not `type`. A scanner checking `issue.get("type") == "epic"` will miss all epics. Always use `issue_type`.
- **Title-based epic detection**: Some issues have `[epic]` in the title AND `issue_type: "epic"`. But not all. Check `issue_type` first, fall back to title prefix.
- **Timestamps are UTC with `Z` suffix**: `datetime.fromisoformat()` in Python 3.11+ handles `Z` directly, but for broader compat replace `Z` with `+00:00` before parsing.
- **Labels may be absent**: The `labels` key may exist as an empty array `[]` or be missing entirely. Use `.get("labels", [])` defensively.

## Shared database detection

Worktrees and clones of the same repo share the same beads Dolt database. To detect:

```bash
git -C <dir_a> remote -v   # Check the fetch/push URL
git -C <dir_b> remote -v   # If same URL → same beads DB → only scan one
```
