# CP-1 — Spring path combination (2O design §0a)

**Question.** Does Spring serve `@RequestMapping("users")` and `@RequestMapping("/users")`
at the same URL, how does class+method combination insert separators, and is a
trailing slash distinct?

**Version scope.** Framework 6+ / Boot 3+ (where `setUseTrailingSlashMatch` was
removed). Boot 2 / Framework 5 matched a trailing slash to the slashless mapping.

**How to run.** In a scratch directory, build a minimal `spring-boot-starter-web`
app (this run used Boot 4.0.1, resolved offline from `~/.m2` — no network
required once the artifact is cached) declaring a controller per row below,
run it on an embedded Tomcat, and curl each candidate URL. Two rows collide on
the SAME served URL as another row in the same class (row 1 vs row 2, row 3 vs
row 4) — those pairs were run as two separate app instances rather than two
`@RestController`s in one instance, since Spring refuses to start with two
identical GET mappings. Record the observed status per URL in the table.

| Class mapping | Method mapping | URL served | Observed |
|---|---|---|---|
| (none) | `"users"` | `/users` | CONFIRMED — GET `/users` → 200 |
| (none) | `"/users"` | `/users` | CONFIRMED — GET `/users` → 200 (separate instance, no class mapping) |
| `"/api"` | `"users"` | `/api/users` | CONFIRMED — GET `/api/users` → 200 |
| `"/api/"` | `"/users"` | `/api/users` | CONFIRMED — GET `/api/users` → 200 (separate instance) |
| `"/api"` | `""` | `/api` | CONFIRMED — GET `/api` → 200 (used `/api2` as the class prefix in the probe app to avoid colliding with the row-3 controller in the same instance; the shape under test — empty method mapping contributing nothing beyond the class prefix — is identical) |
| (none) | `"/users/"` | `/users/` served, `/users` 404 | CONFIRMED — GET `/users6/` → 200, GET `/users6` → 404 (used `/users6` as the segment name in the probe app to avoid colliding with the row-1/row-2 controllers; the trailing-slash distinctness under test is identical) |

**Verdict.** All six rows CONFIRMED against a live Boot 4.0.1 / Framework 7
app (in scope: Framework 6+ / Boot 3+, per the version-scope note above — Boot
4 removed `setUseTrailingSlashMatch` the same as Boot 3 did). No row falsified;
no spec amendment needed.

**Reproduction.** The probe app's source (`ProbeApplication.java`, one
`@SpringBootApplication` class with one static `@RestController` nested class
per row) and its `pom.xml` (`spring-boot-starter-web:4.0.1`, no other
dependencies) are not committed — they were scratch files, not a fixture this
repo needs to keep running. A future re-run: scaffold the same shape (a
controller per row, run rows that share a served URL as separate instances on
different ports), start each instance, and curl. No test in this repository
depends on this probe running — it is evidence for the ruling recorded above,
consumed by Task 2's design of the path-combination seam.
