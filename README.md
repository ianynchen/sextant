# Sextant

Sextant reads compiled code and produces an accurate, queryable model of a software
system: what it exposes, what it calls, what data crosses each boundary, and how the
pieces reach each other.

Where to read next: [CONTEXT.md](CONTEXT.md) for what the terms mean,
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the system is shaped,
[docs/COVERAGE.md](docs/COVERAGE.md) for what it can and cannot detect today, and
[docs/components/](docs/components/README.md) for the data and module contracts.

## Running it

```
uv sync                                        # Python side
(cd extractor-jvm && ./gradlew build)          # the JVM extractor jar

uv run sextant module analyze <module-path>
uv run sextant module render  <module-path>
uv run sextant module export  <module-path>
```

`scripts/check.sh` runs every gate — formatting, lint, types, import contracts, the
extractor's own build and tests, then the Python suite. `scripts/check.sh --lint` runs
the lint gates alone, which is what the pre-commit hook in `.githooks/` runs.

## Dependencies

Three toolchains, deliberately kept apart. **The layering is the reason there are three
and not one**: an extractor reads artifacts and emits facts, and one component in the
Python core interprets them — so a dependency that understands a *format* belongs to the
core, and never to any extractor.

### Python — `uv sync`

Runtime dependencies are pinned in `pyproject.toml`; `uv sync` installs them, and the
`dev` extra adds the test and lint tools. Requires Python 3.12 or newer. Beside DuckDB
(the workspace), Click and Rich (the command surface), Pydantic (the fact models) and
PyYAML (catalogs and configuration files), two exist for wire-format support:

- **`protobuf`** — parsing schema descriptors. It is also the **authority for wire
  names**: `FieldDescriptor.json_name` gives protobuf's JSON encoding of a field, whether
  computed by protoc or overridden in the `.proto`, so the proto3 renaming rule
  (`total_amount` → `totalAmount`) is data Sextant reads rather than an algorithm it
  reimplements and could get wrong. Only the single descriptor interpreter imports it —
  an architecture test enforces that.
- **`grpcio-tools`** — compiling `.proto` **source files** to descriptors. It bundles
  `protoc`, so a repository's own schema files can be read with nothing installed by
  hand. There is no hand-written `.proto` text parser anywhere in the codebase, and there
  will not be one.

### JVM extractor — no new dependency, on purpose

`extractor-jvm` builds with Gradle, on ASM plus the Kotlin metadata decoder. Reading
protobuf and Avro schemas added **nothing** to that list: it harvests the schema payload a generated
class already embeds, as string constants, and hands it on unparsed. That is the whole
layering argument in one line — no extractor in any language links a schema runtime,
because exactly one component in the Python core understands schema formats, so a second
language's scanner gains schema support by emitting the same fact and nothing else.

### Fixture toolchain — nothing installed by hand

`fixtures/orders-service` is a real Maven module compiled by the end-to-end tests
(`mvn -o compile`). Its schema code generation is declared in its own `pom.xml`:
`protobuf-maven-plugin` (which downloads the `protoc` it needs — there is no system
`protoc` to install) and `avro-maven-plugin`. Building the fixture therefore needs Maven
and a JDK, and nothing else.
