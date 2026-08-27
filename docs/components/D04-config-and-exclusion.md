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
