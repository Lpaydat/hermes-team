# Karpathy's Autoresearch Pattern — Implications for R&D/Exploration

## Source
GitHub: karpathy/autoresearch (92.5k stars). An AI agent autonomously runs ML training experiments overnight — modify code, train 5 minutes, check metric, keep or discard, repeat forever.

## The core pattern

The agent runs a **keep-or-discard loop**:
1. Modify code (try an experimental idea)
2. Run it (fixed time budget)
3. Check the metric (did val_bpb improve?)
4. **Keep** (git commit) or **discard** (git reset)
5. Repeat — NEVER STOP, never ask permission

The `program.md` file is the "skill" that programs this loop. It's deliberately minimal — the agent is told what it CAN edit, what it CANNOT, the metric, and the loop. Then it runs autonomously.

## What's transferable to our R&D phase

The insight isn't ML-specific — it's the **autonomous experiment loop as a way to explore solution spaces.** Applied to software R&D:

```
Problem arrives
  → fan out N parallel spike prototypes (different approaches)
  → each spike runs autonomously (build, test, measure against success criteria)
  → converge: compare results, keep the winner, discard the rest
  → hand the winner to the architect for production design
```

This combines:
- **Toyota's set-based design** — explore multiple solutions in parallel, narrow gradually
- **Ousterhout's "Design It Twice"** — deliberately produce 2-3 designs before choosing
- **Karpathy's keep-or-discard** — let empirical results decide, not committee

## Where it fits in the pipeline

```
PO (grill → spec) → R&D/exploration (fan out spikes) → architect (design informed by dossier) → tech-lead (build)
```

R&D goes BEFORE architect — universally confirmed by Google (alternatives considered), Amazon (Working Backwards), Toyota (set-based), YC (build-measure-learn). You don't design a car before researching what problems you're solving.

## Implementation note

This doesn't need a new profile. The capabilities exist (builder prototypes, researcher deep-dives, scout scans). The missing piece is orchestration — an `exploration-gate` skill that the PO loads conditionally. Same pattern as `architect-gate`. One skill + one routing update.

The Karpathy pattern reinforces that R&D should be **autonomous** — the PO sets the success criteria and approach briefs, then the spikes run without intervention. The user wakes up to results.
