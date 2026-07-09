# Language build & test reference

Build, run, and test commands for languages/ecosystems beyond the main build detection table and program-type references. Each entry covers: signal file, build command, run command, test verification, and ecosystem-specific quirks worth probing.

---

## C# / .NET

**Signal:** `.sln`, `.csproj`, `.fsproj`, `Directory.Build.props`

```bash
# Build
dotnet build
dotnet build -c Release

# Run
dotnet run --project src/MyApp
./bin/Release/net8.0/MyApp          # run the binary directly

# Test (xUnit/NUnit/MSTest)
dotnet test
dotnet test --logger "console;verbosity=detailed"

# Package
dotnet pack -c Release
```

**Quirks to probe:**
- `appsettings.json` vs `appsettings.Production.json` — configuration overrides
- Entity Framework migrations: `dotnet ef database update` — does it apply cleanly?
- ASP.NET Core: test `GET /health` and `GET /swagger/index.html` (Swagger UI)
- Nullable reference types (`<Nullable>enable</Nullable>)` — pass null where string expected
- Dependency injection: verify DI container resolves all services at startup
- Kestrel vs IIS vs kestrel-with-nginx — test behind a reverse proxy if applicable

---

## PHP / Laravel / Composer

**Signal:** `composer.json`, `artisan`, `index.php`, `public/index.php`

```bash
# Install
composer install

# Laravel dev server
php artisan serve --port=8000

# Plain PHP
php -S localhost:8000 -t public/

# Run migrations
php artisan migrate

# Test (PHPUnit/Pest)
./vendor/bin/phpunit
./vendor/bin/pest

# Clear caches (common fix for stale state)
php artisan config:clear
php artisan route:clear
php artisan view:clear
```

**Quirks to probe:**
- `php artisan route:list` — verify all routes are registered
- CSRF tokens: POST without `_token`, with expired token, with tampered token
- Mass assignment: POST extra fields to a model controller — does `fillable`/`guarded` protect?
- N+1 queries: check Laravel Telescope or `DB::enableQueryLog()` for excessive queries
- `.env` file: missing required keys, wrong DB credentials
- File uploads: `upload_max_filesize`, `post_max_size` in `php.ini`
- Session handling: session in file vs Redis vs database — test session persistence across requests
- Composer autoload: `composer dump-autoload` if class-not-found after adding files

---

## Scala / sbt

**Signal:** `build.sbt`, `project/build.properties`, `build.sc` (Mill)

```bash
# sbt
sbt compile
sbt run
sbt test

# Mill (alternative build tool)
mill _.compile
mill _.run
mill _.test

# Package
sbt package          # JAR
sbt assembly         # Fat JAR (if assembly plugin present)
```

**Quirks to probe:**
- JVM version mismatch: Scala 3 needs JDK 11+; verify `java -version`
- Implicit resolution: verify library-specific implicits compile at usage site
- Akka/Pekko actors: test message delivery, supervision strategy, actor lifecycle
- Cats/ZIO effects: test error channel (`.either`, `Task.catchAll`)
- SBT dependency conflicts: `sbt evicted` to check for version conflicts

---

## Haskell / stack / cabal

**Signal:** `*.cabal`, `stack.yaml`, `package.yaml`, `flake.nix` (with Haskell)

```bash
# Stack
stack build
stack exec <executable-name>
stack test

# Cabal
cabal build
cabal run <executable>
cabal test

# GHCi (REPL for interactive testing)
stack ghci
```

**Quirks to probe:**
- `undefined` / `error` in code paths — these compile fine and crash at runtime
- Partial functions: `head []`, `tail []`, `fromJust Nothing` — call with empty/None
- Lazy evaluation: space leaks with large lists — force evaluation with `deepseq`
- Template Haskell: compile-time code generation — verify it works across GHC versions
- `README.md` build instructions: Haskell projects often have non-standard build steps

---

## Erlang / OTP / rebar3

**Signal:** `rebar.config`, `src/*.erl`, `relx.config`

```bash
# Build
rebar3 compile

# Run a release
rebar3 release
./_build/default/rel/<name>/bin/<name> console

# Test (Common Test / EUnit)
rebar3 ct
rebar3 eunit

# Shell (for interactive testing)
rebar3 shell
```

**Quirks to probe:**
- Supervision trees: kill a child process — does the supervisor restart it?
- Message passing: send to a non-existent PID — crash or silent?
- Hot code reload: load new module version while old runs — does it swap cleanly?
- Distributed Erlang: `epmd` daemon must be running for node communication
- OTP application start: `application:start(<app>)` — missing dependencies?
- Mnesia tables: schema creation, table recovery after crash

---

## Lua

**Signal:** `*.rockspec`, `init.lua`, `lua/` directory, `luarocks`

```bash
# Install dependencies
luarocks install <rock-name>

# Run
lua main.lua
lua script.lua arg1 arg2

# Test (busted/luaunit)
luarocks install busted
busted spec/

luarocks install luaunit
lua test.lua
```

**Quirks to probe:**
- Global variables: Lua treats undeclared variables as globals (nil) — typos are silent bugs
- `nil` indexing: `nil.field` throws an error — pass nil where a table is expected
- Numeric precision: Lua 5.3+ has integers, pre-5.3 everything is float
- C modules: `require("cmodule")` — verify shared library is compiled and on `package.cpath`
- LÖVE (game framework): `love .` to run — test game loop, input handling, draw callbacks

---

## R

**Signal:** `DESCRIPTION`, `NAMESPACE`, `*.Rproj`, `R/` directory

```bash
# Install package
R CMD INSTALL .
# Or from R:
Rscript -e 'devtools::install()'

# Run a script
Rscript analysis.R

# Test (testthat)
R CMD check .
Rscript -e 'devtools::test()'

# Shiny app (interactive web app)
Rscript -e 'shiny::runApp(".")'
```

**Quirks to probe:**
- CRAN check warnings: NOTE about global variables (common in dplyr pipelines)
- S3/S4 dispatch: call generic with unexpected class — correct method selected?
- NA propagation: `NA + 1 = NA`, `mean(c(1,2,NA)) = NA` unless `na.rm=TRUE`
- Factor levels: unexpected levels, empty levels after subsetting
- Package dependencies at runtime: missing `library()` calls
- Shiny reactivity: reactive values, observers, reactive expressions — test re-render on input change
- Data file paths: `system.file()` vs relative paths — works when installed but not from source?

---

## Zig

**Signal:** `build.zig`, `build.zig.zon`

```bash
# Build
zig build

# Run
./zig-out/bin/<name>

# Run tests (defined in build.zig)
zig build test

# Build for different targets (cross-compilation is a first-class feature)
zig build -Dtarget=x86_64-linux-gnu
zig build -Dtarget=aarch64-macos
```

**Quirks to probe:**
- Allocator behavior: Zig has no default allocator — test with different allocators (GeneralPurpose, Arena, FixedBuffer)
- `@intCast` overflow: explicit casts panic on overflow in Debug/ReleaseSafe
- Undefined behavior: Debug mode catches more UB than ReleaseFast — test in both
- `undefined` values: reading an undefined value is UB — verify initialization paths
- Panic on unwinding: Zig panics abort by default (no unwinding) — test error return paths
- `comptime`: compile-time evaluation — verify generic functions work with edge-case types

---

## Nim

**Signal:** `*.nimble`, `*.nim`, `nim.cfg`

```bash
# Build
nimble build

# Run
./<name>

# Compile directly
nim c -d:release main.nim
nim c main.nim

# Test
nimble test
# Or if tests are in a directory:
nim c -r tests/test_main.nim

# Documentation generation
nim doc main.nim
```

**Quirks to probe:**
- `nil` dereference: accessing fields of a nil ref/ptr — crashes with SIGSEGV
- Stricter null safety with `--experimental:strictNotNil`
- `seq` bounds: `seq[i]` with out-of-bounds index — raises IndexDefect
- Exceptions vs defects: Exceptions are catchable; Defects are not (programmer error)
- JS backend: `nim js main.nim` — test code compiled to JavaScript
- ImportC: C interop — verify header bindings match the linked library

---

## Unlisted language?

See the "Novel type?" protocol in SKILL.md — find the README, check CI config for exact build commands, map to the closest archetype, and add a new entry here once you've figured out the flow.
