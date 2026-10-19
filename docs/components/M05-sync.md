# M05 — Sync

## Purpose

Assemble the participant set for a system.

## Interface

```
Sync
  resolve(manifest, state) -> ParticipantSet
```

## Inputs

`system.yml` and `system.state.json` ([D05](D05-manifest-and-state.md)). Git remotes, for
staleness only. Bundles ([D06](D06-bundle-format.md)) produced by [M08](M08-exporter.md) in
**earlier, separate runs** of the service pipeline.

This is the only edge in the design that crosses between pipeline runs, and it is why a
bundle must be self-describing.

**Amendment 2026-10-19 (user decision 1, spec `2026-10-19-reactor-linking-design.md`): THIS
module is not the only way a participant set can be assembled, and it is not the one built
first.** A Maven reactor is a participant set that needs no manifest to discover: the
`<modules>` walk `module analyze` already makes names every participant, and each module's
own workspace holds its graph. `system analyze <reactor root>` uses that, with no
`system.yml`, no `system.state.json` and no staleness — one build has no commits to be stale
against.

**What that path gives up, stated here rather than left to be discovered:** the
cross-repository case, which is this module's whole subject. Participants in separate
repositories at separate commits need the manifest, the state file and the staleness rule,
and the reactor path answers none of them. This module stays `planned` and specified.

## Output

The `ParticipantSet`: every service with its bundle, resolved commit and staleness; every
external participant; the alias index; and refusals.

## Behaviour

### It fetches. It does not build.

Sync never runs the service pipeline. Analysing a module needs a build, a JDK, and possibly
credentials, and burying that inside a system command is surprising — it would also make
this module untestable without a toolchain.

**The convenience lives in [M00](M00-cli.md)**, where `system analyze --refresh-stale`
composes the two pipelines explicitly. Orchestration belongs in the composition root.

### Staleness is per module, not per repository

A monorepo holding `shipping` and `billing` makes both look stale the moment either changes.
The right comparison is the last commit touching that module's own path — but **history
cannot be walked without fetching it**, and `git ls-remote` returns refs only. So two phases:

```bash
# Phase 1 — one line from the server
git ls-remote <repo> <branch>
#   unchanged -> not stale, done. The common case.

# Phase 2 — only when the head moved AND the repo holds several modules
git clone --filter=blob:none --no-checkout <repo>
git log -1 --format=%H -- services/shipping
```

A blobless clone fetches commits and trees but no file contents — enough for the question, a
fraction of a full clone. A single-module repository never reaches phase 2, because the head
moving *is* the module changing.

Where a server does not support partial clone, the fallback is head comparison, and the
resulting over-reporting is **stated rather than hidden**.

**In continuous integration none of this runs.** The service pipeline already has a clone, so
`module_commit` is computed at scan time and travels in the bundle; the system tier compares
bundles.

### The alias index

Aliases from `system.yml`, plus those a module's own artifacts declare — a Kubernetes
Service name, a `spring.application.name`, an artifact id — read from the bundle's
deployment facts **for the system's environment only**. Deployment facts are
per-environment (Helm renders every values file), and a Service name that exists only in
the development overlay must not resolve calls in a production system map.

| Source | Treatment |
|---|---|
| Declared in `system.yml` | Applied |
| Declared by the module's own artifacts | **Applied.** The module is stating its own name; this is evidence, not a guess. |
| Inferred by similarity | **Proposed**, never applied |

This index is what lets [M06](M06-stitcher.md) resolve `http://orders-svc:8080/...` to the
`orders` participant. Without it that call is unresolved even though the manifest that
proves the name was already read.

### Refusals and warnings

| Condition | Action |
|---|---|
| Two services claim one alias | **Refuse.** Every match through that name is ambiguous, and picking one silently produces a wrong architecture. |
| Bundle schema incompatible with this Sextant | **Refuse** |
| Bundles disagree on schema version | **Refuse.** Mixed vintages produce a wrong graph with no error. |
| Catalog hashes differ between bundles | **Warn.** Endpoint coverage differs between participants, so a missing link may be a coverage gap rather than an absence. |
| A bundle is marked partial | **Warn**, and propagate `partial` to every document derived from it |
| **A declared service has no bundle** | **Refuse by default** — see below |

### The missing participant

This is the failure most easily got wrong, so it is stated separately.

If `orders` is declared and has no bundle, every call into it appears as an **unmatched
outbound endpoint** — which reads as an undocumented dependency rather than as *we did not
look*. On a diagram those two are indistinguishable, and only one of them is a finding about
the architecture.

So a missing participant is refused by default. `--allow-missing` proceeds and marks the
participant **explicitly absent**, so that its unmatched calls are attributed to the gap
rather than to the architecture.

## What it must not do

- **No building.** No `module analyze`, no compilation, no dependency download.
- **No cloning.** Staleness uses remote refs. A bundle is fetched, not a repository.
- **No matching.** Endpoints are [M06](M06-stitcher.md)'s concern; Sync produces the set to
  match over.
- **No writing to `system.yml`.** State goes to `system.state.json`, so a scan never
  dirties a hand-written file, never loses its comments, and never collides when two people
  scan different services.
- **No silent substitution.** A stale bundle is used only when the run says stale bundles
  are acceptable, and the fact travels with the result.

## Honesty obligations

- Every stale participant, with how many commits behind.
- Every missing participant, distinguished from a participant with no links.
- Every refusal, naming the bundles and the versions involved.
- Aliases applied from module artifacts, so a link's evidence chain is followable.
- Aliases proposed but not applied, written to `proposals.yml`.

## Open decisions

| Decision | Blocks |
|---|---|
| Whether `system.yml` may name a bundle directly, for a service analysed elsewhere | [D05](D05-manifest-and-state.md) |
| Whether bundles are fetched from a store, or expected on local disk | [D06](D06-bundle-format.md) |
| Whether staleness needs network access at all, or can rely on recorded commits | Offline use |
| Whether `--allow-missing` is per-service or global | M00 |
