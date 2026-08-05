# Expression Engine Comparison: Hermes vs nginbot-api

> **Question under test:** Can nginbot-api's expression engine replace Hermes's condition evaluator?

**TL;DR — Yes, with one extension.** nginbot's engine is strictly more powerful
(math expressions via `expr-eval`, declarative source directives, store mutation,
list-item iteration). The only Hermes pattern it lacks out-of-the-box is a
first-class `${trigger.*}` channel — but that maps cleanly onto nginbot's
`input:` source (graph-level inputs). A merged syntax that keeps Hermes's
familiar `${...}` template form *and* nginbot's declarative `source:` bindings
is proposed in §5.

---

## 1. Hermes variable patterns (complete list)

Source: `model.py` — `resolve_template()` (L537), `_evaluate_single_clause()`
(L565), `evaluate_condition()` (L657), `strip_template_var()` (L526), and usage
across `runtime.py`.

There is **no `TEMPLATE_RE` constant** — Hermes uses ad-hoc `str.replace()` and
`re.sub(r"\$\{[^}]+\}", "")` rather than a compiled matcher. All variables are
`${...}` (dollar-brace).

### 1a. Template variables (`resolve_template`)

| Pattern | Meaning | Example |
|---|---|---|
| `${nodes.<id>.output.<field>}` | Output field of a completed node | `${nodes.plan.output.spec_path}` |
| `${nodes.<id>.output.<field>.<sub>}` | Dot-path into a nested output dict | `${nodes.check.output.metadata.verdict}` |
| `${trigger.<key>}` | Value from the workflow trigger context (card_id, task, build_id, metadata.*) | `${trigger.card_id}` |
| `${item}` | The current item in a `foreach` iteration (whole value) | `${item}` |
| `${item.<field>}` | A field of the current foreach item (dot-path) | `${item.slug}` |
| `${item_index}` | Integer index of the current foreach iteration | `${item_index}` |
| `${<any.context.key>}` | Any other key present in the resolution context dict (generic escape hatch) | `${spec_path}` |

Resolution semantics:
- `str.replace()` over context keys; dict values get dot-path expansion
  (`${key.sub}` → `value["sub"]`); unresolved `${...}` are stripped to `""`.
- Lists of dicts are stringified wholesale (no per-element pathing inside `resolve_template`).

### 1b. Condition atoms (`_evaluate_single_clause`)

Every atom is exactly `${var} <op> <rhs>`. The **same** variable patterns from
§1a are reused inside `${...}`. Operators:

| Operator | Form | Notes |
|---|---|---|
| `==` | `${var} == 'x'` or `${var} == bare` | String eq; bare supports `True`/`False`/`true`/`false`/`null`/`None` coercion |
| `!=` | `${var} != 'x'` or `${var} != bare` | Inverse |
| `exists` | `${var} exists` | Truthy check |
| `is empty` | `${var} is empty` | Falsy check |
| `<` `<=` `>` `>=` | `${var} < 3` or `${var} <= '3'` | Numeric-aware: tries `float()` on both sides, falls back to string |

### 1c. Boolean composition (`evaluate_condition`)

```
condition := clause ( OR  clause)*
clause    := atom  ( AND atom )*
```
- `AND` binds tighter than `OR`. Left-to-right, short-circuits.
- **No parentheses, no arithmetic, no string functions.** Pure boolean over
  atomic comparisons. Unknown forms → `False` (safe default).

---

## 2. nginbot-api source directives & expression patterns (complete list)

nginbot has **two distinct, cooperating mechanisms**:

### 2a. Declarative source directives — `sourceExtractor.ts`

Regex: `/^(?:(\w+|#):)?(store|node|input)(?::((?:#|\w)[\w.]*))?$/`

Used in a node's `inputSchema.properties.<key>.source` string. Three source
types (`ParamSourceType = 'store' | 'node' | 'input'`):

| Directive | Meaning | Example |
|---|---|---|
| `store:<path>` | Read from the graph-level mutable store (persists across nodes) | `store:totalCount` |
| `store:<dotted.path>` | Dot-path into store | `store:user.profile.name` |
| `node:<Id>.output.<path>` | Output (or sub-field) of a named node | `node:planId.output.spec_path` |
| `input:<name>` | Graph-level input parameter | `input:buildId` |
| `#:node` / `node:#.output.<path>` | `#` = previous step's node id (resolves at runtime via `prevStepId`) | `node:#.output.verdict` |
| `<srcType>:<nodeName>:<path>` | Explicit source-node qualifier (for composite/multi-state inputs) | `A:store:field` |

**Shorthand behaviors** (from `state.ts` `resolvePath`, L289):
- Omit the path for `store`/`input` → defaults to `[<key>]` (the property name itself).
- Omit the path for `node` → defaults to `[<prevNodeId>]` (whole previous output).
- `#` anywhere in a node path segment is rewritten to `prevStepId`.

### 2b. Expression engine — `expr-eval` (via `stringExtractors.ts` + `base.ts`)

Used in **conditions** (`ConditionalRoute.condition`) and **store updaters**
(`storeUpdater` expressions). Parsed by the `expr-eval` Parser, evaluated against
an `ExpressionScope = Record<string, string | number>`.

Three reserved symbols (`constants.ts`):

| Symbol | Constant | Role |
|---|---|---|
| `$` | `EXPR_LIST_ITEM_SYM` | Current list item in a `map`/reduce expression. Rewritten to `_item` before parsing, then excluded from the exported param set. |
| `#` | `EXPR_DEFAULT_STATE_SYM` | Default/previous state reference (used in composite multi-state graphs). |
| `_` | `EXPR_PREV_VALUE_SYM` | Previous value (for reduce-style accumulators). Reserved; cannot be a schema property name. |

Expression examples (full math + boolean logic, **with parentheses**):
```ts
"verdict == 'PASS'"                              // simple eq
"score > 0.5 && verdict == 'PASS'"               // AND
"score > 0.8 || (verdict == 'PASS' && retries < 3)"  // OR + parens
"count + 1"                                       // arithmetic (store updater)
"$ * 2"                                           // list item in map
```

### 2c. Template parameters — `extractTemplateParams`

Separate from expressions: `{param}` (**single** curly braces, no `$`) for
prompt/description templating in TASK nodes. Extracted via `/{([^{}]+)}/g`.

---

## 3. Can every Hermes pattern be expressed in nginbot? (forward mapping)

| Hermes pattern | nginbot equivalent | Notes |
|---|---|---|
| `${nodes.plan.output.spec_path}` | source: `node:plan.output.spec_path` (declarative); or expr var `spec_path` bound via that source | ✅ Direct |
| `${nodes.check.output.metadata.verdict}` (nested) | source: `node:check.output.metadata.verdict` | ✅ Dot-path supported by `getNodeOutput` |
| `${trigger.card_id}` | source: `input:card_id` (graph input) | ✅ if the trigger payload is passed as graph input. **Requires a wiring convention** — see §5. |
| `${trigger.Z}` (whole trigger dict) | source: `input:trigger` then dot-path, or bind the whole object | ✅ |
| `${item}` (foreach whole item) | expr symbol `$` (`EXPR_LIST_ITEM_SYM`) inside a `map` expression | ✅ — but only inside map/lambda context, not as a free template var |
| `${item.slug}` (foreach field) | `$` + field access in expr-eval (e.g. `$.slug` if supported, else bind via map) | ⚠️ Partial — expr-eval's `$` is a scalar; field access needs the map to project fields, or a source directive |
| `${item_index}` | Not directly exposed | ❌ **Gap.** nginbot's array/map iteration doesn't surface an index var. Needs an extension (e.g. `$_index`). |
| `${<context.key>}` (generic) | source: `input:<key>` or `store:<key>` | ✅ |
| Condition `==`, `!=`, `<`, `<=`, `>`, `>=` | expr-eval native operators | ✅ Superset (expr-eval has `and/or/not/+/-/*///%/^`) |
| Condition `exists` | expr `var != null` or `var != ''` (nginbot scope is `string|number`) | ✅ approximable; nginbot throws on undefined scope vars rather than treating as falsy |
| Condition `is empty` | expr `var == '' or var == 0` | ✅ approximable |
| `AND` / `OR` boolean composition | expr-eval `&&` / `||` / `and` / `or`, **with parentheses** | ✅ Strictly more capable |
| foreach over `${nodes.X.output.list}` | nginbot `map` over a source bound to that list + `$` item symbol | ✅ Different shape, same semantics |

**Gaps for forward migration:**
1. **`${item_index}`** — nginbot has no loop-index variable. Add `$_index` (or
   `_index`) alongside `$`.
2. **`${item.field}` as a free template token** — nginbot confines `$` to
   `map` expressions. To use item fields in a prompt template, either (a) project
   them via a `storeUpdater` into named vars first, or (b) extend template
   substitution to recognise `$` paths.
3. **Falsy-on-missing semantics** — Hermes silently treats missing vars as
   empty/false; nginbot's `expr-eval` throws on undefined scope members and
   `sourceExtractor` throws on missing paths. A migration must either pre-populate
   defaults or wrap evaluation in try/catch.

---

## 4. Can every nginbot expression be expressed in Hermes? (reverse mapping)

| nginbot feature | Hermes equivalent | Verdict |
|---|---|---|
| `store:<path>` (mutable, cross-node) | No concept of a mutable store. Closest: `${nodes.<producer>.output.<field>}` reads a prior node's output, but nothing writes a shared bag. | ❌ **Gap.** Hermes has no store. Would need a dedicated "store" pseudo-node or a new `${store.X}` namespace. |
| `input:<name>` (graph inputs) | `${trigger.<name>}` covers trigger-carried inputs. Graph inputs not originating from a trigger: no equivalent. | ⚠️ Partial — only if all inputs come through the trigger. |
| `node:<Id>.output.<path>` | `${nodes.<Id>.output.<path>}` | ✅ Direct |
| `#` (previous node) | No shorthand — must name the node explicitly. Hermes nodes know their `depends_on`, so `${nodes.<dep>.output.*}` is the explicit form. | ⚠️ Expressively yes (name the node), ergonomically no (no `#`). |
| `node:<A>:<path>` (source-node-qualified, multi-state) | No multi-state concept. Hermes context is a single flat dict per node. | ❌ **Gap.** |
| expr-eval arithmetic (`+`, `-`, `*`, `/`, `%`, `^`) | None — Hermes conditions are comparison-only, no math. | ❌ **Gap.** |
| expr-eval functions (`min`, `max`, `abs`, `round`, conditional ternary via lib) | None. | ❌ **Gap.** |
| Parentheses in conditions | None — Hermes grammar is flat `AND`/`OR`. | ❌ **Gap.** (`A AND B OR C` works, but `(A OR B) AND C` does not.) |
| `$` list-item symbol | `${item}` (Hermes equivalent) | ✅ |
| `_` prev-value (reduce) | None. | ❌ **Gap.** |
| `#` default-state (composite graphs) | None. | ❌ **Gap.** |
| `storeUpdater` (write-back into store mid-graph) | None — Hermes outputs are write-once at node completion. | ❌ **Gap.** |
| `map` + `filter` on edges | None — Hermes `foreach` creates parallel cards; no inline filter/map on edge values. | ⚠️ Different mechanism. |

**Conclusion:** nginbot is a **strict superset** of Hermes's condition power
plus several capabilities Hermes has no analogue for (mutable store, arithmetic,
parentheses, reduce/prev-value, multi-state). Hermes **cannot** host every
nginbot expression without additions.

---

## 5. Proposed MERGED syntax

Goal: keep Hermes's familiar `${...}` template form for inline substitution,
**and** nginbot's declarative `source:` bindings for schema-driven data flow,
in one unified variable resolver.

### 5a. Two layers, one namespace

**Layer 1 — Declarative source bindings** (the nginbot `inputSchema` model).
Each consuming field declares where its value comes from:

```yaml
inputSchema:
  properties:
    spec_path:
      source: "node:plan.output.spec_path"     # nginbot form, unchanged
    verdict:
      source: "node:#.output.verdict"          # '#' = previous node
    build_id:
      source: "input:build_id"                 # graph-level input (== trigger.*)
    total:
      source: "store:total"                    # mutable store
```

**Layer 2 — Inline `${...}` references** (the Hermes template form) that resolve
against the same namespace, so authors can write either style:

| Unified `${...}` form | Resolves to | Equivalent source directive |
|---|---|---|
| `${nodes.plan.output.spec_path}` | named node output | `node:plan.output.spec_path` |
| `${nodes.#.output.verdict}` | previous node output | `node:#.output.verdict` |
| `${input.build_id}` | graph input | `input:build_id` |
| `${store.total}` | mutable store value | `store:total` |
| `${trigger.card_id}` | **alias** for `${input.card_id}` (trigger channel) | `input:card_id` |
| `${item}` | current foreach item | `$` in map expr |
| `${item.slug}` | field of current foreach item | `$.slug` in map expr |
| `${item_index}` | current foreach index | **new** — `$_index` / `_index` |
| `${env.VAR}` | process env var | **new** namespace (neither engine has it) |

### 5b. Concrete examples — same logic, both styles

**Simple condition — "route to PASS branch":**

Hermes-style inline (familiar):
```
${nodes.check.output.verdict} == 'PASS'
```

nginbot-style declarative + expr (typed, validated):
```yaml
conditions:
  - condition: "verdict == 'PASS'"
    target: ship
inputSchema:
  properties:
    verdict: { source: "node:check.output.verdict" }
```

Unified (both coexist — `${...}` desugars to the bound name):
```yaml
conditions:
  - condition: "${nodes.check.output.verdict} == 'PASS'"
    target: ship
# no inputSchema needed; the ${...} is resolved directly by the engine
```

**Numeric + parentheses (Hermes can't, nginbot can, unified keeps both):**
```
${store.total} > 10 && (${nodes.check.output.score} >= 0.8 || ${nodes.check.output.verdict} == 'PASS')
```
Desugars to nginbot expr-eval: `total > 10 && (score >= 0.8 || verdict == 'PASS')`,
with `total`/`score`/`verdict` auto-bound from the `${...}` paths.

**foreach with index (closes the §3 gap):**
```yaml
foreach: "${nodes.tickets.output.beads}"
title_template: "Bead ${item_index}: ${item.slug}"
```
Engine exposes both `${item}` and `${item_index}` to the template, and `$` /
`$_index` to any inline expression.

**Store write-back (closes the §4 gap — new to Hermes):**
```yaml
storeUpdater:
  total: "${store.total} + 1"        # read-modify-write
  seen: "true"
```

### 5c. Resolution algorithm (unified)

1. Parse all `${...}` tokens in the string with a single compiled regex
   (Hermes currently lacks `TEMPLATE_RE` — add one: `\$\{([^}]+)\}`).
2. For each token, split on `.`: first segment selects the **namespace**
   (`nodes` | `input` | `store` | `trigger` | `item` | `item_index` | `env`).
3. `trigger.*` is sugar for `input.*` (same backing map).
4. `nodes.#` → rewrite `#` to the previous node id (borrow nginbot's `resolvePath`).
5. Resolve via the corresponding getter (`getNodeOutput` / `getInputValue` /
   `getStoreValue` / foreach context / env).
6. For conditions, desugar `${path} <op> rhs` into a bound var + feed the scope
   to `expr-eval` — gaining parentheses, arithmetic, and functions for free
   while preserving the familiar `${...}` surface syntax.
7. Missing-var policy: **configurable** — Hermes-style "treat as empty/false"
   (lenient) or nginbot-style "throw" (strict). Default lenient for templates,
   strict for conditions.

### 5d. What the merge buys

- **Hermes authors** keep writing `${nodes.X.output.Y}` — zero migration friction.
- **nginbot authors** keep declarative `source:` bindings + typed schemas.
- **Both gain**: parentheses, arithmetic, a mutable store, a loop index, and a
  unified `${...}`/directive duality where either can express the other.
- **Engine simplification**: one resolver, one condition evaluator
  (`expr-eval`), one regex (`TEMPLATE_RE`), replacing Hermes's hand-rolled
  clause matcher.

---

## 6. Verdict on the migration question

**nginbot-api's expression engine can replace Hermes's condition evaluator** —
it is a strict superset for boolean logic and adds arithmetic, parentheses,
store mutation, and reduce. Three items need attention during migration:

1. **Add `${item_index}` / `$_index`** — nginbot currently has no loop index.
2. **Wire trigger context as graph inputs** so `${trigger.*}` maps to
   `${input.*}` (one convention, documented).
3. **Decide missing-var policy** — Hermes is lenient (strip/false), nginbot is
   strict (throw). Pick one per context (lenient for templates, strict for
   conditions is the sensible default).

The reverse is **not** true: Hermes cannot host nginbot's store/arithmetic/
multi-state features without substantive new code.
