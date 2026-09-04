# Documented but not implemented

**Status: a factual register, opened 2026-09-04 during Phase 2O; entries #1, #2, #3 and #6
updated the same day when Task 6 built what it needed rather than citing it.** Every entry
below was verified in the code at the time of writing — not inferred from a
document. Each names where it is documented, what the code actually does, the
impact, and its disposition.

**Why this file exists.** Phase 2O's spec was written against two mechanisms
this repository documents and has never implemented, and four rounds of
adversarial review did not catch it — because the reviewer read the same
documents the author did and cited the same lines back. A shared false premise
survives review; only execution exposed it. Every entry here was found the same
way: something tried to *use* the mechanism.

The lesson generalises: **for this codebase, a document is not evidence that a
mechanism exists.** A spec that depends on one must verify it in `src/` first.

---

## The register

| # | Mechanism | Documented in | What the code does | Disposition |
|---|---|---|---|---|
| 1 | `detect:` / `detect.coordinates` | D02; declared by every shipped catalog | **PARTLY CLOSED, 2O Task 6.** Now on the `Catalog` model and read by the loader, and it GATES the one style whose framework rule is conditional on the library (`derived_resource`, via `application/resolve/dependencies.py`). The MODULE-WIDE catalog activation D02 §12 describes is still not implemented — applied today it would deactivate `spring-mvc.yml` on any Maven module declaring only `spring-boot-starter-web`, because a parsed POM records direct declarations only. | Open, narrowed — needs a resolved classpath under both build systems |
| 2 | `ClasspathEntry` | `domain/facts.py:49` | Still **constructed nowhere**, deliberately (2O Task 6): an entry names a resolved ARCHIVE and its tier, which the Gradle report carries and a parsed POM does not, so filling it from Maven would mean inventing a path. The coordinate half a gate needs is `ModuleFact.dependency_coordinates` instead. | Open — classpath TIERING waits on a resolved classpath |
| 3 | `ModuleFact` | `domain/facts.py:83` | **CLOSED, 2O Task 6.** Written by `application/stages/analyze.py` on every run, carrying the module's identity, kind, languages, roots and `dependency_coordinates`; read back by the `module_dependencies` named query. `classpath` stays empty — entry #2. | Closed (partly: tiering is #2) |
| 4 | `constant` fact kind (`Symbol, value`) | D00 §5 | No `ConstantFact` class. `ClassScanner.visitField` receives ASM's `Object value` — the field's `ConstantValue` attribute — and never reads it. | **Deliberately routed around** in 2O (ruling R11); still unimplemented |
| 5 | `resolves:` / `resolves.direction` with `when: {owner_implemented_in_module: true}` | D02 only | Zero occurrences in `src/`. Contrast `declared_on`, which IS implemented (`derive_endpoints.sql:675`, `engines/annotation_driven.py`). | **2O Task 10** |
| 6 | `default_produces` | D02; 2E's spec and plan | **CLOSED, 2O Task 6.** Read as a TOP-LEVEL catalog key (not under `mapping:`, where D02 first sketched it — the catalog that needed it declares no `mapping` at all) and written into `produces` by `derived_resource`, which refuses a catalog of its own style that declares none. `default_consumes` stays specified-not-used: Data REST negotiates the request side, so no catalog could declare one honestly. | Closed; `default_consumes` open |
| 7 | `root_kind` | D00:181, with a full member list | The token appears **nowhere in `src/`** — not merely the `scheduled` member, the whole concept. | **Open — must be resolved before 2P's Meridian vocabulary is specified** |
| 9 | Routing-ambiguity "finding" | D01:296 — "that collision is a routing-ambiguity finding" | No findings mechanism exists anywhere in `src/`. D01 describes a *property* of content-derived identity (two handlers sharing one wire contract merge into a single row), not a detector that reports anything. Found 2026-09-04 by the mechanism-existence pass, **before** Task 10 was dispatched against it. | Open — 2O Task 10 restated around merge precedence |
| 8 | Rung 5 marker semantics | D02: markers are "package families whose presence **anywhere in the module** is evidence" | Code read annotation FQNs only — narrower than documented. | **CLOSED, 2O Task 2** |

---

## Impact, calibrated

These are not uniform, and treating them as one severity would be wrong.

**One produces wrong output today.** #5: a module that locally *implements* an
`@HttpExchange` interface (legal since Spring 6.1) has an **outbound row
fabricated** — Sextant reports it calling itself — and its **inbound routes
missed entirely**. Two errors in the same rows. Narrow in reach, because
server-side `@HttpExchange` is less common than client-side, but it is the only
entry where shipped output is actively false rather than merely thin.

**Three under-report.** #8 left Jackson-bearing modules `unresolved` where the
framework guarantees JSON (now fixed). #6 left format unresolved where a
framework contract is certain (now fixed). #1 meant no catalog could report
*"skipped: the framework is not present"* — **one now can**, and does: the
manifest names `spring-data-rest` with the reason whenever the module's build
does not declare Spring Data REST, or when the question cannot be answered at
all. Every other catalog still evaluates against every module, always.

**Three blocked or reshaped work.** #2/#3 meant no dependency-aware reasoning
existed anywhere; 2O Task 2 fell back to `documents.origin`, which covers only
opt-in extracted libraries. **#3 is now closed** — the module fact is written and
carries the build's declared coordinates — so a later pass could widen that
fallback (`resolve/format.py`'s rung-5 coordinate marker is the obvious
candidate); Task 6 did not, because widening a format rung was not its change.

#4 makes a compile-time constant's *value*
unreachable from field facts — mitigated in practice because JLS 13.1/13.4.9
requires javac to inline such constants at their use sites, so the literal
appears in `call_site` facts, but a constant declared and never used in its own
module stays invisible.

**One is a live risk to the NEXT phase.** #7: the Meridian integration scoped
into 2P specifies a boundary vocabulary derived from D00/D01/D06. `root_kind`
is documented in D00 with a full member list and does not exist in the code. A
vocabulary specified from those documents the way 2O's spec was would be built
against fiction, and the failure would surface at a *consumer* rather than in
our own tests.

---

## Preventing recurrence

Fixing eight instances does not fix the mechanism that produced them. Two
proposals, cheapest first:

1. **An architecture test that cross-checks documentation against code.** The
   two highest-value checks: every catalog key D02 declares must be read by
   `yaml_source.py` (or be explicitly listed as reserved-not-yet-read), and
   every fact field D00 declares must exist on the corresponding
   `domain/facts.py` model. Both are mechanical, and either would have caught
   #1, #4 and #7 the day they diverged.
2. **A convention for reserved vocabulary.** Where a document deliberately
   describes something ahead of its implementation, it says so in the document,
   in a form the test above can read. "Specified here, not yet used" (#6) is
   already exactly this — it was honest, and it is the model. The failure mode
   is silence, not intent.

---

## The check that works, demonstrated

Entry #9 was found by grepping `src/` for every mechanism the remaining tasks
cite — minutes of work, and it landed *before* a task was dispatched against a
detector that does not exist. The same pass applied at spec-writing time would
have caught six of the first eight.

This is worth stating because the alternative was tried and failed: **four
rounds of adversarial spec review did not catch entries #1 or #4**, because the
reviewer read the same documents the author did and cited the same lines back.
A shared false premise is invisible to review. It is only visible to a grep.

## Rule for future specs

**Before a spec cites a mechanism as shipped, grep for it in `src/`.** Phase
2O's own experience is the argument: two phantom mechanisms, four adversarial
review rounds, and neither the author nor the reviewers caught it, because all
of them were reading the same documentation.
