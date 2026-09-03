# D04 — Configuration, exclusion and redaction

What can be configured, where it lives, and how Sextant is kept from storing secrets.
Written by people. Read by [M02](M02-detector.md), [M03](M03-scanner.md) and, through them,
everything else.

---

## 1. The separation this document rests on

> **Exclusion controls *scope*. Redaction controls *values*.
> The defence against leaking a secret is redaction, not exclusion.**

The instinct is to exclude files that hold credentials. That instinct is a trap here:
`application.yml` and `.env` are simultaneously where credentials live **and** where the
placeholder values come from that make the endpoint catalog work. Excluding them empties
the catalog.

**They must be read and redacted, never excluded.** Everything below follows from that.

---

## 2. Two configuration files

Different settings have different owners, so one file is not enough.

| File | Owner | Holds |
|---|---|---|
| `~/.sextant/config.yml` | The person | Workspace location, default output format, tool paths, scanner selection, personal redaction patterns |
| `sextant.yml` at repository root | The repository | First-party group patterns, module classification overrides, extra catalogs, extra redaction patterns |
| `.sextant.yml` beside a module | The module | Which dependencies' own bytecode is extracted with it (§2a) |

**Precedence: flags, then repository, then user, then built-in defaults.** First-party group
patterns are a property of the codebase, not of the person analysing it — which is the
reason the repository file exists.

```yaml
# sextant.yml
version: 1

first_party:
  groups: ["com.acme.*", "io.acme.*"]
  artifacts: ["com.partner:shared-domain"]

modules:
  ":tools:codegen": { kind: library }

catalogs:
  - catalogs/acme-http-client.yml

redaction:
  key_patterns:   ["*.internal-token"]
  value_patterns: ["ACME_[A-Z0-9]{24}"]
```

```yaml
# ~/.sextant/config.yml
version: 1

workspace: { location: in-module }
output:    { format: auto }

tools:
  helm: /opt/homebrew/bin/helm

scanners:
  pin: { java: asm }
```

**Lists merge, scalars override.** Repository redaction patterns add to the user's and to
the built-in set; they never replace them. A repository cannot switch redaction off.

---

## 2a. `.sextant.yml` beside a module — opt-in library extraction, added redaction

A third file, owned by neither of the two above: it sits **beside one module's build file**,
because what it declares is a property of that module and of nothing else.

```yaml
# fixtures/orders-service/.sextant.yml
extract_libraries:
  - com.example:orders-soap-client

redact:
  key_patterns:   [dsn]                    # matched against a normalized config key
  value_patterns: ["ACME_[A-Z0-9]{24}"]    # regular expressions, matched against values

enrich:
  agent:      tradewind                    # an AGENT_REGISTRY name; --agent overrides
  auth:       subscription                 # or api-key; --auth overrides
  session_store: .tradewind/sessions.sqlite  # api-key only; ':memory:' opts out
  model:      <provider's own model id>    # passed to the agent verbatim; --model overrides
  max_turns:  50                           # --max-turns overrides
```

`extract_libraries` names dependencies whose **own bytecode** is scanned alongside the
module's output. Every fact it produces records the coordinate as its `origin`
([D00](D00-fact-schema.md) §2), lands under `facts/lib/<groupId>/<artifactId>/`, and is
marked in the rendered document as coming from that library.

**Naming a library is an assertion, and it is why this is opt-in.** It says the library's
declarations are part of *this module's* runtime surface — that a `@WebService` interface it
ships is an operation this module calls, not merely a class on the classpath. The dependency
tree is **never** walked: a transitive jar nobody named stays invisible, because scanning
everything reachable would publish every framework's own annotated types as this module's
endpoints. A module with no `.sextant.yml` produces exactly the facts it produced before
this mechanism existed, byte for byte. What each engine style then derives from a
library's bytecode — and how removing a coordinate retracts it again — is
[D02](D02-catalog-schema.md) §4a.

Each coordinate is `groupId:artifactId`, which defers to the build for the version — the
only place that says which release this module compiles against — or
`groupId:artifactId:version`, which is the author's **own** assertion of the release to
read. The three-part form exists because the two-part one cannot reach every dependency:
a version managed by a parent POM or a BOM is not one [M02](M02-detector.md) resolves, and
pinning it here asks the build nothing. Either way the library is *known* by its
`groupId:artifactId`, so the fact subtree and the rendered attribution do not change shape
when a version is pinned.

M02 resolves the coordinate to an archive in the local repository. A coordinate that
resolves to nothing, and an archive that resolves but cannot be read, are both **named**
with their reason — in `metadata.json` and in the document's gaps list, never silently
skipped. They are two lists, not one: the first is closed by declaring, pinning or
installing the dependency, the second by replacing a corrupt archive, and a reader should
not have to work out which from prose. A library that fails to scan never takes the
module's own analysis down with it, and leaves no partial fact subtree behind.

`redact` (2K design §1) **widens** the built-in redaction set of §4, for this module only.
A key pattern is matched as a substring of a *normalized* configuration key — the relaxed
binding rule the resolver itself uses, so one written pattern covers `api-key`, `api_key`
and `apiKey` at once — and a value pattern is a regular expression matched against a
value's text, masking the span it matched. **There is no key here or anywhere that narrows
the set**: the built-ins are not an argument the redactor accepts, so no file can remove
one. A module with no `redact:` section is redacted by the built-in set exactly as before.

**Substring matching over-masks, deliberately.** `aws.secretsmanager.endpoint` carries
`secret` and therefore masks, though its value is a hostname. The two failure directions
are not symmetric: under-masking leaks a credential and cannot be undone once a bundle has
left, while over-masking hides a value from a document that still says the key is present —
masked is not absent, so [NFR-7](../REQUIREMENTS.md) survives it. The day it costs a real
workflow something, the fix is a **more precise built-in pattern**, never a reveal, unmask
or exclude mechanism; none exists, by construction.

`enrich` (2K design §3) reads its own **defaults** from this file: `agent`, `model`,
`max_turns`, each `None` — no default declared — where the module names none. Precedence is
flags, then this file, then nothing: `sextant module enrich`'s own `--agent`/`--model`/
`--max-turns` flags win whenever given, and fall through to whatever `enrich:` declares only
when the flag itself is absent. A module with no `enrich:` section supplies every value
through its own flags, exactly as if this section did not exist. See §4b for the command
this configures.

**A malformed `.sextant.yml` fails the run** — the one input where Sextant refuses rather
than degrading. DR-6's refusal-to-guess governs evidence read out of a codebase Sextant
does not own, where an honest absence is the right answer. This file is an instruction
written *for* Sextant, and a misspelled key that read as "extract nothing" would be
indistinguishable from an unconfigured module for as long as nobody checked.

---

## 3. `.sextantignore`

> **Amendment (2026-09-02, Phase 2K design §2 — approved, Task 2 delivered).** What ships
> is narrower than the rest of this section describes, in three ways:
>
> - **Root-level file only.** Not "files cascade, nearest first" — a nested per-directory
>   `.sextantignore` is a stated fast-follow, not read today. One file, at the repository
>   root, and every pattern in it is matched against a path made relative to THAT root —
>   never to whatever resource or schema root a given walk happens to start from.
> - **The JVM subtlety below does not apply.** The extractor's `.class` walk is out of
>   scope (ledgered, rarely wanted); `.sextantignore` governs the Python-side file
>   enumerations only — config readers, schema readers, resource walks, and the
>   enrichment jail (2K Task 5) — never a resolution back through a compiled class's
>   source attribute.
> - **The built-in set is the list in "Built-in defaults" below, amended.** See that
>   subsection's own amendment note for the actual set — it neither contains nor omits
>   quite what this section originally specified.
>
> What ships as written: git's own wildmatch semantics via the `pathspec` package
> (negation, dir-only patterns, anchoring, `**` — mirroring git exactly rather than
> hand-rolling it, DR-6's drift-trap argument), the exclude-entirely behaviour below, and
> the two-layer safety rule — built-in patterns are **non-negatable**: a repo
> `.sextantignore` carrying `!.env` re-admits nothing, because the built-in layer is
> never given that line to evaluate against. Within the repo's own patterns, full
> gitignore semantics apply, negation included. `domain/ignorefile.py`
> (`IgnoreRules.load(repo_root)` / `.matches(path)`) is the one matcher, applied at every
> walk site.

Version-control ignore syntax, because nobody should have to learn a second one: glob
patterns, `!` to re-include, a leading `/` to anchor, `**` to cross directories. A file in
a subdirectory applies to that subtree. Files cascade, nearest first.

It excludes paths from **analysis entirely** — no facts, no module discovery, no coverage
expectation.

### The JVM subtlety

Sextant reads class files, not source. So an ignore rule written against a source path is
applied by resolving each class file back to its source through the class file's source
attribute.

**Where that resolution fails, the class is still analysed.** This is a coverage question,
not a leak, because redaction has already run over its values. `module status` counts the
classes whose ignore rules could not be applied, so the gap is visible rather than assumed
away.

### Built-in defaults

> **Amendment (2026-09-02, Phase 2K design §2 — approved, Task 2 delivered).** The actual
> set, `domain/ignorefile.py`'s `BUILTIN_PATTERNS`: `.env`, `.env.*`, `*.pem`, `*.p12`,
> `*.jks`, `id_rsa*`, `id_ed25519*`, `**/secrets/**`, `*.keystore`. Differences from the list
> below: `*.key`, bare `credentials`, `.git/` and build-output directories are NOT
> built in (a repo names them in its own `.sextantignore` if it wants them excluded);
> `.env.*`, `id_ed25519*` and `**/secrets/**` are added. The secrets pattern was spelled
> `secrets/**` until 2K Task 5 fix round 5: a pattern containing a slash is anchored to
> the repository root, so it protected only a `secrets/` directory sitting AT that root
> and missed `mod/secrets/` in a module one directory down. `**/` restores the
> every-depth matching every other built-in gets for free from being slashless. Section 1's rule against excluding
> `.env`/`application*.yml` is **retracted for `.env` specifically** — see below.

`*.pem`, `*.key`, `*.p12`, `*.jks`, `*.keystore`, `id_rsa*`, `credentials`, `.git/`, and
common build output directories that are not the module's own.

**`.env` and `application*.yml` are deliberately absent from that list.**

> **Amendment (2026-09-02, Phase 2K design §2 — approved, Task 2 delivered).** `.env` IS
> in the built-in set that ships — Task 2's binding context named it explicitly, over
> section 1's own instinct-is-a-trap argument. The two rules do not actually conflict:
> section 1 is about `application.yml`, the file that carries the placeholder values the
> endpoint catalog resolves against, and that file is still never excluded by anything
> built in. `.env` is dotenv-format shell/process environment material — Spring does not
> read it as a configuration source at all, so excluding it costs the catalog nothing,
> while a leaked `.env` is exactly the shape of secret this section exists to keep out.
> `application*.yml` remains outside the built-in set, unchanged.

---

## 4. Redaction

> **Amendment (2026-09-02, Phase 2K design §1 — approved).** The rest of this section
> describes redaction as it was designed to run: inside [M03](M03-scanner.md), before a
> fact is written. **What ships runs at the EXITS instead** — the rendered document, the
> exported bundle, and (2K Task 5) the enrichment tools' read path. The reason is
> `resolved_config`: analysis needs the real values locally, because peer resolution
> substitutes real addresses into endpoint expressions, and a workspace of masked values
> is a workspace that cannot answer. The analyst's own disk is not the trust boundary; the
> document and the bundle are. Four consequences, all live:
>
> - **The marker is `«redacted»`**, one stable literal with no pattern class in it — a
>   masked value still counts as present and still compares equal across runs. The
>   `<redacted:key_pattern>` form below is not what is written.
> - **The workspace stays verbatim** — the tables, `raw_facts`, and the local fact files
>   alike — so a document's own `redaction_set_hash` is `sha256:none` and the cache-key
>   paragraph below describes a mechanism nothing needs: changing the rule set changes the
>   next EXPORT, with no re-extraction at all.
> - **The bundle masks everything that leaves**, `facts/` included: a `config_entry`
>   payload's value is masked by its own `key_path` through the same rules
>   `resolved_config` gets ([D06](D06-bundle-format.md) §3 lists the exact coverage and the
>   one residual).
> - **`redaction_set_hash` is produced by the exporter**, beside `catalog_hash`, and names
>   the effective set that masked those bytes ([D06](D06-bundle-format.md) §3).
>
> Section 2a below states the per-module `redact:` key that widens the set. Everything else
> in this section — the two strategies, the built-in key patterns, and the
> widen-never-narrow rule — ships as written.

Runs **inside [M03](M03-scanner.md), before a fact is written.** Not at load, not at
render.

A value that reaches a fact file has already been written to disk and may already be inside
a published bundle. Removing it afterwards means rewriting the workspace and every bundle
that left the machine. There is no second chance, so there is only one place this can
happen.

### Two strategies, because one is not enough

| Where | Strategy | Why |
|---|---|---|
| Configuration entries | **By key name** | `spring.datasource.password` is redacted whatever its value looks like. Far more reliable than trying to recognise a password by shape. |
| String literals and constants in code | **By value pattern** | The key name is unavailable; the value is all there is |

**Key patterns** (built-in): any key whose final segment matches `*password*`, `*secret*`,
`*token*`, `*credential*`, `*private-key*`, `*apikey*`, `*api-key*`, case-insensitively.

**Value patterns** (built-in): private key blocks, cloud provider access keys, JSON web
tokens, and connection strings carrying a password component.

### The mark a redaction leaves

A redacted value is replaced, never removed, and the fact records that redaction occurred
and which pattern class matched — never the value.

```
value: "<redacted:key_pattern>"
```

**This matters for correctness, not only tidiness.** A configuration placeholder that
cannot be resolved *because its value was redacted* is a different finding from one that is
missing. Without the mark, the endpoint catalog reports the wrong reason, and somebody goes
looking for a configuration entry that is there.

### The pattern set is part of every cache key

Adding a pattern later does not clean facts already written. So the hash of the effective
pattern set is stored on each document ([D00](D00-fact-schema.md)) and is part of the cache
key. Changing the set invalidates the affected facts and forces re-extraction, which is the
only behaviour that actually applies a new pattern.

---

## 4a. `--allow-resolve` — one flag, every network escape

Sextant's default is offline everywhere. One flag, with one meaning, opens the network, and
its use is always recorded in `state.json`:

| Refusal it lifts | Where |
|---|---|
| Build-tool dependency resolution | [M02](M02-detector.md) |
| Remote OpenAPI `$ref` targets | [M03](M03-scanner.md) |

Anything fetched under the flag is cached in `~/.sextant/cache/` and its **content hash is
recorded as an input** — a remote document is an input Sextant does not control, so a
change in it must surface as a change, never be silently absorbed. Without the flag, each
refusal is a reported gap naming what was refused and what is incomplete because of it.

---

## 4b. The enrichment agent — the jail, four tools, and two doors

`sextant module enrich` (2K design §3/§4) composes a brief from a rendered module and hands
it to a model through the `EnrichmentAgent` port (`application/ports/enrichment.py`:
`run(self, brief: EnrichmentBrief, executor: ToolExecutor) -> EnrichmentAnswers`) — the
`executor` parameter is the seam that makes "our code serves the bytes" true: the adapter
drives whatever loop its runtime uses, but every tool call it makes runs through this same
`ToolExecutor`, never a call the foreign runtime services itself. The one adapter that
ships, `tradewind` (`src/sextant/agents/tradewind.py`, 2N design §1 — it replaced 2K's
`claude-api`), lives in `agents/` — a new outer group, sibling to
`ingress`/`storage`/`egress`, importing `application`/`domain` inward and nothing else
outward. It drives the user's Tradewind library through its public client, and it is the
**only** file in the codebase permitted to import `tradewind`, enforced by a structural
test, mirroring how the `protobuf`/`graphql-core` dependencies are each confined to the one
component that understands their format (§Dependencies, [README.md](../../README.md));
`anthropic` is importable nowhere (it remains installed only as Tradewind's own transitive
dependency). Two auth modes, selected explicitly by `--auth`, never guessed:
`subscription` (the default) runs Tradewind's claude backend — the machine's logged-in
Claude Code, whose engine disables its own built-in dev tools so only the four jailed tools
below exist, and which APPENDS the enrichment instructions to its preset persona rather
than replacing it — and `api-key` runs the langchain backend, where
**`ANTHROPIC_API_KEY` is read from the environment alone** — never a flag, never a config
file — and its absence refuses loudly, naming the variable, before any client is built.
The api-key path persists Tradewind's session mirror to
`<module>/.tradewind/sessions.sqlite` (an audit log: re-analyze does not clear it, export
never copies it, and `.tradewind/` is a jail-specific exclusion — the model must not read
its own prior conversation); the subscription path configures no store at all, because the
engine keeps its own native record.

**The jail is what makes the call safe to run against a real repository.** The model gets
exactly four read-only, in-process tools (`application/enrich/tools.py`'s `ToolExecutor`) —
`list_dir`, `find`, `grep`, `read_file` — and nothing else: no shell, no network, no write.
Every call is checked against an explicit allowlist of roots (the module's own source, its
fact root, its rendered outputs) with no exception:

- **A symlink is never followed, anywhere in the walk** — not `root` itself, not an
  intermediate directory, not the final target — even one that resolves back inside the
  jail to a file readable directly under its real name. A path is visible only under the
  exact, case-included spelling of a real directory entry.
- **`.sextantignore` and its built-ins apply at the jail exactly as they do at every other
  walk site** (§3): an excluded file is invisible to `list_dir`/`find`/`grep` and unreadable
  by `read_file`.
- **A derived-output directory** (`target/`, `build/`, `out/`, `node_modules/`, `.git/`) is
  excluded the same way, as a jail-specific rule — not added to `.sextantignore`'s built-in
  patterns, which stay the short, non-negatable credential layer §3 describes. The jail
  describes human-authored source, never its compiled shadow; an ordinary `analyze` walk is
  unaffected.
- **Redaction-on-read.** A config-bearing file's content, and a fact file's own
  `config_entry` value, are masked by the §4 redactor before either `read_file` or `grep`
  exposes them — the same rule set the rendered document and the bundle apply, so a value
  neither of those two exits would show is not recoverable through the jail either.
- **Sextant's own prior `.sextant-enrichment.json`** is excluded as a jail-specific rule too:
  the model must never read a previous run's own claims back as if they were source.

Every tool result — including a refusal — additionally has the module's own absolute path
and the analyst's home directory rewritten to relative and `~`-prefixed spellings before it
reaches the model, so neither ever appears as a raw host path in a transcript a person later
reads.

**Two doors bypass the model call entirely, and Sextant validates either identically.**
`--dry-run` writes the composed brief and calls no agent — any tool at all, Codex, Cursor, a
human with an editor, can answer it under its own abilities. `--ingest answers.json` reads a
file already answered and runs it through the exact same validation-by-construction
(`application/enrich/validate.py`) a live run's answer gets, writing the identical overlay
shape. Supporting a new external tool costs zero changes to Sextant.

> **The external-door honesty note, stated rather than assumed.** The jail and redaction
> guarantees above are enforceable only when Sextant's own loop is the one making the tool
> calls. `--dry-run`/`--ingest` are the external path: whatever answered the brief did so
> outside Sextant's process, under **its own** permissions, which the jail has no reach
> into — Sextant runs the identical validation over what comes back, but what an external
> agent actually read is outside its control. This is not a gap to close: it is the user's
> own tool under the user's own control, the same stance
> [DR-2](../ARCHITECTURE.md#dr-2--no-language-model-inside-sextant)'s original
> external-skill design took, carried forward into the door that replaces it. The same note
> appears in [README.md](../../README.md), where a reader is more likely to meet it first.

## 5. Scanner selection

Multiple scanners may accept one language, and Sextant must be able to prefer a better one
later without any other change.

Each scanner declares `accepts`, `capabilities` and `rank`. **Selection picks the highest
rank among those accepting the language**, unless configuration pins one.

**One scanner per language per run.** Two scanners writing facts for the same file
reintroduces cross-tier reconciliation, which is the defect this architecture was shaped to
avoid. Artifact readers are not competing scanners and are unaffected.

Switching scanners invalidates the cache, because `scanner_id` and `scanner_version` are
both on the document record.

---

## 6. What configuration must not control

- **Nothing that changes what is true.** Configuration selects scope, tools and
  presentation. It cannot make a `narrowed` edge `resolved`, or switch off an honesty
  report.
- **Redaction cannot be disabled**, and a repository cannot remove a built-in pattern.
- **No framework behaviour.** That is [D02](D02-catalog-schema.md). Configuration may add a
  catalog; it may not describe one inline.
- **No language branching.** Configuration never says "for Java, do X."

---

## 7. Open decisions

| Decision | Blocks |
|---|---|
| Whether high-entropy detection is worth the false positives, alongside pattern matching | The value-pattern set |
| Whether `workspace.location` supports a central cache keyed by path and commit, or only in-module | M00 and M08 |
| Whether an ignore rule can be written against a symbol rather than a path | M03 |
