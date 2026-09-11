# CP-5 — Actuator endpoint paths and operation verbs (2O Task 7, Step 0)

**Question.** Does `@Endpoint(id = "x")` serve under `/actuator/x`? Does
`@ReadOperation` map to GET, `@WriteOperation` to POST, `@DeleteOperation` to
DELETE? Is the `/actuator` prefix a constant, or does something in the module
move it?

**Version scope (§5.4).** Run against **Spring Boot 3.5.10 and 4.1.1**, both on
an embedded Tomcat. The verdict below is evidence about those two versions and
no other: the base-path property NAME and the `/actuator` DEFAULT are both
version-scoped configuration, and Boot 1.x served actuator endpoints at the
context root with no prefix at all. Widening the verdict means adding a version
to `VERSIONS` in `cp5_actuator/run.sh` and re-running, never assuming.

**AND EACH COLUMN'S IDENTITY COMES FROM THE RUN'S OWN OUTPUT** (2O Task 7
review, Critical 2). The first version of this harness ran `package` without
`clean`, so the second loop iteration re-ran the FIRST version's fat jar while
printing a `4.1.1` header: eight of the sixteen cells the shipped table carried recorded a
run that never happened. The re-run reproduces every one of them genuinely, and the
harness no longer takes a run's identity from the loop variable it passed in —
each JVM's own Spring Boot `(vX.Y.Z)` banner is parsed out of that process's
log, every status is filed under THAT version, and a banner disagreeing with
the version requested aborts the harness. The table below is the harness's own
generated output, transcribed verbatim rather than restated.

**How to run.** `bash scripts/probes/cp5_actuator/run.sh`. It builds
`cp5_actuator/` (one `@SpringBootApplication`, one `@Endpoint(id = "probe")`
carrying all three operation annotations, one `@Endpoint(id = "empty")`
carrying none, one `@Endpoint(id = "closed", defaultAccess = Access.NONE)`)
once per version and runs it three ways: with `exposure.include=*` under the
default base path, with `exposure.include=*` under `base-path=/manage`, and
with **exposure left at Boot's own default**. It curls one URL per row and ends
by printing the observation table itself. Needs a JDK 21+, Maven, and network
on the first run. Not a test — nothing in the suite runs it, and NFR-1's
no-network rule governs the suite, not evidence gathering.

## Expectation table

| # | Declaration | URL under test | Expected |
|---|---|---|---|
| 1 | `@Endpoint(id="probe")` + `@ReadOperation` | GET `/actuator/probe` | 200 |
| 2 | `@Endpoint(id="probe")` + `@WriteOperation` | POST `/actuator/probe` | 200 |
| 3 | `@Endpoint(id="probe")` + `@DeleteOperation` | DELETE `/actuator/probe` | 200 |
| 4 | the same class, no operation for PUT | PUT `/actuator/probe` | 405 |
| 5 | the id alone, without the prefix | GET `/probe` | 404 |
| 6 | `@Endpoint(id="empty")`, **no operation annotation** | GET `/actuator/empty` | 404 |
| 7 | `management.endpoints.web.base-path=/manage` | GET `/manage/probe` | 200 |
| 8 | the same run, the default prefix | GET `/actuator/probe` | 404 |
| 9 | `@Endpoint(id="probe")` + `@ReadOperation`, **exposure left at Boot's default** | GET `/actuator/probe` | 404 |
| 10 | the same run, the one endpoint the default DOES expose | GET `/actuator/health` | 200 |
| 11 | `@Endpoint(id="closed", defaultAccess = Access.NONE)`, exposure `*` | GET `/actuator/closed` | 404 |

Rows 1-8 are the original expectation set. Rows 9-11 were added by the Task 7
review: rows 9-10 measure **web exposure**, the second conjunct of Boot's rule
that rows 1-8 silently satisfied and never stated, and row 11 measures the
`@Endpoint` annotation's own second attribute.

## Observations

Verbatim from `run.sh`'s generated table — every column header is the version
the JVM under test reported in its own Spring Boot banner, not the version the
loop asked for.

| # | probe | 3.5.10 | 4.1.1 |
|---|---|---|---|
| 1 | `GET /actuator/probe` | 200 | 200 |
| 2 | `POST /actuator/probe` | 200 | 200 |
| 3 | `DELETE /actuator/probe` | 200 | 200 |
| 4 | `PUT /actuator/probe` | 405 | 405 |
| 5 | `GET /probe` | 404 | 404 |
| 6 | `GET /actuator/empty` | 404 | 404 |
| 7 | `GET /manage/probe` — `base-path=/manage` | 200 | 200 |
| 8 | `GET /actuator/probe` — `base-path=/manage` | 404 | 404 |
| 9 | `GET /actuator/probe` — exposure left at Boot's DEFAULT | 404 | 404 |
| 10 | `GET /actuator/health` — exposure left at Boot's DEFAULT | 200 | 200 |
| 11 | `GET /actuator/closed` — `defaultAccess = Access.NONE`, exposure `*` | 404 | 404 |

Every row CONFIRMED on both versions, none falsified.

Two rows are stronger than their status code, and the harness captures the
discovery document rather than asserting either:

- **Row 6.** `GET /actuator` on the exposed run listed `probe` alongside the
  built-in endpoints and listed neither `empty` nor `closed`.
- **Rows 9-10.** `GET /actuator` on the default-exposure run listed
  `health` and `health-path` and **nothing else** — not `probe`, not the
  built-ins — on both versions.

## Verdict

1. **The address is `<base-path>/<id>`**, and the id is the `@Endpoint`
   annotation's own `id` attribute (`javap`: `Endpoint` declares `id()` and
   `defaultAccess()`, `@Target(TYPE)`).
2. **The verb comes from the operation annotation**, one verb each:
   `ReadOperation` → GET, `WriteOperation` → POST, `DeleteOperation` → DELETE.
   Row 4 shows the framework serves no verb it was not given an operation for.
3. **An `@Endpoint` class with no operation annotation serves nothing** (row
   6). This is why `spring-actuator.yml` gates on the operation annotations
   rather than on the class: a class-level rule would publish an address the
   framework does not serve.
4. **`/actuator` is a DEFAULT, not a constant** (rows 7-8). The property is
   `management.endpoints.web.base-path` on both versions probed.
5. **A custom `@Endpoint` is not served at all unless it is WEB-EXPOSED, and
   Boot's default exposure is `health` alone** (rows 9-10, 2O Task 7 review,
   Critical 3). This is a conjunct rows 1-8 satisfied without stating: the
   probe app was passing `management.endpoints.web.exposure.include=*`, so
   every 200 above is conditional on it. Under Boot's OWN default, the very
   same `@ReadOperation` on the very same `@Endpoint(id="probe")` is a 404 and
   is absent from the discovery document. `spring-actuator.yml` cannot read
   that key — `annotation_driven` never touches `resolved_config` — so **every
   `/actuator/<id>` row the catalog publishes at `resolved`/`compiler` is an
   address nothing serves unless the module opted in.** A `docs/COVERAGE.md`
   boundary, falsified the day the default changes or an annotation-derived row
   can read a configuration key.
6. **`@Endpoint(defaultAccess = Access.NONE)` closes the endpoint by itself**
   (row 11): exposed by `*` and still a 404, still absent from the discovery
   document, on both versions. A second, smaller unread conjunct — nothing in
   Sextant reads the attribute — and the same over-report in miniature.

## What this probe deliberately did not measure

- **`@Selector` path segments.** `@Endpoint`'s operations may take
  `@Selector`-annotated parameters that become extra path segments
  (`/actuator/env/{toMatch}` in the discovery document above). Out of scope
  for this task by the brief, and a stated boundary in `docs/COVERAGE.md`:
  `mapping` has no vocabulary for a path segment contributed by a PARAMETER.
- **`@WebEndpoint`, `@ControllerEndpoint`, `@RestControllerEndpoint`,
  `@ServletEndpoint`, `@EndpointExtension`.** Other registration
  annotations, none probed and none catalogued; stated boundaries.

## How the verdict is consumed

`src/sextant/catalogs/spring-actuator.yml` declares `mapping.path_prefix:
/actuator` and one mapping annotation per operation annotation with its verb
pre-set. Rows 7-8 are precisely why the prefix is recorded as a **stated
boundary** rather than read: `annotation_driven` never touches
`resolved_config` (only `resolve/engines/config_join.py:528` and
`resolve/engines/derived_resource.py:578` do), so a module that overrides the
base path is published under `/actuator` regardless. That over-claim is
recorded in `docs/COVERAGE.md`, and it becomes false the day an
annotation-driven row can read a configuration key — which is the condition to
revisit this line.

Verdict rows 5-6 are the SAME seam and the larger over-claim: the base path
moves an address, but exposure decides whether there is an address at all, and
`management.endpoints.web.exposure.include` defaults to `health`. Both are
unread conjuncts for the same reason and both are stated boundaries in
`docs/COVERAGE.md` and in `spring-actuator.yml` itself.
