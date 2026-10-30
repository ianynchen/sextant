# CP-57: which configured prefix each dispatcher takes

Measured with `./run.sh` (JDK 21, Maven). Spring Boot 3.5.14 (Spring Framework 6.2.x, Tomcat embedded),
Spring Cloud 2025.0.2 (`spring-cloud-starter-gateway-server-webflux`, Gateway 4.3.x), Jersey from
`spring-boot-starter-jersey`. Every ordering of every subset of the candidate prefixes was requested
for each handler; only the listed path answered 2xx.

Servlet app: `server.servlet.context-path=/c`, `spring.mvc.servlet.path=/m`, `spring.jersey.application-path=/j`.
Reactive app: `spring.webflux.base-path=/w`, leftover `server.servlet.context-path=/c`.

| Handler kind | Declared path | Path that answered 200 | Prefix keys that apply |
|---|---|---|---|
| MVC `@RestController` | `/mvc` | `/c/m/mvc` | context-path, mvc servlet path |
| MVC `RouterFunction` | `/fn` | `/c/m/fn` | context-path, mvc servlet path |
| `@WebServlet("/legacy")` | `/legacy` | `/c/legacy` | context-path only (not `spring.mvc.servlet.path`) |
| Jersey resource | `/jersey` | `/c/j/jersey` | context-path, jersey application-path (not `spring.mvc.servlet.path`) |
| Actuator health (same port) | `/actuator/health` | `/c/m/actuator/health` | context-path, mvc servlet path (served by DispatcherServlet) |
| WebFlux `@RestController` | `/flux` | `/w/flux` | webflux base-path only; `server.servlet.context-path` ignored |
| WebFlux `RouterFunction` | `/fnflux` | `/w/fnflux` | webflux base-path only |
| Spring Cloud Gateway route | `Path=/gw/**` | `/w/gw/x` (route's `SetStatus=299`, so 299 not 200) | webflux base-path only |
| Actuator health (reactive) | `/actuator/health` | `/w/actuator/health` | webflux base-path only |

## Reading

- Dispatcher `spring` on the servlet stack (MVC controller, functional router, actuator, Data REST):
  context-path then `spring.mvc.servlet.path`, composed left to right.
- Dispatcher `servlet` (`@WebServlet`): context-path only. `spring.mvc.servlet.path` and
  `spring.jersey.application-path` do not apply.
- Dispatcher `jaxrs` (Jersey): context-path then `spring.jersey.application-path`. `spring.mvc.servlet.path` does not apply.
- Reactive stack: `spring.webflux.base-path` applies to controllers, functional routes, actuator and
  Gateway routes alike; `server.servlet.context-path` has no effect (a leftover is harmless noise).
  Gateway uses the `spring` (DispatcherHandler) class of key, so `spring-cloud-gateway` and
  `spring-cloud-gateway-properties` can be tagged `dispatcher: spring` with `stack: reactive`.

## Surprises

- Actuator with no separate management port is under the MVC servlet path (`/c/m/actuator/health`),
  not merely the context-path.
- Gateway dependency resolved fine; Gateway routes are matched after base-path stripping, so the
  configured route predicate `/gw/**` is reached at `/w/gw/x`, not at `/gw/x`.
- Gateway starter was renamed in Spring Cloud 2025.0 (`spring-cloud-starter-gateway-server-webflux`);
  the property prefix is `spring.cloud.gateway.server.webflux.*`.
- Not measured: `management.server.port` / `management.endpoints.web.base-path`, WebFlux with
  `spring.webflux.base-path` and a servlet context path on a servlet app (reactive only here).
