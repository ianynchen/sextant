# D05 — Manifest and state

What a system is, and what Sextant remembers about a run. `system.yml` is written by
people; the rest is written by Sextant. Read by [M05](M05-sync.md) and
[M06](M06-stitcher.md).

The governing rule: **a file a person edits is never rewritten by Sextant.** Intent and
state live in separate files, so a scan never dirties a hand-written file, never loses its
comments, and never collides when two people scan different services.

---

## 1. `system.yml` — written by a person

```yaml
version: 1
name: order-platform
environment: prod

services:
  - name: orders
    aliases: [orders-api, ORDERS-SERVICE, acme-orders]
    repo: git@github.com:acme/acme-orders.git
    branch: main

  - name: shipping
    aliases: [shipping-svc]
    repo: git@github.com:acme/monorepo.git
    branch: main
    module: ":services:shipping"

external:
  - name: stripe
    hosts: ["api.stripe.com"]
```

| Field | Why it is there |
|---|---|
| `name` | **The name in every diagram and document.** Module identifiers come from build coordinates and are ugly; a person chooses this one. |
| `aliases` | Not documentation — **matcher input.** A Feign client naming `orders-api` links to this service only because something says the two are the same. |
| `repo`, `branch` | Intent. The commit is resolved and recorded in state, never here. |
| `module` | Required when a repository holds several modules |
| `environment` | Named **once**, at the top |
| `external` | Named participants outside the analysed set |

### Environment is a property of the system, not of a chart

The same twelve services wired with development values and with production values are two
different systems: different hostnames, different topics, sometimes a service that is
switched off entirely.

So **a system analysis is always of exactly one environment**, and this field settles what
had looked like a Helm question. Rendering a chart with that environment's values is
following an instruction rather than making a guess.

### Two hard errors

**An alias claimed by two services** makes every match through that name ambiguous.
[M05](M05-sync.md) refuses to proceed rather than choosing.

**A service with no bundle** is not the same as a service with no links, and on a diagram
the two look identical — every call into it appears as an unmatched outbound endpoint,
which reads as an undocumented dependency rather than as "we did not look."

---

## 2. `system.state.json` — written by Sextant

```json
{
  "graph_schema_version": 2,
  "sextant_version": "0.4.0",
  "resolved_at": "2026-08-27T09:14:22Z",
  "environment": "prod",
  "services": {
    "orders": {
      "commit": "a3f91c…", "module_commit": "a3f91c…", "scanned_at": "…",
      "bundle": "s3://sextant/orders@a3f91c",
      "producer": { "sextant_version": "0.4.0", "fact_schema_version": 2,
                    "graph_schema_version": 2,
                    "scanners": [{ "id": "sextant-detector" },
                  { "id": "sextant-jvm-extractor",
                    "libraries": ["org.ow2.asm:asm:9.10.1"] }],
                    "catalog_hash": "…", "redaction_set_hash": "…" },
      "stale": false
    },
    "shipping": { "commit": "7b2e40…", "module_commit": "3c8d1f…",
                  "bundle": "…", "stale": true, "behind_by": 4 }
  }
}
```

**`bundle` is a location, not a label.** Under federated system queries
([D01](D01-graph-schema.md)), the bundles are read at **query** time, not only when the
system was stitched. A bundle that has moved or been deleted must fail with a message naming
it, never return a shorter answer.

**`producer` records what made each bundle**, copied from its manifest. Two services built
by different Sextant versions can produce a system graph that is wrong with no error, and
this is the record [M05](M05-sync.md) refuses on.

**`commit` and `module_commit` are different.** The first is the repository head at
resolution; the second is the last commit that touched this module's own path. In a monorepo
they diverge, and the second is what staleness compares.

### Staleness is computed per module, in two phases

A monorepo holding `shipping` and `billing` makes both look stale the moment either changes.
The repository head is the wrong comparison; the right one is the last commit that touched
that module's own path.

But those two facts pull in opposite directions, because **`git ls-remote` returns refs, not
history** — and per-path history cannot be walked without fetching it. So:

```bash
# Phase 1 — one line from the server, no history
git ls-remote <repo> <branch>
#   head unchanged  -> not stale. Done. This is the common case.
#   head moved      -> phase 2

# Phase 2 — history metadata without file contents
git clone --filter=blob:none --no-checkout <repo>
git log -1 --format=%H -- services/shipping
```

**Phase 2 needs two conditions at once**: the head moved, *and* the repository holds more
than one module. A single-module repository skips it entirely, because the head moving is the
module changing. So the expense lands only where it buys something.

A blobless clone fetches commits and trees but not file contents, which is enough for the
question and a fraction of a full clone. Where a server does not support partial clone, the
fallback is repository-head comparison, and the resulting over-reporting is stated rather
than hidden.

**In continuous integration this never runs.** The service pipeline already has a clone, so
`module_commit` is computed locally at scan time and travels in the bundle; the system tier
compares bundles, not repositories.

---

## 3. `metadata.json` — what a module *is*

Written by [M04](M04-resolver.md) **as the final act of `analyze`**, atomically, into the
workspace. This is the file an agent reads — so its invariant is: *it exists if and only if
the workspace exists, and it always describes the graph beside it.* Tying it to `render`
would leave it absent or stale whenever nobody happened to render, which is exactly the
failure the file exists to prevent. It is the sibling of the bundle manifest
([D06](D06-bundle-format.md)): same information, both stamped by the pipeline that computed
it, never by presentation.

```json
{
  "schema_version": "1.0.0",
  "boundary_vocabulary_version": 1,
  "catalog_hash": "…",
  "module": { "id": ":services:orders", "kind": "service", "languages": ["java", "kotlin"] },
  "provenance": { "commit": "a3f91c…", "generated_at": "…", "sextant_version": "0.4.0",
                  "scanners": [{ "id": "sextant-jvm-extractor", "libraries": ["…"] }] },
  "coverage": { "sources": 1283, "covered": 1283, "uncovered": 0, "partial": false,
                "reach": { "body_read": 465, "boundary": 971 },
                "resolution": { "resolved": 1434, "narrowed": 2 },
                "method_resolution": { "declared_here": 191, "owner_not_scanned": 320 },
                "format_unresolved": 3, "inbound_total": 12,
                "peer_unresolved": 1, "outbound_total": 7 },
  "gaps": ["call_graph_not_implemented"],
  "skipped_catalogs": [{ "catalog_id": "spring-webclient", "missing_capabilities": ["string_constants"],
                         "feeds": ["dependency"], "cause": "missing_capability" }],
  "catalogs_run": { "endpoint": 12, "dependency": 4, "data-contract": 9, "schedule": 1 },
  "observability": { "boundary_vocabulary_version": 1,
                     "kinds": { "endpoint": { "verdict": "observable", "reasons": [] },
                                "dependency": { "verdict": "partial",
                                                "reasons": ["catalog skipped: spring-webclient (string_constants)"] } },
                     "attributes": { "endpoint": { "format": { "verdict": "partial",
                                                              "reasons": ["3 of 12 formats unresolved"] } } },
                     "stated_boundaries": ["call_graph_not_implemented"] },
  "endpoints": { "inbound": { "http": 8, "kafka": 3, "grpc": 1 },
                 "outbound": { "http": 5, "kafka": 2 } },
  "query": ["sextant endpoint list --scope module", "sextant symbol impact <symbol>"]
}
```

Three things earn their place. **`provenance.commit`** lets a reader compare against `HEAD`
and see for itself that the file is stale — a generated document that hides its age is
worse than none. **`coverage`** says how much of this to trust, and since W38 that is three distributions rather than a file count: `reach` (was the callee's body here at all), `resolution` (did dispatch settle the call) and `method_resolution` (why a lookup missed). *The block used to sit beside `coverage` as a top-level `resolution` of FRACTIONS, with `partial` and `unresolved` members; what ships is counts, nested under `coverage`, and the buckets are each column's own — `resolution` can hold only `resolved` or `narrowed`.* The first two are per EDGE and the third per `(class, name, descriptor)`, so they are not addable.
**`gaps`** names what Sextant knowingly did not do, so a catalog that is complete-looking
and incomplete cannot pass as complete.

**Seven additions serve the boundary vocabulary and the observability map** (spec
[2026-10-22](../superpowers/specs/2026-10-22-boundary-vocabulary-and-diff-design.md), FR-21 to
FR-23), all written by `analyze` and all read by something that runs long after the catalogs
are gone:

- **`boundary_vocabulary_version`** — which generation of the kinds and their
  identity/attribute/evidence split ([D01](D01-graph-schema.md) §3, "The boundary
  vocabulary") the entries a reader derives are named in. `export` copies it into the
  manifest's `producer`.
- **`catalog_hash`** — the identity of the framework knowledge this run used. Until now only
  the exporter computed it, from the catalogs installed at export time, so a workspace had no
  hash of its own to compare, and hashing the catalogs installed NOW would describe the
  diff's machine and not the analysis. `analyze` writes it where the catalogs are loaded;
  `export` copies it and recomputes only for a workspace analysed before this key existed.
  Absent, never a placeholder, where the caller computed none.
- **`catalogs_run`** — `{kind: count}`: how many catalogs that feed each boundary kind
  actually ran on this module. A kind nothing ran for is absent.
- **`skipped_catalogs[].feeds`** — the kinds each skipped catalog would have fed. A catalog's
  `style`, `direction` and whether it declares a shape model (any of `serialization`,
  `nullability`, `known_types`) already say what it writes (D02), so this is a function over
  fields the catalogs carry and not a new declaration; it is recorded because a bundle's
  reader has no catalogs to ask. A catalog that declares no `direction` (the `config_join`
  catalogs `spring-integration` and `spring-kafka-media`) feeds both `endpoint` and
  `dependency`, because its rows are either direction and which is known only per row.
- **`skipped_catalogs[].cause`** — which gate skipped the catalog, a closed set:
  `missing_capability` (the extractor cannot read what the catalog needs), `framework_absent`
  (none of its `detect.coordinates` is in the recorded dependency set — `dependency_source`
  says which set), `dependencies_unrecorded` (no dependency set was recorded to ask) and
  `superseded` (a `detect_superseded_by` coordinate is in the build). Data the map reads, so
  nothing parses the reason in `missing_capabilities`; absent for a skip read back from
  metadata written before the field.
- **`coverage.format_unresolved`, `inbound_total`, `peer_unresolved`, `outbound_total`** — the
  two shares the map's per-attribute verdicts read, measured off the same rows the
  `endpoints` counts use. `inbound_total` counts the rows the `endpoint` kind holds (a `both`
  row included), so outbound rows cannot inflate the format share.
- **`observability`** — per boundary kind, `observable`, `partial` or `not-observable`, with the
  reasons; per attribute only where a measurement names one (`endpoint.format`,
  `dependency.peer`); and `stated_boundaries`, the static `gaps` list repeated as a statement
  about Sextant and never folded into a verdict. It is written LAST, a pure function of the
  dictionary above it (`application/boundary/observability.py`), so the map for a bundle can be
  computed from its manifest alone, and `export` copies it rather than re-deriving it. A
  verdict is `partial` for any reason (uncovered source files, partial documents, a skipped
  catalog that feeds the kind and is a gap, and, for `dependency` and `data-contract` alone,
  `dependency_source: declared`) and `not-observable` only
  where a catalog feeding the kind was skipped as a gap and none feeding it ran. Every skip is
  a gap but one: a skip whose `cause` is `framework_absent` on a classpath the build tool resolved (`dependency_source` `maven` or `gradle`) is not — the framework is simply not used, so there
  is nothing to observe (ruled 2026-10-22). On a `declared` classpath the same absence is not
  proven and stays a reason; a skip with no recorded `cause` is a gap and its reason says the
  cause was unrecorded. `module` and
  `boundary-property` are always `observable`: they are read off files, not derived by a
  catalog that can be skipped. Metadata that predates `catalogs_run` gets `partial` for every
  code-grounded kind with the reason *catalog kinds unrecorded: manifest predates boundary
  vocabulary 1* — a degraded answer that says it is degraded.

There is **no prose** here. Purposes are overlays.

---

## 3a. `modules.json` — the repository's module inventory

Written by [M02](M02-detector.md) at `<repo-root>/.sextant/modules.json`, once per
invocation. Machine-written, gitignored, regenerable from the build.

```json
{
  "repo_commit": "a3f91c…",
  "detected_at": "2026-08-27T…",
  "modules": [
    { "id": ":services:orders",    "path": "services/orders",
      "kind": "service", "languages": ["java", "kotlin"],
      "workspace": "services/orders/.sextant",
      "module_commit": "a3f91c…", "last_analyzed": "…" },
    { "id": ":libs:shared-domain", "path": "libs/shared-domain",
      "kind": "library", "languages": ["java"],
      "workspace": "libs/shared-domain/.sextant",
      "module_commit": "3c8d1f…", "last_analyzed": "…" }
  ]
}
```

This is the one-hop answer to "what is in this repository and where are its workspaces" —
for `module list`, for `--refresh-stale`, for system-tier tooling, and for an agent that has
just opened the repository.

## 4. `state.json` — what Sextant *did*

Bookkeeping for one module workspace. Never read by a person.

```json
{
  "stamp": {
    "sextant_version": "0.4.0",
    "fact_schema_version": 2,
    "graph_schema_version": 2,
    "scanners": [{ "id": "sextant-jvm-extractor",
                   "libraries": ["org.ow2.asm:asm:9.10.1"] }],
    "catalog_hash": "…",
    "redaction_set_hash": "…"
  },
  "environments": ["dev", "staging", "prod"],
  "last_run": { "started": "…", "stages": {"scan": "ok", "extract": "ok", "resolve": "ok"} },
  "allow_uncovered_used": false,
  "allow_resolve_used": false,
  "cache": { "documents": 1283, "reused": 1275 }
}
```

**`stamp` is the rebuild trigger**, and it distinguishes *what* must be rebuilt rather than
always rebuilding everything. A `fact_schema_version` change forces re-extraction, which is
expensive; a `sextant_version` or `catalog_hash` change forces re-derivation only, which is
minutes. The full matrix is in [D01](D01-graph-schema.md) §7.

**Any mismatch rebuilds rather than mixing vintages.** That is what makes per-row version
columns unnecessary: the guard is complete, so a workspace can only ever hold one vintage.

**`environments` lists the profiles this module resolved.** A module analysis is not tied to
one environment — it resolves every profile it finds, and consumers select. See §1.

**`allow_uncovered_used` is recorded, not just acted on.** A partial analysis must remain
identifiable long after the command that produced it.

---

## 5. Which files go in git

| File | In git | Why |
|---|---|---|
| `system.yml` | **Yes** | An input |
| `curations.yml` | **Yes** | An input, and the highest-trust source |
| `sextant.yml`, `.sextantignore` | **Yes** | Inputs |
| `system.state.json` | **Yes**, optionally | Makes an analysis reproducible |
| `metadata.json`, `state.json` | No | Workspace output |
| Facts, graph, rendered documents | No | Output |

The rule is *inputs in git, outputs not* — which is not the same line as *hand-written
versus generated*. `system.state.json` is generated and may be committed, because pinning
it reproduces a past analysis exactly.

---

## 6. Open decisions

| Decision | Blocks |
|---|---|
| Whether `system.yml` supports a bundle reference in place of `repo` and `branch`, for a service analysed elsewhere | M05 |
| Whether `environment` can be overridden per run, or is fixed by the file | M05 and Helm rendering |
| Whether `metadata.json` lists endpoints in full below some count, or always as counts | M07 |
