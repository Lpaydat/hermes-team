# Library / Package / SDK Testing

Covers Python packages, npm packages, Rust crates, Go modules, Java/Kotlin jars, and any code consumed by other code.

## Key distinction

You write a **real consumer script** that imports and uses the library the way a real user would, to prove the public API works as documented. This is integration testing from the consumer's perspective.

## Install

```bash
# Python:
pip install -e .            # editable install from source
pip install .               # package install

# Node.js:
npm install                 # local
npm link                    # global link for local testing

# Rust:
cargo add <crate-name>      # or path = "../my-crate" in a test project's Cargo.toml

# Go:
go mod tidy
go get <module-path>

# Java/Kotlin:
mvn install                 # install to local Maven repo
```

## Confirm it's importable

```bash
python3 -c "import <package>; print(<package>.__version__)"
node -e "const lib = require('<package>'); console.log(Object.keys(lib))"
go build -o /dev/null ./...   # at least compiles
```

## Write a real consumer

Create a test script in the workspace (outside the library source) that uses the library the way the docs describe:

### Python
```python
from <package> import Client, Config

client = Client(Config(api_key="test-key"))
result = client.do_the_thing("input")
assert result is not None
assert result.status == "ok"
print(f"PASS: do_the_thing returned {result}")
```

### Node.js
```javascript
const { Client } = require('<package>');

async function main() {
    const client = new Client({ apiKey: 'test-key' });
    const result = await client.doTheThing('input');
    console.assert(result.status === 'ok', `Expected ok, got ${result.status}`);
    console.log('PASS: doTheThing returned', result);
}
main().catch(e => { console.error('FAIL:', e); process.exit(1); });
```

## Test the documented API surface

```python
# Enumerate the public API:
import <package>
public_names = [n for n in dir(<package>) if not n.startswith('_')]
print("Public API:", public_names)

# For each documented function/class:
# 1. Call with valid arguments → verify return value
# 2. Call with invalid arguments → verify error handling
# 3. Check the return type matches the docs
```

## Library-specific edge cases

Cases beyond the universal categories in SKILL.md:

| Category | Tests |
|----------|-------|
| Version compatibility | Does it import on the minimum supported language version? Latest? |
| Missing optional deps | If the library has optional dependencies, test without them installed |
| Type hints | If the library ships type hints (py.typed, .d.ts), do they match the actual API? |
| Async/sync | If the library has both async and sync APIs, test both |
| Thread safety | Call from multiple threads simultaneously — is it thread-safe as documented? |
| Error messages | Are exceptions/errors informative and as documented? |
| Configuration | Default config, custom config, invalid config values |
| Resource cleanup | Does it close connections/files properly? Use context managers? |
| Serialization round-trip | If the library serializes/deserializes data, round-trip test it |
| Callbacks/events | If the library uses callbacks or events, trigger and verify they fire |
| Circular references | If the library handles objects/graphs, test circular refs |

## Package distribution checks

If the library is published (or about to be), verify the package contents:

```bash
# Python:
python3 -m build
unzip -l dist/*.whl              # are all modules included? data files present?
python3 -m twine check dist/*

# Node.js:
npm pack --dry-run               # what files are in the tarball?

# Rust:
cargo package --list
```

A frequent finding: source files or data files missing from the published package despite being needed at runtime.

## Evidence

- Consumer script source code
- Full output of running the consumer script (stdout + stderr + exit code)
- Import error output (if import fails)
- Public API listing
- Package contents listing (for distribution checks)
