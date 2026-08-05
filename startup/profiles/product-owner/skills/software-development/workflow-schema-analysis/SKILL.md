---
name: workflow-schema-analysis
description: "Analyze, document, and compare workflow/graph schema formats across systems — field structures, persistence models, versioning schemes, and dispatch semantics. Produces complete schema documentation and unified-format proposals. Use when asked to 'document the graph JSON', 'compare workflow formats', 'analyze the schema structure', 'how are graphs persisted', 'propose a unified format', or when migrating between workflow engines. Knows the nginbot-api IGraphSchema format and the Hermes template format side-by-side."
triggers:
  - document graph schema
  - analyze workflow format
  - compare schema formats
  - unified workflow format
  - graph JSON structure
  - workflow schema fields
  - how are graphs persisted
  - graph versioning scheme
  - migrate workflow format
---

# Workflow Schema Analysis

Analyze, document, and compare the JSON schema formats that define workflow graphs. This skill covers the **technique** (what to read, in what order, to fully understand a format) and holds **reference knowledge** for the two formats most relevant to this workspace: Hermes templates and nginbot-api's IGraphSchema.

## When to load

- "Document the complete graph/workflow JSON schema"
- "How are graphs persisted? What tables/columns?"
- "How are graph versions managed?"
- "Compare this format against Hermes templates"
- "What would a unified format look like?"
- Migrating between workflow engines or adopting a new one
- Designing a workflow format from scratch

## Analysis technique — read these in parallel

To fully understand any workflow graph format, read these layers in one batch (they're independent):

1. **Type definitions** — the TypeScript/Python types that define the schema shape (`types.ts`, `types.py`, `model.py`). This gives you every field and its type.
2. **Validation logic** — what's enforced (`validation.ts`, validators, load-time checks). Tells you which fields are load-bearing vs cosmetic.
3. **Serialization** — how the schema is exported/imported (`SchemaSerializer`, `export()`, `from_dict()`). Reveals the canonical on-disk shape.
4. **Persistence layer** — repository classes + DB type definitions (`graph.repo.ts`, `db/types.ts`, migration files). Shows how schemas are stored and addressed.
5. **Versioning logic** — how versions are computed (`generateVersion`, `xxhash`, `object-hash`). Often a hash of a specific subset of fields.
6. **GraphQL mutations / API layer** — how schemas are created via the API (if applicable).

**Pitfall:** Don't read just the types — the types show shape but not semantics. The versioning logic and persistence layer reveal *which fields matter* (e.g., nginbot versions only the I/O contract, not internal wiring).

## Producing the deliverable

A complete schema analysis document should cover, in order:

1. **Complete schema structure** — every field, every type, with a table
2. **Full working example** — not fragments; a complete graph that does something real
3. **Persistence model** — tables, columns, how schemas are addressed (composite PK? immutable?)
4. **Versioning** — what's hashed, what algorithm, what the version means semantically
5. **Side-by-side comparison** — if comparing formats, express the SAME workflow in both
6. **Unified proposal** — if asked, what fields to add/remove to unify, with a complete JSON Schema

## Reference: the two formats

For detailed field-by-field comparison, node type tables, persistence columns, versioning code, and the unified schema proposal, see:

- [`references/graph-schema-format-comparison.md`](references/graph-schema-format-comparison.md) — nginbot-api IGraphSchema vs Hermes template: structure, persistence, versioning, readability vs expressiveness verdict, and the 8 additions needed to unify them.

**Headline differences:**
- Hermes: flat node array + flat edge array, stateless nodes, `${var}` data flow, first-class triggers/profiles. More readable.
- nginbot-api: node object map with embedded edges, shared mutable store, typed data flow with `source` overrides, no dispatch concept in schema. More expressive/rigorous, ~2x more verbose.
- Unifying requires adding a `dispatch` block (trigger, idempotency, entry/exit) and per-node `profile`/`skill`/`cardMode`/`foreach` to the nginbot base.

## Pitfalls

- **Don't confuse content hash with contract hash.** nginbot's version is an I/O *contract* hash (same inputs/outputs = same version even if internal wiring differs). This is deliberate — callers don't need to update references when internals change. Don't "fix" this by hashing the full schema.
- **Edges location matters for readability.** A flat edge array (Hermes) lets you see topology at a glance. Embedded per-node edges (nginbot) scatter topology — always include a separate topology summary when documenting nginbot-style formats.
- **Resources vs profiles.** nginbot resolves agents from a resource registry (`Set<ResourceKey>`); Hermes inlines `profile`/`skill` per node. When comparing, don't assume they're equivalent — nginbot's indirection enables version-pinned resource resolution.
