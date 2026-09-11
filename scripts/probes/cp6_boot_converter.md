# CP-6 — Boot's default converter (2O design §0a)

**Question.** Does `jackson-databind` on the classpath of a Spring MVC app
make JSON the response format for a handler with no `produces` and no
Jackson annotation?

**Version scope.** Framework 6+ / Boot 3+, the same scope CP-1 states — this
run used Boot 4.0.1, which pulls `jackson-databind` transitively via
`spring-boot-starter-json` (a transitive of `spring-boot-starter-web`), with
no `produces` declared on the mapping and no Jackson annotation anywhere on
the return type.

**How to run.** In a scratch directory, build a minimal
`spring-boot-starter-web` app (Boot 4.0.1, resolved offline from `~/.m2`),
declare a `@GetMapping` handler with no `produces` returning a plain POJO
(a no-argument constructor, a getter, zero Jackson annotations), run it on an
embedded Tomcat, and curl the endpoint with response headers. Record the
observed `Content-Type`.

| Handler | `produces` | Payload | URL | Observed `Content-Type` |
|---|---|---|---|---|
| Plain POJO return, no annotations | (none) | `class Payload { String value; ...getter/setter, no-arg ctor }` | `/probe/converter` | CONFIRMED — `application/json` |

**Verdict.** CONFIRMED. `jackson-databind`'s presence on the classpath (via
`spring-boot-starter-json`) makes JSON the default response format for a
handler that declares no `produces` and whose return type carries no
serialization annotation — the same rule 2G design §7's `json_default_markers`
rung mirrors. No spec amendment needed.

**Reproduction.** Same scratch probe app as CP-1 (not committed — see that
file's Reproduction note): one additional `@RestController` with a
`@GetMapping("/probe/converter")` handler returning the plain `Payload` POJO,
curled with `curl -s -D - -o /dev/null <url>` and the `Content-Type` response
header read off. A future re-run needs only `spring-boot-starter-web` on the
classpath (which brings Jackson in transitively) and the one handler above.
