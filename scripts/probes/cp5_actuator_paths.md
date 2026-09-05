# CP-5 — Actuator endpoint paths and operation verbs (2O Task 7, Step 0)

**Question.** Does `@Endpoint(id = "x")` serve under `/actuator/x`? Does
`@ReadOperation` map to GET, `@WriteOperation` to POST, `@DeleteOperation` to
DELETE? Is the `/actuator` prefix a constant, or does something in the module
move it?

**Version scope (§5.4).** Run against **Spring Boot 3.5.10 and 4.1.1**, both on
an embedded Tomcat with `management.endpoints.web.exposure.include=*`. The
verdict below is evidence about those two versions and no other: the base-path
property NAME and the `/actuator` DEFAULT are both version-scoped
configuration, and Boot 1.x served actuator endpoints at the context root with
no prefix at all. Widening the verdict means adding a version to `VERSIONS` in
`cp5_actuator/run.sh` and re-running, never assuming.

**How to run.** `bash scripts/probes/cp5_actuator/run.sh`. It builds
`cp5_actuator/` (one `@SpringBootApplication`, one `@Endpoint(id = "probe")`
carrying all three operation annotations, one `@Endpoint(id = "empty")`
carrying none) once per version, runs it, and curls one URL per row. Needs a
JDK 21+, Maven, and network on the first run. Not a test — nothing in the suite
runs it, and NFR-1's no-network rule governs the suite, not evidence
gathering.

## Expectation table

| # | Declaration | URL under test | Expected | Observed (3.5.10 / 4.1.1) |
|---|---|---|---|---|
| 1 | `@Endpoint(id="probe")` + `@ReadOperation` | GET `/actuator/probe` | 200 | CONFIRMED — 200 / 200 |
| 2 | `@Endpoint(id="probe")` + `@WriteOperation` | POST `/actuator/probe` | 200 | CONFIRMED — 200 / 200 |
| 3 | `@Endpoint(id="probe")` + `@DeleteOperation` | DELETE `/actuator/probe` | 200 | CONFIRMED — 200 / 200 |
| 4 | the same class, no operation for PUT | PUT `/actuator/probe` | 405 | CONFIRMED — 405 / 405 |
| 5 | the id alone, without the prefix | GET `/probe` | 404 | CONFIRMED — 404 / 404 |
| 6 | `@Endpoint(id="empty")`, **no operation annotation** | GET `/actuator/empty` | 404 | CONFIRMED — 404 / 404 |
| 7 | `management.endpoints.web.base-path=/manage` | GET `/manage/probe` | 200 | CONFIRMED — 200 / 200 |
| 8 | the same run, the default prefix | GET `/actuator/probe` | 404 | CONFIRMED — 404 / 404 |

Row 6 is stronger than a 404: the endpoint does not appear in the discovery
document at all. `GET /actuator` on the default-path run listed `probe`
alongside the built-in endpoints and did **not** list `empty`.

## Verdict

All eight rows CONFIRMED on both versions, none falsified.

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
