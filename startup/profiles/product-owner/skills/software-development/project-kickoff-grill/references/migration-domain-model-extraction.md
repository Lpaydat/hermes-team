# Migration: Extracting the Old Domain Model

When migrating an existing system, the spec is only as good as its understanding of the old data model. Pull the actual model definitions from source before writing the spec — never reconstruct from memory or guess.

## Technique: Fetch model files from GitHub

Use `gh api` to pull file contents directly from the old repo. The `--jq '.content'` extracts the base64-encoded content, which you then decode.

### Backend models (Python / Pydantic / Strawberry)

```bash
gh api repos/<owner>/<repo>/contents/<path>/models/product.py --jq '.content' | base64 -d
gh api repos/<owner>/<repo>/contents/<path>/models/order.py --jq '.content' | base64 -d
gh api repos/<owner>/<repo>/contents/<path>/models/order_item.py --jq '.content' | base64 -d
gh api repos/<owner>/<repo>/contents/<path>/models/transaction.py --jq '.content' | base64 -d
```

What to extract:
- **Field names and types** — the actual data shape
- **Enums** — status values, action types, unit types
- **Computed properties** — these become frontend logic, not stored fields
- **Validators** — business rules embedded in the model (e.g. keywords must be unique)
- **Nested structures** — if Order contains items[] and transactions[], these become separate tables in the new schema

### Frontend interfaces (TypeScript)

```bash
gh api repos/<owner>/<repo>/contents/<path>/interfaces/product.ts --jq '.content' | base64 -d
gh api repos/<owner>/<repo>/contents/<path>/interfaces/order.ts --jq '.content' | base64 -d
gh api repos/<owner>/<repo>/contents/<path>/enum/unitType.ts --jq '.content' | base64 -d
```

The frontend interfaces show the exact shape the UI expects — useful for verifying the new schema covers all fields the old UI relied on.

## Building the migration map

Create a table in the spec's Implementation Decisions section:

```
| Old field | New collection.field | Notes |
|-----------|---------------------|-------|
| Product.name | products.name | direct |
| Product.keywords (includes barcodes) | products.keywords | preserved |
| Order.items[] (nested) | order_items (separate table) | normalized |
| Order.transactions[] (nested) | transactions (separate table) | normalized |
| OrderItem.total_price (computed) | (computed in frontend) | not stored |
| Unit enum (dozen/pack/unit) | products.unit (free text) | un-locked from enum |
```

Key decisions to make explicit:
- **Nested arrays → separate tables.** Old MongoDB-style embedded documents become normalized collections in relational/SQLite storage.
- **Computed properties → frontend logic.** If the old model had `@property total_price`, it's calculated in the new frontend, not stored.
- **Enums → free text or enum.** Decide whether to keep strict enums or relax to free text with suggestions.
- **New fields.** Anything the new system adds that didn't exist before (e.g. `created_by`, `updated_at`, `device_id` for sync).

## What NOT to migrate

- **Session/auth state** — old auth tokens, sessions are throwaway.
- **Temporary/runtime data** — anything that was computed at runtime, not persisted.
- **Framework-specific fields** — MongoDB ObjectId internals, GraphQL resolver metadata.
- **New-domain entities with no old equivalent** — if the new system introduces a concept that didn't exist in the old system (e.g. customers, staff accounts, ledger entries), there is nothing to migrate. State this explicitly in the spec so the builder doesn't waste time looking for old data. If there's real-world data (e.g. a paper ledger of existing debt), call it out as a manual entry task for the store owner, not a migration script.

## Verifying the migration map

After building the table, do a coverage check:
1. List every field in every old model.
2. Mark each as: migrated, computed (frontend), dropped (with reason), or renamed.
3. Every field must have a disposition. No orphans.

This table is the contract between the spec and the migration script. The builder implements the script against this map; the verifier checks that every field has a home.
