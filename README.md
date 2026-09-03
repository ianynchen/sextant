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
uv run sextant module enrich  <module-path> --agent claude-api --model <model-id>
uv run sextant module export  <module-path>
```

`scripts/check.sh` runs every gate — formatting, lint, types, import contracts, the
extractor's own build and tests, then the Python suite. `scripts/check.sh --lint` runs
the lint gates alone, which is what the pre-commit hook in `.githooks/` runs.

## Build systems and multi-module repositories

Maven and Gradle are both detected behind the same `Detector` port
([M02](docs/components/M02-detector.md)): Maven reads `pom.xml` directly, and Gradle —
which has no build file a parser can read on its own, since `build.gradle.kts` is a
Kotlin program — is learned by running the project's own `./gradlew` (falling back to a
`gradle` on `PATH`) against a read-only init script Sextant packages, offline first with
one flagged online retry (`--allow-resolve`) if the build's own dependency cache is
incomplete. `pom.xml` wins when both exist in one repository; the coexistence is recorded
as a note, never merged.

`sextant module analyze <path>` detects the root first. A **multi-module** root — Maven's
`<modules>`, Gradle's own `include`d projects — analyzes every module that is not
*known* not to be a service (a Gradle-only `library` kind, or a leaf `packaging: pom`
aggregator/BOM) into its **own** workspace, one per module, root-relative and listed in
`<repo-root>/.sextant/modules.json` alongside whether each was analyzed or skip-listed and
why. A Gradle module with no compiled output (no source-set-owning plugin applied) is
recorded with the same `skip_reason: "packaging is pom"` a Maven leaf `packaging: pom`
module gets — Maven vocabulary, reused deliberately rather than invented per build system,
since both name the identical "nothing here to scan" shape. `--workspace` is refused at a multi-module root — the flag is per-module — and
`render`/`enrich`/`export` never re-detect: pointed at a multi-module root instead of one
of its modules, they refuse and print the module list `modules.json` already named.

**Tested surface, stated honestly.** The end-to-end suite's fixtures pin Spring Boot 3.x
semantics — their value is stability, not currency. Boot 4.1 is field-validated instead,
for the HTTP inbound surface, against `examples/jhipster-sample-app` and
`examples/spring-petclinic-rest` (both live Boot 4.1 repositories) by `scripts/field_check.py`
— opt-in, network-using, and never part of `scripts/check.sh` or the test suite; its own
module docstring states exactly what it checks (endpoint counts, route sets, the HTML
output-quality assertions) and how "the first diagram parses" is defined without a browser.

## `.sextant.yml` — reading a dependency's own code

Some declarations a module depends on are not in the module. A generated SOAP client stub,
for instance, is usually published as a jar. A file beside the module's build file names
the dependencies whose **own bytecode** should be scanned alongside it:

```yaml
# .sextant.yml, beside pom.xml
extract_libraries:
  - com.example:orders-soap-client        # version comes from the build
  - com.example:legacy-billing:2.4.0      # …or state it here

redact:                                   # widens the built-in set; nothing narrows it
  key_patterns:   [dsn]                   # substring of a config key, spelling-insensitive
  value_patterns: ["ACME_[A-Z0-9]{24}"]   # regex, masks the span it matches
```

Redaction is **on by default and needs no file**: configuration keys naming a password,
secret, token, credential, API key, private key, authorization or passphrase mask as
`«redacted»`, and `scheme://user:pass@host` addresses lose their userinfo — at every point
data crosses the trust boundary: the rendered document, everywhere in the exported bundle
(its fact files included), and what `module enrich`'s own tools read back to the model (see
below). The workspace keeps real values, because resolving an endpoint's address needs them
and your own disk is not the boundary. A bundle records the rule set that masked it, as
`producer.redaction_set_hash` in its manifest.

A key pattern is matched as a substring, so it **over-masks on purpose**:
`aws.secretsmanager.endpoint` masks a hostname. That is the safe direction — a leaked
credential cannot be recalled, a masked hostname is an inconvenience, and the key is still
listed as present. If it gets in your way, the answer is a narrower built-in pattern; there
is no unmask switch, deliberately.

Three things are worth knowing before using it.

**It is an assertion, which is why it is opt-in.** Naming a library says its declarations
are part of *this module's* runtime surface — that a `@WebService` interface it ships is an
operation this module calls. Sextant cannot see component scanning, so it cannot check that
for you; instead every row a library contributed is marked with its coordinate in the
rendered document, in the facts and in the exported bundle, so the claim stays visible. The
dependency tree is **never** walked: a transitive jar nobody named stays invisible.

**It is retractable.** Remove a coordinate and its rows are gone on the next run — the
library fact subtree is discarded before anything is written, so opting out actually takes
effect rather than leaving the previous run's facts behind.

**Two coordinate forms.** `groupId:artifactId` defers to the build for the version, which
is the only place that says which release this module compiles against; `groupId:artifactId:version`
states it outright, and is the form to use when a parent POM or a BOM manages the version
(which Sextant does not resolve). The archive is read from the local Maven repository at
Maven's own layout, where a successful build has already left it. A coordinate that resolves
to nothing, and an archive that cannot be read, are both named with their reason in
`metadata.json` and in the document's gaps list — never silently skipped.

## `.sextantignore` — excluding files entirely

A root-level file, git's own ignore syntax (negation, dir-only patterns, anchoring,
`**` — via the `pathspec` package, so the semantics genuinely match git rather than a
hand-rolled approximation of it):

```
# .sextantignore, beside pom.xml
src/main/resources/legacy-vendor-dump.yml
build/
```

A file it names is excluded from analysis **entirely** — no facts, no document, no
coverage expectation, as if the file were not there. That is a stronger and riskier claim
than redaction (above), which is why exclusion is opt-in and redaction is not: excluding
`application.yml` would empty the endpoint catalog of the placeholder values it resolves
against, so nothing built in excludes ordinary configuration.

Beneath whatever a repository writes sits a fixed, **non-negatable** built-in set —
`.env`, `.env.*`, `*.pem`, `*.p12`, `*.jks`, `id_rsa*`, `id_ed25519*`, `secrets/**`,
`*.keystore`. A repository `.sextantignore` carrying `!.env` re-admits nothing: the
built-in layer never sees that line. Within a repository's own patterns, ordinary
gitignore negation works as expected — one pattern can re-admit what an earlier one in
the same file excluded.

Nested, per-directory `.sextantignore` files are not read today — one file, at the
repository root, and every pattern in it matches against a path relative to that root,
whichever resource or schema directory a given file was actually found under.

## `sextant module enrich` — the agentic overlay

Requires a rendered module first (`sextant module render`) — the brief it composes reads the
machine-rendered `architecture.md`. The model gets four read-only tools — `list_dir`,
`find`, `grep`, `read_file` — jailed to the module's own source, its facts and its rendered
outputs, with every result masked by the same redactor `render`/`export` use. Its answers
land as **add-only** claims (components, sections, diagrams, verdicts on open questions) at
`evidence: llm`, written to `.sextant-enrichment.json` at the module root and assembled
straight into both `architecture.md` and `architecture.html` — one command, done; nothing
here rewrites or reorders machine-derived text.

```
uv run sextant module enrich <module-path> --agent claude-api --model <provider's model id>
```

- **`--agent`** — for a live run, a name in `AGENT_REGISTRY` (`claude-api` ships in v1); an
  unknown name is refused, naming the known list. Under `--dry-run`/`--ingest` no adapter
  runs, so this is a free-text label for the overlay's provenance instead, not validated
  against the registry. **`--model`** is passed to the adapter **verbatim** — Sextant does
  not maintain a provider's model catalog. **`--max-turns`** caps the tool-use loop (default
  50); a no-progress guard ends the run early if the same call repeats three times running.
- **`.sextant.yml`'s `enrich:` section** supplies defaults for all three
  (`agent`/`model`/`max_turns`), read only where the matching flag is absent — flags always
  win.
- **`ANTHROPIC_API_KEY` comes from the environment alone** — never a flag, never a config
  file. Its absence is refused before any network attempt.
- **Two doors skip the model call entirely**, and Sextant validates whatever comes back
  through them exactly as it validates a live run's answer: **`--dry-run`** writes the
  composed brief and the instructions document to the workspace and calls nothing, for any
  other tool — Codex, Cursor, a person with an editor — to answer by hand; **`--ingest
  answers.json`** reads an already-answered file and writes the overlay from it.

**The jail and redaction guarantees hold only when Sextant's own loop is driving.** An agent
working the brief through `--dry-run`/`--ingest` reads the repository under its **own**
permissions, entirely outside Sextant's process — that is by design, the same "your own tool,
your own control" stance the rest of Sextant takes, not a gap in the jail above.

## Dependencies

Three toolchains, deliberately kept apart. **The layering is the reason there are three
and not one**: an extractor reads artifacts and emits facts, and one component in the
Python core interprets them — so a dependency that understands a *format* belongs to the
core, and never to any extractor.

### Python — `uv sync`

Runtime dependencies are pinned in `pyproject.toml`; `uv sync` installs them, and the
`dev` extra adds the test and lint tools. Requires Python 3.12 or newer. Beside DuckDB
(the workspace), Click and Rich (the command surface), Pydantic (the fact models) and
PyYAML (catalogs and configuration files), three exist for schema and wire-format support:

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
- **`graphql-core`** — parsing GraphQL SDL (`.graphqls`). The reference implementation of
  the GraphQL specification, used for the same reason as the two above: a schema language
  is **data we read, never an algorithm we reimplement**, and an SDL parser written by
  hand would be a second opinion about what a `!` or an `extend type` means. Only the same
  single descriptor interpreter imports it — the architecture test that confines
  `protobuf` confines this too, and the SDL *reader* hands the file's text on verbatim
  without importing a GraphQL runtime at all.
- **`pathspec`** — `.sextantignore` matching. Git's own wildmatch semantics (negation,
  dir-only patterns, anchoring, `**`) have corners a hand-rolled `fnmatch` or single
  regex disagrees with git on; mirroring git's own implementation is the point, not
  re-deriving it. Pinned to an exact version, unlike the others above — matching git
  precisely is a property of one specific release, not a minimum.

### JVM extractor — no new dependency, on purpose

`extractor-jvm` builds with Gradle, on ASM plus the Kotlin metadata decoder. Reading
protobuf and Avro schemas added **nothing** to that list: it harvests the schema payload a generated
class already embeds, as string constants, and hands it on unparsed. That is the whole
layering argument in one line — no extractor in any language links a schema runtime,
because exactly one component in the Python core understands schema formats, so a second
language's scanner gains schema support by emitting the same fact and nothing else.
GraphQL added nothing either, and for a stronger reason: its schema is a repository file,
so the Python reader emits it verbatim and the extractor never sees it.

### Fixture toolchain — nothing installed by hand

`fixtures/orders-service` is a real Maven module compiled by the end-to-end tests
(`mvn -o compile`). Its schema code generation is declared in its own `pom.xml`:
`protobuf-maven-plugin` (which downloads the `protoc` it needs — there is no system
`protoc` to install) and `avro-maven-plugin`. Building the fixture therefore needs Maven
and a JDK, and nothing else.

Since Phase 2I it also depends on `fixtures/orders-soap-client`, the stub library its
`.sextant.yml` opts into extracting. `tests/conftest.py` builds that sibling and installs
it into the local Maven repository — `~/.m2/repository/com/example/orders-soap-client/`,
exactly what `mvn install` of that fixture would write, and the only thing in this suite
that writes outside the repository — once per session, so `pytest` remains the only command
anyone runs. But `mvn -o compile` inside `fixtures/orders-service` on a fresh clone fails
until that helper has run.

### `architecture.html`'s vendored asset — pinned, not fetched

`sextant module render` writes `architecture.html` beside `architecture.md` (2K design
§6b): the same assembled document, with every diagram — machine and LLM-simplified alike —
wrapped in pan-zoom controls. The page is self-contained and opens with no network access,
which means the client-side diagram library it depends on, [mermaid](https://mermaid.js.org),
ships inside the file rather than being fetched from a CDN at view time.

`src/sextant/egress/render/assets/mermaid.min.js` is therefore vendored: downloaded once at
dev time from the official npm/jsDelivr artifact and committed verbatim, pinned by version
and sha256 in `src/sextant/egress/render/asset_pins.py` and recorded, with its MIT license,
in `assets/LICENSE-mermaid`. `tests/egress/test_render_html.py` hashes the committed file
against the pin, so an accidental swap for a different version — or a different library
under the same file name — fails loudly instead of silently changing what a reader sees.
Upgrading is deliberate: replace the file and bump both constants together.

The pan-zoom script beside it, `assets/panzoom.js`, is not vendored — it is Sextant's own,
a few dozen lines of vanilla JS with no dependency of its own to pin.
