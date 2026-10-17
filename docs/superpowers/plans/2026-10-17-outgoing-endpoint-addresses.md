# Outgoing Endpoint Addresses — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the rendered `architecture.md` say **where** an outgoing call goes. Today, on
Spring's own reference microservice app, 1 of 6 outbound rows carries a destination and a
gateway's whole route table is missing. This plan takes that to 9 of 10 outbound rows with a
destination, plus 4 new inbound rows.

**The deliverable is the document, not a COVERAGE cell** (user ruling, 2026-10-17). The
Spring Boot *REST outbound* cell is already `✅` — it counts whether a row appears, never
whether the row says anything. So **no task here moves a cell, by design**, and the measure is
the field pins.

**Spec:** `docs/superpowers/specs/2026-10-17-outgoing-endpoint-addresses-design.md` — read the
*What it closes* table, §1 and §2 (the two user rulings) and §5a (what was actually broken, after
four wrong guesses) before Task 1.

**Tech Stack:** Python 3.14, DuckDB, YAML catalogs; Java 21 + ASM for Task 3; `javap` and real
poms for the probes.

## Global Constraints

- **No false positives** (standing user rule). Every ambiguity is `unresolved` with a reason.
  **This plan's specific danger:** it converts blanks into assertions about a real system, so
  every conversion is a new claim. A diff shows movement, not correctness.
- **Read the honest output before theorising about a cause.** `metadata.json`'s
  `dependencies_not_resolved` and `skipped_catalogs` named Task 1's real cause in plain words
  while four plausible theories were being argued. Spec §5a's method note records it.
- **Verify what a task claims to close.** The previous spec's closure list had four false
  entries, caught at its task 13 of 14. Each task below ends by re-running the field pins.
- **The resolve layer names no framework and no language**
  (`tests/architecture/test_source_rules.py`, `test_language_confinement.py`). Task 4's
  framework knowledge lives in a catalog with a probe, never in `resolve/`.
- **Every framework claim carries a probe with §5.4 provenance**
  (`tests/architecture/test_probe_provenance.py`): a generated table, the version read back
  from the run's own output, never from a parameter.
- **Existing output moves only in the task that says so**, and the pins that fix it move in
  that same task.
- **No worktrees** (GUIDELINES §13.9). **New branch** — not PR #40, which carries the previous
  spec's close-out.
- **The gate is** `JAVA_HOME=/Users/yining/.gradle/jdks/eclipse_adoptium-21-aarch64-os_x.2/jdk-21.0.12.1+1/Contents/Home bash scripts/check.sh`
  — run it whole, read the exit code, never pipe it through `tail`.
  `scripts/check.sh --guards` runs the mutation guards. **Five `tests/cli/test_app.py` failures
  are pre-existing** (this machine's offline Maven; CI on #39 passed on the same five).
- **Match the surrounding style** (GUIDELINES §3, §13.5); do not refactor adjacent code.

---

## File Structure

| file | responsibility |
|---|---|
| `src/sextant/ingress/detect/maven.py` | Task 1 — `_interpolated` built-ins, `_managed_versions` reporting |
| `src/sextant/catalogs/spring-cloud-gateway-properties.yml`, `spring-cloud-gateway.yml` | Task 1 — the 5.0.0 starter coordinate |
| `scripts/probes/cp35_bom_chain/` | **new** — Task 1's measurement |
| `src/sextant/application/resolve/values.py` | Tasks 2, 4 — the `concat` arm, then the peer arm |
| `extractor-jvm/src/main/java/dev/sextant/extractor/MethodFlow.java` | Task 3 — `fieldWrites` carrying a constant |
| `docs/components/D00-fact-schema.md` | Task 3 — the widened `field_write` |
| `src/sextant/application/resolve/shapes/arguments.py` | Task 4 — `peer` and `path` from separate evidence |
| `src/sextant/catalogs/spring-cloud-discovery.yml` | **new** — Task 4, `getInstances` names a peer |
| `scripts/field-expectations/petclinic-*.json` | every task — the pins that must move |

---

## Task 1: Versions through the BOM chain, and the gateway's route table · **DONE 2026-10-17**

**8 rows — the largest single win, and it needs no ruling.** Both causes are already proven end
to end (spec §5a): a throwaway patch took `api-gateway` from 6 endpoints to 14, every missing
row `resolved`. This task re-does that properly, with the reporting fix the silent drop deserves.

**Files:**
- Modify: `src/sextant/ingress/detect/maven.py` (`_interpolated` ~:151, `_managed_versions` ~:773)
- Modify: `src/sextant/catalogs/spring-cloud-gateway-properties.yml:15`, `spring-cloud-gateway.yml`
- New: `scripts/probes/cp35_bom_chain/{run.sh,README}` + `scripts/probes/cp35_bom_chain.md`
- Test: `tests/ingress/test_maven_detector.py`, `tests/architecture/test_probe_provenance.py`
- Pins: `scripts/field-expectations/petclinic-api-gateway.json`

**Interfaces:**
- Consumes: poms from the local repository, as today.
- Produces: `dependency_versions` entries that were previously dropped, and a
  `dependencies_not_resolved` message where one still cannot be settled.

- [x] **Step 1: The probe first, because the claim is about other people's poms**

`scripts/probes/cp35_bom_chain/run.sh` GENERATES its table — walking from
`spring-cloud-dependencies` and reporting, per dependency, the BOM that manages it, the hop
count, and the raw version string. The version column header is read back from the run's own
output (the BOM version it actually opened), never from a parameter. `test_probe_provenance.py`
refuses a hand-written table; do not write one.

Expected content, measured 2026-10-17: all four of `api-gateway`'s unresolved dependencies at
**2 hops**, each via a different component BOM, each `version: ${project.version}`.

- [x] **Step 2: Write the failing tests**

In `tests/ingress/test_maven_detector.py`, using that file's existing pom-building harness:

```python
def test_a_bom_managing_its_own_artifacts_by_project_version_resolves_them():
    """`${project.version}` is a Maven BUILT-IN, not a `<properties>` entry, and it is how every
    Spring Cloud component BOM versions its own artifacts. `_interpolated` read only
    `<properties>`, so the entry was dropped — with no message, which is why the symptom read as
    a BOM that was never opened."""

def test_a_managed_version_that_cannot_be_interpolated_is_REPORTED_not_dropped():
    """The silent drop is the defect worth fixing beyond the one property: four wrong theories
    were argued while `metadata.json` could have named the cause."""

def test_project_version_resolves_in_the_declaring_poms_scope_not_the_modules():
    """The importing module's own version must never answer `${project.version}` — it would
    yield a coordinate that does not exist, which is worse than an honest unresolved."""
```

- [x] **Step 3: Run them to verify they fail**

```bash
.venv/bin/python -m pytest tests/ingress/test_maven_detector.py -q
```
Expected: FAIL — the entry is dropped and nothing is reported.

- [x] **Step 4: Define the built-ins per pom, scoped to that pom**

In `_managed_versions`, the imported BOM's property map gains `project.version` (the version the
import names), `project.groupId` and `project.artifactId`. Scoped to that BOM, beside the
existing comment that says the importing module's properties *"must not answer it"*.

- [x] **Step 5: Report a managed entry that cannot be interpolated**

The `if settled is not None:` branch gains an `else` appending to `unreadable`, which the
surrounding code already threads into `dependencies_not_resolved`.

- [x] **Step 6: List the 5.0.0 starter in both gateway catalogs**

`org.springframework.cloud:spring-cloud-starter-gateway-server-webflux`, with a comment citing
CP-35 and naming `spring-cloud-starter-gateway` as the pre-5.0 spelling it does not replace.
Closes the `gateway-detect-4x-coordinate` half of `OI-139`.

- [x] **Step 7: Prove it on the real module, and move the pin**

```bash
.venv/bin/sextant module analyze examples/spring-petclinic-microservices/spring-petclinic-api-gateway
```
Expected: **14 endpoints** — 8 inbound (4 new: `/api/vet/**`, `/api/visit/**`,
`/api/customer/**`, `/api/genai/**`) and 6 outbound (4 new: `lb://vets-service`,
`lb://visits-service`, `lb://customers-service`, `lb://genai-service`), and
`dependencies_not_resolved` empty. Re-record `petclinic-api-gateway.json`, then:

```bash
.venv/bin/python scripts/field_check.py petclinic-api-gateway petclinic-genai-service
```

- [x] **Step 8: Gate, guards, commit**

**Result: 14 endpoints (was 6) — 8 inbound, 6 outbound, `dependencies_not_resolved` empty.**
The four routes derive in both directions, all `resolved`. Three catalogs gained the
coordinate, not two: `spring-cloud-gateway-outbound.yml` carries the same stale list.
Field pins: both `ok`. Gate 4098 passed (+4), guards 161/0.

**`OI-140` found and logged, NOT fixed here.** The four new rows render as
`` `(unresolved) lb://vets-service` | unresolved | `None` | unresolved | resolved `` — three
deliberate NULLs printed as the word "unresolved" on a row whose Resolution says resolved,
plus a Python `None` in a published cell. Pre-existing (measured: `fixtures/orders-gateway`
has rendered this way since gateway support shipped), real-input-triggered, and Major on the
deliverable's own terms. Left out of this task because fixing it MOVES PINNED OUTPUT, which
this plan's own constraint reserves to a task that says so.

**A `peer` is NOT set on the four new outbound rows** — they carry `lb://…` whole as `path`,
which is the shipped shape and already tells a reader where the route goes. Splitting it is
scoped out (spec §4) and must not be done here.

---

## Task 2: Join a concatenation whose holes are all source literals — locals only

**1 row, and it proves the join end to end with no new fact.** `VectorStoreController` writes
`vetsHostname + "vets"` where `vetsHostname` is a LOCAL holding a literal in the same method
body (`aload_3`; `#63 = String http://vets-service/`, recipe `#261 = \u0001vets`).

**Ruling 1, granted:** *"join them when every single piece is a fixed string typed into the
source code. If any piece comes from a config file, a method parameter, or anything that changes
at runtime — don't join, behave exactly as today."*

**Files:**
- Modify: `src/sextant/application/resolve/values.py` (`_entry`'s `concat` arm, ~:605)
- Modify: `docs/superpowers/specs/2026-09-22-value-resolution-design.md` §6 — the amendment, in
  the voice §0c uses
- Test: `tests/application/test_values.py`, `tests/e2e/` as the pin requires
- Pins: `scripts/field-expectations/petclinic-genai-service.json`

**Interfaces:**
- Consumes: the `concat` fact's `source`, which already points at the indy's own call site —
  `domain/facts.py` says *"What FILLS the hole is the concat site's own call-site fact, reached
  by `source` → `result`."*
- Produces: a `literal` of `literal_kind: string` where every hole answered one; today's
  `expression` otherwise, template unchanged.

- [ ] **Step 1: Write the failing tests** — the negative cases first, because they are the ruling

```python
def test_a_concat_of_two_source_literals_joins():
def test_a_concat_with_one_unresolved_hole_carries_the_template_unchanged():
def test_a_concat_whose_hole_is_a_config_placeholder_never_joins():
    """`${…}` is an `expression`, not a `literal`, so it fails the all-literals test by
    construction. §8.2 is untouched: this fills no deployment hole."""
def test_a_concat_whose_hole_is_a_parameter_never_joins():
def test_two_holes_each_with_two_enumerable_answers_yield_four_rows_not_a_guess():
    """Ruling 1 of the previous spec (multiplicity), applied per hole."""
def test_a_concat_reached_on_two_paths_with_different_operands_is_two_answers():
    """Memoisation stays keyed on (position, path) — spec §1c, ruling M-1."""
```

- [ ] **Step 2: Run them to verify they fail**
- [ ] **Step 3: Resolve each hole through the ordinary walk; join only if all answered string literals**
- [ ] **Step 4: Amend spec §6 in place**, marking what the ruling narrowed and what it did not
- [ ] **Step 5: Re-run the cost measurement — the no-cap ruling was measured with this arm as a terminal**

```bash
.venv/bin/python scripts/measure_value_walk.py
```
This arm turns one terminal answer into N sub-walks. §3a of the previous spec ruled *no cap,
measure first*; that measurement predates this change and must be redone before Task 4 widens it
further.

- [ ] **Step 6: Prove on the real module, move the pin, gate, guards, commit**

Expected: `VectorStoreController` publishes peer `vets-service`, path `/vets` — matching
`vets-service`'s own inbound `GET /vets`.

---

## Task 3: A binding's literal value is a fact

**1 row.** `VisitsServiceClient` holds `private String hostname = "http://visits-service/"`.
Measured at `cp33_binding_writes.md` row 8: a field initialiser is
`aload_0; invokespecial; aload_0; ldc; putfield` — **inside `<init>`**, so the existing
constructor filter already admits it. Only the fact's grammar refuses: `fieldWrites` requires the
middle instruction to be a `VarInsnNode` and an `ldc` is not one.

**This is NOT capability 9.19 and NOT what `OI-136` deferred** — that is a write *outside* an
initialiser, a method-filter change. This is a grammar change inside `<init>`.

**Files:**
- Modify: `extractor-jvm/.../MethodFlow.java::fieldWrites` (~:249)
- Modify: `docs/components/D00-fact-schema.md` §5's `field_write`
- Modify: `src/sextant/application/resolve/values.py` — the `read_from_binding` arm reads the
  new shape
- Test: `extractor-jvm/src/test/java/dev/sextant/extractor/MethodFlowTest.java`,
  `tests/application/test_values.py`

- [ ] **Step 1: Write the failing tests, including every shape that must still emit nothing**

CP-33 rows 3 and 7 are the guard rails: a computed assignment and a field assigned another
call's result both present something that is not a load where the value must be, so neither
emits a fact and neither can be joined. **Direct traces only still holds** — assert it.

- [ ] **Step 2: Run them to verify they fail**
- [ ] **Step 3: Carry a constant value beside the parameter ordinal**, leaving the parameter arm byte-identical
- [ ] **Step 4: D00 records the widened fact** and keeps the 9.19 deferral note distinct from it
- [ ] **Step 5: Prove, move the pin, gate, guards, commit**

Expected, with Task 2: `VisitsServiceClient` publishes peer `visits-service`, path
`/pets/visits?petId={petId}` — from code facts alone, matching `visits-service`'s own inbound
rows.

---

## Task 4: `peer` and `path` from separate evidence, and a service name is a destination

**3 rows, and the only task needing both rulings.** `AIDataProvider` has **no URL in its class
file** (verified: zero `http://`). The service name is `#147 = String customers-service`, the
argument to a registry lookup one method away; the path is in the concatenation.

**Ruling 2, granted:** `peer` and `path` may be filled from separate evidence.

**Files:**
- Modify: `src/sextant/application/resolve/shapes/arguments.py` — a row may take `peer` from one
  resolved value and `path` from another
- New: `src/sextant/catalogs/spring-cloud-discovery.yml`
- New: `scripts/probes/cp36_discovery_client/` — the jar evidence
- Test: `tests/application/test_call_engines.py`, `tests/architecture/test_probe_provenance.py`

- [ ] **Step 1: The probe** — generated, recording from the jars: `getInstances(String) →
  List<ServiceInstance>`; `ServiceInstance.createUri` builds from `%s://%s:%s`, **no path**; and
  that `getUri()` is abstract on the interface, so the no-path claim holds for the default
  implementation and is a stated boundary otherwise.

- [ ] **Step 2: Write the failing tests — the value-flow rule is the point**

```python
def test_a_discovery_lookup_whose_value_reaches_a_url_slot_names_the_peer():
def test_a_discovery_lookup_that_reaches_no_url_slot_names_nothing():
    """`getInstances` was CALLED is not evidence of an outgoing call — a dashboard could list
    instances and call none. The rule is value-flow, never call-presence."""
def test_a_row_may_carry_a_resolved_peer_with_an_unresolved_path():
def test_messaging_peers_stay_null():
    """D02 §3, unchanged by ruling 2."""
```

- [ ] **Step 3–5: Run, implement, then prove / pin / gate / guards / commit**

Expected: the three `AIDataProvider` rows publish peer `customers-service` with paths `/owners`
and `/owners/{}/pets` — matching `customers-service`'s own inbound `GET /owners` and
`POST /owners/{ownerId}/pets`.

**Which instance is not modelled.** `getInstances` returns every registered instance and the
application picks one (`.get(0)` here, which is not load balancing). The service identity is the
peer; instance choice is a runtime detail.

---

## Task 5: Docs, register, COVERAGE, pins

- [ ] `OI-139` closes citing Task 1's test and the moved pin. `OI-138`'s four causes each close
  or are restated with what remains.
- [ ] `gateway-detect-4x-coordinate` closes in `docs/java-kotlin-delivery-list.md`.
- [ ] COVERAGE §3c regenerated (`scripts/value_boundaries.py --measure`) — Tasks 2–4 move those
  figures, and `--check` cannot see it (it compares the document to the snapshot, so both go
  stale together).
- [ ] COVERAGE's Spring Boot REST-outbound row states what now derives and what does not, with
  the `lb://` split named as scoped out and why.
- [ ] `scripts/coverage_matrix.py --check`, `coverage_versions.py --check`,
  `value_boundaries.py --check` all pass.
- [ ] **The register records what did NOT close**, in the voice §5a's method note uses.

## Task 6: Finish

- [ ] Full gate and `--guards`.
- [ ] Amend the spec with anything implementation forced.
- [ ] Use superpowers:finishing-a-development-branch. **Do not merge without the user.**

---

## Self-Review

**Spec coverage.** *What it closes* table row 1 → Task 1. Row 2 → Task 2. Row 3 → Tasks 2+3.
Row 4 → Tasks 2+4. §1 → Task 2. §2 → Task 4. §3 → Task 3. §4 → Task 4. §5a → Task 1.
§6 → every task's pin step. §7 → the constraints above.

**Placeholders.** None. Every expected figure is one measured in the spec, and every task ends
at a pin that must be re-recorded.

**Ordering, and why it is not negotiable.** Task 1 first because it needs **no ruling**, is worth
8 of the 13 rows, and is already proven. Task 2 before 3 because the local-variable case proves
the join with no new fact — if the join is wrong, that is where it shows, cheaply. Task 3 before
4 because 4 needs both rulings and 3 needs one. Task 5 last of the substantive work.

**The risk this plan carries, named where it is handled.** Every task converts a blank into an
assertion about a real system, and the pins record today's blanks verbatim — so each task FAILS a
pin and forces a deliberate re-record rather than passing silently. That is the plan's answer to
spec §7, and it is why no task is allowed to end without the pin step.

**What this plan does NOT do.** The `lb://` → peer split (spec §4 — an empty path is what D02
forbids, and it rewrites 10 pinned fixture rows); capability 9.19 (`OI-136`, deferred);
`akka-pekko-actors` (probe row 7 — an `actorOf` result fits no fact we have);
`OI-110`/`OI-124`/`OI-126` (unrelated mechanisms); Gateway `filters` rewriting the upstream path
(`OI-111`).
