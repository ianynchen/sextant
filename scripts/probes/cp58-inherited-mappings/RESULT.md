# CP-58: which frameworks serve a mapping a controller inherits without overriding it

Measured 2026-10-30 under JDK 21 (`run.sh`; builds, starts each app on a free port, curls, stops it).
Each app: an abstract base (`CrudController` / `CrudResource`, no stereotype or path annotation) with
`GET /list` and `POST ""`; `OrderController` at `/orders` extending it and overriding nothing;
`ProductController` at `/products` extending it and overriding `list` with `GET /all`; and a third
case, `BaseController` at `/base` carrying both mappings itself with `SubController` at `/sub`
extending it and overriding nothing.

## Versions

| Framework | Measured |
|---|---|
| Spring MVC | Spring Boot 3.5.14, spring-webmvc 6.2.18 |
| Jersey (JAX-RS 3.1) | Jersey 3.1.11, jakarta.ws.rs-api 3.1.0, via Boot 3.5.14 starter-jersey on Tomcat |
| Quarkus REST | Quarkus 3.40.1.1, quarkus-rest |
| Micronaut | micronaut-platform 4.7.6, http-server-netty, serde-jackson |

## Status codes (identical for all four)

| Request | Spring MVC | Jersey | Quarkus REST | Micronaut |
|---|---|---|---|---|
| GET /orders/list | 200 | 200 | 200 | 200 |
| POST /orders | 200 | 200 | 200 | 200 |
| GET /products/list | 404 | 404 | 404 | 404 |
| GET /products/all | 200 | 200 | 200 | 200 |
| POST /products | 200 | 200 | 200 | 200 |
| GET /base/list | 200 | 200 | 200 | 200 |
| POST /base | 200 | 200 | 200 | 200 |
| GET /sub/list | 200 | 200 | 200 | 200 |
| POST /sub | 200 | 200 | 200 | 200 |

## Conclusions

Serves inherited non-overridden mappings under the subclass's prefix:

- Spring MVC: yes
- Jersey: yes
- Quarkus REST: yes
- Micronaut: yes

An inherited method the subclass overrides is served only at the override's own mapping
(`/products/list` is 404; the base's `/list` does not survive the override in any framework).

`/base` vs `/sub`: when the base class is itself a controller/resource, both are served, each under
its own prefix (`/base/list` and `/sub/list` are both 200). The subclass inheriting is additive; the
base keeps serving its own routes.

Notes: no build failures; Micronaut first died at startup (no JSON error-body provider) until
`micronaut-serde-jackson` was added, which is a probe-setup matter, not a mapping finding.
