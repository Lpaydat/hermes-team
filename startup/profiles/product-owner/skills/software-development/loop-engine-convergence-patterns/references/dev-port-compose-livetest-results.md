# dev-port + dev-compose Livetest Results (2026-08-10)

First live test of both new workflows, run in parallel.

## Test Setup

- **port-csv2md**: Port lzakharov/csv2md (Python, ~200 LOC, zero deps) to Rust. 4 user stories.
- **compose-dataviz**: Combine json-to-csv (~51 SLOC) + termchart (~45 SLOC) into a terminal data visualizer in Rust. 4 user stories.

Both ref repos cloned to `~/workspace/refs/`.

## Coverage Map Results (THE KEY TEST)

### port-csv2md — architect output:
```json
{
  "verdict": "stamped",
  "ref_repos": ["/home/lpaydat/workspace/refs/csv2md"],
  "coverage": {"covered": 3, "partial": 1, "gap": 0, "total": 4}
}
```
Correct: 3 stories fully covered by the Python ref, 1 partial (stdin handled differently). Zero gaps — the ref covers all capabilities. This is the expected result for a port.

### compose-dataviz — architect output:
```json
{
  "verdict": "stamped",
  "ref_repos": ["/home/lpaydat/workspace/refs/json-to-csv", "/home/lpaydat/workspace/refs/termchart"],
  "coverage": {"covered": 3, "partial": 0, "gap": 1, "total": 4},
  "source_map": {
    "1. chart data.csv": "termchart",
    "2. chart data.json --field price": "json-to-csv + termchart",
    "3. --width --height": "termchart",
    "4. Auto-detect numeric columns": "gap (new)"
  }
}
```
Correct: source_map attributes each story to the RIGHT ref repo. The integration story (auto-detect numeric columns) correctly identified as a gap. This proves the compose workflow's Source column works.

## Ticket Decomposition Results

### port-csv2md — all PORT tickets (zero gaps = zero BUILD tickets):
- `[ticket-01] Port: CSV file to Markdown on stdout`
- `[ticket-02] Port: Custom delimiter`
- `[ticket-03] Port: Global alignment`
- `[ticket-04] Port: Stdin input`

### compose-dataviz — 2 PORT + 1 BUILD (correct gap detection):
- `[ticket-01] Port from termchart: chart data.csv` — PORT, correct source
- `[ticket-02] Port from json-to-csv: chart data.json --field` — PORT, correct source
- `[ticket-03] Auto-detect numeric columns` — BUILD (no "Port from" prefix, no source ref)

## Workflow Instance Completion

Both dev-port and dev-compose instances completed cleanly (status=completed). No stuck instances. The downstream pipeline (tech-lead-execute, milestone-gate) fires identically to dev-dispatch — proving the shared pipeline design works.

## Code Quality Issues Found (Manual Testing)

Manual binary testing found bugs that unit tests missed:

### port-csv2md:
- `--alignment center` produces no visible change — separator row stays `| - |` instead of `| :---: |`
- 1 integration test failing (cli_alignment_center_emits_centered_separators)

### compose-dataviz:
- JSON chart path broken — can't find numeric values in arrays (`{"prices": [10, 20, 30]}` → error)
- CSV chart renders upside down (high values at top)

These bugs exist because QA hadn't completed yet at time of testing. The key question for future runs: does QA actually RUN the binary with real input, or just check "tests pass"?

## Naming Decision

User decided: `[port]` for all single-repo work (migration/translation/extraction), `[compose]` for multi-repo combining. Not separate prefixes per sub-type — the coverage map handles the nuance.

## What Worked

1. Coverage map concept — architect correctly analyzed ref repos and mapped stories
2. Source column in compose — correctly identified which ref covers which story
3. PORT vs BUILD ticket naming — "Port from <ref-name>" prefix clearly identifies provenance
4. Shared downstream pipeline — zero new code needed for tech-lead-execute/milestone-gate integration
5. Both workflows completed cleanly (no stuck instances)

## What Needs Attention

1. QA binary testing gap — unit tests pass but the binary has real bugs. QA must exercise the actual CLI with real input.
2. Blocked cards from agent crashes still occur (consecutive_failures hitting max-retries). The cross-profile plugin fix (Pattern 22) eliminated the loops-engineering crash class, but other crash causes remain.
