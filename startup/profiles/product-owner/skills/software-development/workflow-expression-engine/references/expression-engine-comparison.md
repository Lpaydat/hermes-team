# Expression Engine: Hermes vs nginbot-api

> Comparative analysis from a side-by-side read of Hermes `model.py` (`resolve_template`, `_evaluate_single_clause`, `evaluate_condition`) and nginbot-api (`ExpressionProcessor.ts`, `sourceExtractor.ts`, `stringExtractors.ts`, `state.ts`, `nodes/base.ts`, `outgoingEdges.ts`).

## Hermes: implementation facts

- **There is NO `TEMPLATE_RE` constant.** `resolve_template()` (model.py ~L537) uses `str.replace()` over context keys, dict values get one-level dot-path expansion (`${key.sub}` → `value["sub"]`), and unresolved `${...}` are stripped via `re.sub(r"\$\{[^}]+\}", "")`.
- Conditions (`evaluate_condition`, ~L657) are parsed by splitting on `" OR "` then `" AND "` — no regex tokenizer, no parentheses, no arithmetic. Unknown forms → `False` (safe default).
- Variable patterns are purely conventional: the resolver matches whatever `${...}` string is present against a flat context dict. Namespaces (`nodes.`, `trigger.`, `item`, `item_index`) are produced by the runtime filling that dict, not by the resolver recognizing them.

### Complete Hermes variable inventory

| Pattern | Source |
|---|---|
| `${nodes.<id>.output.<field>}` | completed node output |
| `${nodes.<id>.output.<field>.<sub>}` | nested dot-path into output dict |
| `${trigger.<key>}` | trigger context (card_id, task, build_id, metadata.*) |
| `${item}` | whole current foreach item |
| `${item.<field>}` | dot-path field of current foreach item |
| `${item_index}` | integer foreach iteration index |
| `${<any.context.key>}` | generic escape hatch — any key in the resolution dict |

### Complete condition operator set

`== 'x'`, `== bare` (True/False/true/false/null/None coercion), `!= 'x'`, `!= bare`, `exists`, `is empty`, `<`, `<=`, `>`, `>=` (numeric via `float()` with string fallback). Boolean composition: `AND` (binds tighter) and `OR`, short-circuit, left-to-right. **No parentheses, no arithmetic, no functions.**

## nginbot-api: two cooperating mechanisms

### 1. Declarative source directives (`sourceExtractor.ts`)

Regex: `/^(?:(\w+|#):)?(store|node|input)(?::((?:#|\w)[\w.]*))?$/`

| Directive | Meaning |
|---|---|
| `store:<path>` | mutable graph-level store (persists across nodes) |
| `node:<Id>.output.<path>` | named node output, dot-pathed |
| `input:<name>` | graph-level input parameter |
| `#:node` or `node:#.output.<path>` | `#` = previous step's node id (runtime-resolved) |
| `<srcNode>:<type>:<path>` | source-node-qualified (multi-state graphs) |

Shorthand: omit path for `store`/`input` → defaults to `[<key>]`; omit for `node` → defaults to `[<prevNodeId>]`.

### 2. Expression engine (`expr-eval`)

Used in `ConditionalRoute.condition` and `storeUpdater`. Full math (`+ - * / % ^`), boolean (`&& || !` / `and or not`), **parentheses**, and library functions. Reserved symbols: `$` (list item, → `_item`), `#` (default state), `_` (prev value / reduce accumulator).

Separate `{param}` (single curly, no `$`) templates for prompt/description substitution in TASK nodes.

## Forward mapping (Hermes → nginbot): ✅ with two gaps

| Hermes | nginbot | Status |
|---|---|---|
| `${nodes.X.output.Y}` | `node:X.output.Y` | ✅ direct |
| `${trigger.Z}` | `input:Z` (if wired as graph input) | ✅ needs convention |
| `${item}` | `$` in map expr | ✅ |
| `${item.field}` | `$` + field projection in map | ⚠️ partial — `$` is scalar in expr-eval |
| `${item_index}` | — | ❌ **gap: no loop index var** |
| all comparison ops | expr-eval native | ✅ superset |
| `exists` / `is empty` | `var != null` / `var == ''` | ✅ approximable |
| lenient missing-var | nginbot throws on undefined | ⚠️ policy mismatch |

## Reverse mapping (nginbot → Hermes): ❌ several gaps

nginbot features Hermes has NO analogue for: **mutable store**, **arithmetic**, **parentheses in conditions**, **reduce/prev-value**, **multi-state graphs**, **storeUpdater write-back**. Hermes conditions cannot express `(A OR B) AND C`.

**Conclusion:** nginbot is a strict superset of Hermes's condition power. Hermes cannot host nginbot expressions without substantial new code.

## Merged syntax proposal (if combining both)

Two layers over one namespace:

**Layer 1 — declarative source bindings** (nginbot `inputSchema` model, unchanged).

**Layer 2 — inline `${...}` references** resolving against the same namespace:

| Unified form | Resolves to |
|---|---|
| `${nodes.plan.output.spec_path}` | named node output |
| `${nodes.#.output.verdict}` | previous node output |
| `${input.build_id}` / `${trigger.card_id}` (alias) | graph input |
| `${store.total}` | mutable store |
| `${item}` / `${item.slug}` / `${item_index}` | foreach context |
| `${env.VAR}` | process env (new namespace) |

Desugar `${path} op rhs` into a bound var + feed the scope to `expr-eval` → gains parens/arithmetic for free while keeping the familiar `${...}` surface. Add a compiled `TEMPLATE_RE = re.compile(r"\$\{([^}]+)\}")` (Hermes currently lacks this).

**Migration prerequisites:** (1) add `${item_index}`/`$_index` to nginbot; (2) wire trigger context as graph inputs; (3) pick missing-var policy (lenient for templates, strict for conditions).

Full session artifact with worked examples: `startup/scripts/workflow_engine/EXPRESSION_ENGINE_COMPARISON.md`.
