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
  "module": { "id": ":services:orders", "kind": "service", "languages": ["java", "kotlin"] },
  "provenance": { "commit": "a3f91c…", "generated_at": "…", "sextant_version": "0.4.0",
                  "scanners": [{ "id": "sextant-jvm-extractor", "libraries": ["…"] }] },
  "coverage": { "sources": 1283, "covered": 1283, "uncovered": 0, "partial": false },
  "resolution": { "resolved": 0.71, "narrowed": 0.22, "partial": 0.04, "unresolved": 0.03 },
  "gaps": ["call_graph_not_implemented"],
  "endpoints": { "inbound": { "http": 8, "kafka": 3, "grpc": 1 },
                 "outbound": { "http": 5, "kafka": 2 } },
  "query": ["sextant endpoint list --scope module", "sextant symbol impact <symbol>"]
}
```

Three things earn their place. **`provenance.commit`** lets a reader compare against `HEAD`
and see for itself that the file is stale — a generated document that hides its age is
worse than none. **`coverage` and `resolution`** say how much of this to trust.
**`gaps`** names what Sextant knowingly did not do, so a catalog that is complete-looking
and incomplete cannot pass as complete.

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
