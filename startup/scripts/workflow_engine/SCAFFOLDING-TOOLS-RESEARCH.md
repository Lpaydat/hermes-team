# Scaffolding Tools Research — Config File Storage & Copying Patterns

**Purpose:** Validate the tech-preferences config-file design (see
`CONFIG-FILE-DESIGN.md`) against how six established scaffolding tools handle
template storage, conditional includes, and partial-file generation. Primary
sources cited inline.

**Bottom line:** Every production scaffolding tool stores config files as **real
files on disk** (not inline JSON, not generated-on-the-fly from a spec). The
industry converges on a manifest-driven approach: a small index file declares
what to copy, and the files themselves are real, copy-able artifacts. This
directly validates our `configs/` + `manifest.json` design.

---

## Summary table

| Tool | Template storage | Templating engine | Conditional includes | Partial-file generation |
|---|---|---|---|---|
| **Cookiecutter** | Real files in a git repo dir; `{{cookiecutter.X}}` in paths + content | Jinja2 | `{% if %}` in content; `_copy_without_render` opt-out; nested templates for variant selection | Hooks (pre/post Python scripts); no native section-merge |
| **cargo-generate** | Real files in a git repo; `cargo-generate.toml` manifest at root | Liquid (`{{ var }}`) | `[conditional.'expr']` in manifest with Rhai expressions; `include`/`exclude`/`ignore` lists | No native section-merge; conditionals exclude whole files |
| **create-react-app** | Real files in `template/` dir of an npm package; `template.json` manifest | None (static copy) — `template.json` does structured JSON merge into `package.json` | None in the template itself; variant selection via separate npm packages (`cra-template-*`) | `template.json` `"package"` section merges into `package.json` |
| **degit** | Real files (git tarball snapshot) — **no templating at all** | None | None (intentionally) | None — just copies files verbatim |
| **Plop** | Real `.hbs` template files referenced by a `plopfile.js` | Handlebars | `if`/`unless` helpers in templates; action-level `skip()` function | **Yes** — `modify` action with regex `pattern` + `template` (insert/edit sections of existing files) |
| **Yeoman** | Real files in generator's `templates/` dir | EJS (`<%= %>`) | `copyTpl` conditionally; `if` blocks in generator JS code | **Yes** — `appendTpl`/`append` for section appending; AST parsers recommended for robust edits |

---

## Per-tool findings (with sources)

### 1. Cookiecutter — Jinja2 everywhere, manifest in `cookiecutter.json`

**Storage:** A cookiecutter template is a plain directory tree of real files.
Filenames and file contents are both Jinja2 templates. A `cookiecutter.json`
file at the root declares the variables and their defaults.

> "A Cookiecutter template is just a directory with variables."
> — https://github.com/cookiecutter/cookiecutter/blob/main/README.md

```
cookiecutter-pypackage/
├── cookiecutter.json          ← variable defaults (the "manifest")
└── {{cookiecutter.repo_name}}/← directory name is templated
    ├── setup.py
    └── ...
```

**Conditional includes:** Three mechanisms, all Jinja2-based:

1. **`{% if %}` / `{% endif %}` inside file content.** Because the entire file
   is rendered through Jinja2, any file can contain conditional blocks:

   ```jinja
   {% if cookiecutter.use_pytest == "y" %}
   [tool.pytest.ini_options]
   testpaths = ["tests"]
   {% endif %}
   ```

2. **`_copy_without_render`** — opt OUT of rendering for files that should be
   copied verbatim (e.g. they contain literal `{{ }}` for their own reasons):

   ```json
   {
       "project_slug": "sample",
       "_copy_without_render": ["*.html", "*not_rendered_dir"]
   }
   ```
   — https://github.com/cookiecutter/cookiecutter/blob/main/docs/advanced/copy_without_render.rst

3. **Nested config files (2.5+)** — variant selection: a parent
   `cookiecutter.json` points to sub-templates, and the user picks one:

   ```json
   {
       "templates": {
           "project-1": {"path": "./project-1", "title": "Project 1"},
           "package": {"path": "./package", "title": "Package"}
       }
   }
   ```
   — https://github.com/cookiecutter/cookiecutter/blob/main/docs/advanced/nested_config_files.rst

   This is the cookiecutter equivalent of our `manifest.json` stack keys
   (`python-paved` vs `python-ruff-standalone`): pick the variant at
   scaffolding time.

4. **Template inheritance (2.2+)** — `{% extends %}` / `{% include %}` for
   shared base files, like Django/Jinja template inheritance:
   — https://github.com/cookiecutter/cookiecutter/blob/main/docs/advanced/templates.rst

**Partial-file generation:** No native support for "write only the `[tool.ruff]`
section into an existing `pyproject.toml`." The practical workaround is
conditional blocks (`{% if %}`) within a single full template file — exactly
**Option A** in our design doc. Hooks (pre/post-generate Python or shell
scripts) can do arbitrary post-processing but are a manual escape hatch.

> **Verdict:** Cookiecutter validates our Option A (full template file with
> conditional `{% if %}` blocks). It does NOT do section-level merging.

---

### 2. cargo-generate — Liquid templates + manifest-driven conditionals

**Storage:** Real files in a git repo. A `cargo-generate.toml` manifest at the
template root declares placeholders, conditionals, and include/exclude rules.
File content uses Shopify's **Liquid** templating language:

> "cargo-generate uses **Shopify's Liquid** as its template engine."
> — https://cargo-generate.github.io/cargo-generate/ (Introduction page)

```markdown
// README.md (template)
This awesome crate `{{ crate_name }}` is brought to you by {{ authors }}.
```
— https://github.com/cargo-generate/cargo-generate/blob/main/guide/src/templates/builtin_placeholders.md

**Conditional includes:** The most structured conditional system of all six
tools. Placeholders are declared in `[placeholders]`, then `[conditional.'expr']`
sections use **Rhai** (an embedded scripting language) expressions to decide
which files to include/exclude/ignore:

```toml
[template]
cargo_generate_version = ">=0.10.0"

[placeholders]
license = { type = "string", prompt = "What license?", choices = ["MIT", "Unrestricted"], default = "MIT" }

# Condition: if crate_type is "lib", ignore src/main.rs
[conditional.'crate_type == "lib"']
ignore = [ "src/main.rs" ]

# Condition: based on license choice, ignore the wrong LICENSE file
[conditional.'license == "MIT"']
ignore = [ "LICENSE-UNRESTRICTED.txt" ]
```
— https://github.com/cargo-generate/cargo-generate/blob/main/guide/src/templates/conditional.md

The `include`/`exclude` lists control whether Liquid processing happens:

> "`include` These files will be processed for `Liquid` syntax by the template
> engine. `exclude` These files will *not* be processed for any `liquid` syntax.
> The files will be in the final output."
> — https://github.com/cargo-generate/cargo-generate/blob/main/guide/src/templates/include_exclude.md

**Partial-file generation:** Not supported. Conditionals exclude **whole
files** (`ignore = [...]`), not sections within a file. A `Cargo.toml` is
emitted as a single Liquid-templated file. This mirrors our Option A decision.

> **Verdict:** cargo-generate's `[conditional]` + `ignore` pattern is the
> closest analog to our `manifest.json` `match_keywords` + stack selection.
> Like cookiecutter, it does section-conditional content via Liquid `{% if %}`
> inside files, not section-merging across files.

---

### 3. create-react-app — static copy + structured JSON merge for package.json

**Storage:** CRA templates are npm packages (`cra-template`, `cra-template-typescript`).
The package contains a `template/` directory of **real static files** and a
`template.json` manifest:

```
cra-template/
├── template.json          ← manifest: declares deps + config to inject
├── package.json
└── template/              ← real files copied verbatim into the new project
    ├── public/
    │   └── index.html
    ├── src/
    │   ├── index.js       ← static, no templating
    │   ├── App.js
    │   └── index.css
    └── ...
```

The actual files are **100% static** — no template engine at all:

```js
// template/src/index.js — copied verbatim, no placeholders
import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
```
— https://github.com/facebook/create-react-app/blob/main/packages/cra-template/template/src/index.js

**Conditional includes:** None within a template. CRA handles variants by
shipping **separate npm packages** (`cra-template` vs `cra-template-typescript`).
The `--template typescript` flag picks a different package entirely. This is
the same "one directory per variant" approach as our `python/`, `node/`, `go/`
language dirs.

**Partial-file generation — the one exception (`package.json`):** The
`template.json` manifest has a `"package"` key whose contents are **merged** into
the generated project's `package.json` by CRA's `package.json` merge logic:

```json
{
  "package": {
    "dependencies": {
      "@testing-library/react": "^16.1.0"
    },
    "eslintConfig": {
      "extends": ["react-app", "react-app/jest"]
    }
  }
}
```
— https://github.com/facebook/create-react-app/blob/main/packages/cra-template/template.json

This is **structured JSON merging** — CRA knows `package.json` is JSON, parses
both, deep-merges the template's `dependencies` and `eslintConfig` into the base.
This is the ONLY tool in the set that does partial-file generation, and it only
works because the target file (`package.json`) is JSON and CRA has
JSON-specific merge logic.

> **Verdict:** CRA confirms static-file-copy for everything *except* one
> structured format (JSON) where it does programmatic merging. For TOML/YAML
> configs, it would fall back to static copy. This validates our distinction:
> static files by default, substitution only where needed.

---

### 4. degit — pure copy, zero templating (the deliberate baseline)

**Storage:** degit makes literal copies of git repositories. No templating,
no substitution, no manifest:

> "**degit** makes copies of git repositories. When you run
> `degit some-user/some-repo`, it will find the latest commit [...] and download
> the associated tar file."
> — https://github.com/Rich-Harris/degit (README)

**Conditional includes:** None. **Partial-file generation:** None.

**Post-copy actions:** degit's `degit.json` supports only three actions:
`clone`, `search_replace`, and `remove` — all operating on the copied tree as a
whole, not on file internals:

> "Currently, there are three actions — `clone`, `search_replace`, and `remove`."
> — https://github.com/Rich-Harris/degit (README, Actions section)

degit exists as the "just copy the files" counterpoint to heavier tools. Svelte,
SvelteKit, and many JS starters are consumed via degit. It proves that for many
real-world scaffolding scenarios, **static file copy with no templating is
sufficient** — the user edits after copying.

> **Verdict:** degit represents the "files are just files" extreme. Our design
> is one notch above this (we add `${PROJECT_NAME}` substitution + manifest
> selection), which is the minimal viable addition over pure copy.

---

### 5. Plop — Handlebars templates + the `modify` action (partial generation done right)

**Storage:** Real `.hbs` (Handlebars) template files referenced by a
`plopfile.js`:

> "plop is basically glue code between inquirer prompts and handlebar templates."
> — https://github.com/plopjs/plop/blob/main/README.md

```js
// plopfile.js
module.exports = function (plop) {
  plop.setGenerator('controller', {
    actions: [{
      type: 'add',
      path: 'src/controllers/{{name}}.js',
      templateFile: 'plop-templates/controller.hbs'
    }]
  });
};
```

**Conditional includes:** Handlebars `{{#if}}` / `{{#unless}}` helpers in
templates, plus action-level `skip()` functions that conditionally skip an
entire file write.

**Partial-file generation — the `modify` action:** Plop is the only tool here
with a **first-class "edit a section of an existing file"** primitive:

> "The `modify` action [...] The `pattern` property is a [regex] that will be
> used to find the section of the file to be modified [...] The `template`
> property is a handlebars template that should replace what was matched by the
> `pattern`."

| Field | Purpose |
|---|---|
| `path` | file to modify |
| `pattern` | regex matching the section to replace |
| `template` | Handlebars template replacing the matched section |

This enables inserting a `[tool.ruff]` block into an existing `pyproject.toml`
by matching a regex anchor and substituting a template. Plop also supports
`append` (add to end of file) and custom action types.

> **Verdict:** Plop proves that partial-file generation IS possible and useful,
> but requires a regex-based or AST-based approach. It's the pattern to follow
> IF we ever need to merge config sections into existing files (our design
> currently avoids this by using full templates — Option A).

---

### 6. Yeoman — EJS templates + in-memory FS + AST-based file editing

**Storage:** Real files in the generator's `templates/` directory:

> "The template context is the folder in which you store your template files."
> — https://yeoman.io/authoring/file-system.html

Templates use **EJS** syntax, applied via `this.fs.copyTpl()`:

```js
class extends Generator {
  writing() {
    this.fs.copyTpl(
      this.templatePath('index.html'),    // source: templates/index.html
      this.destinationPath('public/index.html'),  // dest: project dir
      { title: 'Templating with Yeoman' }         // data
    );
  }
}
```
— https://yeoman.io/authoring/file-system.html

**In-memory filesystem with conflict resolution:** Yeoman writes everything to
an in-memory file system first, then commits to disk once with conflict
detection (won't overwrite existing files without prompting):

> "every file is written asynchronously to the disk [...] Yeoman provide a
> synchronous file-system API where every file gets written to an in-memory file
> system and are only written to disk once when Yeoman is done running."
> — https://yeoman.io/authoring/file-system.html

**Conditional includes:** Done in generator JS code (`if` statements wrapping
`copyTpl` calls) or EJS `<% if %>` blocks in templates.

**Partial-file generation:** Yeoman's `mem-fs-editor` provides `append` and
`appendTpl` methods:

> "`#appendTpl(filepath, contents, data)` — Append the new contents to the
> existing filepath content and parse the new contents as an [ejs] template."
> — https://github.com/SBoudrias/mem-fs-editor (README)

But for **robust** partial edits of structured config files, Yeoman's own docs
explicitly recommend **AST parsing**:

> "Updating a pre-existing file is not always a simple task. The most reliable
> way to do so is to parse the file AST (abstract syntax tree) and edit it."
> — https://yeoman.io/authoring/file-system.html

Recommended parsers: Cheerio (HTML), Esprima/AST-Query (JS), JSON object
methods, Gruntfile Editor.

> **Verdict:** Yeoman confirms that partial-file generation is hard enough that
> the maintainers themselves say "just use an AST parser." This validates our
> decision to avoid section-merging (Option B) and use full templates (Option A)
> for composite configs like `pyproject.toml`.

---

## Cross-cutting patterns

### Pattern 1: Everyone stores templates as real files on disk
All six tools store templates as **real files** in a directory tree — never as
inline strings in a JSON spec, never generated purely from code. Even degit,
which has zero logic, copies real files. This is universal.

### Pattern 2: A manifest/index file drives selection
- Cookiecutter → `cookiecutter.json`
- cargo-generate → `cargo-generate.toml`
- CRA → `template.json`
- Plop → `plopfile.js`
- Yeoman → generator JS code

Our `manifest.json` follows this exact pattern.

### Pattern 3: Conditionals operate at two levels
1. **File-level** (include/exclude whole files based on user choices) — all
   tools except degit support this. Our `manifest.json` stack keys do this.
2. **Content-level** (`{% if %}` blocks within a file) — Cookiecutter (Jinja2),
   cargo-generate (Liquid), Plop (Handlebars), Yeoman (EJS). Our `${}` approach
   is simpler (substitution only, no conditionals) — acceptable for the paved
   road but a limitation if we need optional sections.

### Pattern 4: Partial-file generation (section merging) is hard and avoided
No tool does TOML/YAML section merging natively. The two that attempt
partial-file generation (Plop's `modify`, Yeoman's `appendTpl`) rely on regex
or AST parsing. CRA only does it for JSON (`package.json`). The consensus: use
full template files and avoid merging whenever possible.

---

## Recommendation for the tech-preferences system

### The existing design (CONFIG-FILE-DESIGN.md) is well-validated

The choices in `CONFIG-FILE-DESIGN.md` align with industry consensus:

| Our decision | Industry precedent | Verdict |
|---|---|---|
| Store configs as real files in `configs/` dir | All 6 tools store real files | ✅ Confirmed best practice |
| `manifest.json` maps stack → file list | Cookiecutter's `cookiecutter.json`, cargo-generate's `cargo-generate.toml`, CRA's `template.json` | ✅ Standard pattern |
| Full template file (Option A) over fragment assembly (Option B) | Cookiecutter, cargo-generate, CRA all use full files; section-merging is universally avoided | ✅ Correct |
| Static by default, `${}` only for project name/version | CRA (static), degit (static); CRA uses templating only for the one composite file (`package.json`) | ✅ Minimal templating is the sweet spot |
| One dir per language (`python/`, `node/`, `go/`) | CRA's separate `cra-template-*` packages for variants | ✅ Variant-per-directory is standard |

### Specific recommendation: static files + minimal `${}` placeholders (not JSON generation)

**Store config files as real template files with minimal `${}` placeholders —
NOT generated from JSON, NOT fully static, NOT heavy templating.**

This is a hybrid that matches the majority pattern:

1. **Not pure JSON generation.** No tool generates config files purely from a
   JSON spec. Even CRA, which comes closest (its `template.json` has an
   `eslintConfig` section), only does JSON→JSON merging for `package.json` and
   copies all other files statically. Generating TOML/YAML from JSON would
   require format-specific serializers and lose the "files are diffable and
   auditable" property. Our `ruff.toml`, `.gitignore`, `Makefile`, `conftest.py`
   are not JSON-serializable config — they're freeform files.

2. **Not fully static.** `pyproject.toml` needs `name = "${PROJECT_NAME}"` —
   this varies per project and can't be hardcoded. Cookiecutter and
   cargo-generate both use template engines for exactly this reason.

3. **Minimal `${}` substitution, not a full template engine.** Our paved road
   has exactly two variables (`PROJECT_NAME`, `PROJECT_VERSION`). Adding Jinja2
   or Liquid as a dependency for two substitutions is overkill. `envsubst` or a
   Python `str.replace()` is sufficient and matches degit's philosophy of
   minimal machinery.

### When to reconsider (upgrade triggers)

- **If we need optional config sections** (e.g., `[tool.mypy]` only when mypy
  is selected): upgrade `${}` to a template engine with conditionals (Jinja2).
  This is the Cookiecutter/cargo-generate pattern (`{% if use_mypy %}`). Add it
  only when the paved road fragments into multiple tool combos.

- **If we need to merge config sections into existing files** (e.g., a project
  already has a `pyproject.toml` and we need to add `[tool.ruff]` without
  clobbering `[project]`): adopt Plop's `modify` pattern (regex anchor + template
  insert) or a TOML AST library. Yeoman's docs warn this requires AST parsing —
  don't attempt it with string concatenation.

- **If the number of config variants explodes** (10+ language/tool
  combinations): switch from flat `manifest.json` to nested variant selection
  (cookiecutter's `templates` key, cargo-generate's `[conditional]` sections).

### Concrete next step

The existing `CONFIG-FILE-DESIGN.md` and `manifest.json` schema need **no
changes** based on this research. The design is already the industry-standard
pattern. The one enhancement worth considering for the future is documenting
the upgrade path to Jinja2-style `{% if %}` conditionals if optional tool
sections become needed.

---

## Sources

| Tool | Primary source | URL |
|---|---|---|
| Cookiecutter | GitHub README + RST docs | https://github.com/cookiecutter/cookiecutter |
| cargo-generate | Official mdBook docs (guide/src/) | https://cargo-generate.github.io/cargo-generate/ |
| create-react-app | GitHub repo (cra-template package) | https://github.com/facebook/create-react-app |
| degit | GitHub README | https://github.com/Rich-Harris/degit |
| Plop | GitHub README | https://github.com/plopjs/plop |
| Yeoman | yeoman.io authoring docs + mem-fs-editor | https://yeoman.io/authoring/file-system.html |
