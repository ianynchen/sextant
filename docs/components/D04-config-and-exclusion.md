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

## 2a. `.sextant.yml` beside a module — opt-in library extraction

A third file, owned by neither of the two above: it sits **beside one module's build file**,
because what it declares is a property of that module and of nothing else.

```yaml
# fixtures/orders-service/.sextant.yml
extract_libraries:
  - com.example:orders-soap-client
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
this mechanism existed, byte for byte.

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

**A malformed `.sextant.yml` fails the run** — the one input where Sextant refuses rather
than degrading. DR-6's refusal-to-guess governs evidence read out of a codebase Sextant
does not own, where an honest absence is the right answer. This file is an instruction
written *for* Sextant, and a misspelled key that read as "extract nothing" would be
indistinguishable from an unconfigured module for as long as nobody checked.

---

## 3. `.sextantignore`

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

`*.pem`, `*.key`, `*.p12`, `*.jks`, `*.keystore`, `id_rsa*`, `credentials`, `.git/`, and
common build output directories that are not the module's own.

**`.env` and `application*.yml` are deliberately absent from that list.** See section 1.

---

## 4. Redaction

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
