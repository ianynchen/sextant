// Spring Cloud Gateway's Java DSL (`G-30` inbound, `G-30-outbound`; spec §14): every route is a
// lambda handed to `route(…)`, its predicates a chain on the lambda's own parameter, its target
// the `uri(…)` at the chain's end. Both `route` overloads; path only; path and method; `or`;
// `not`; a lambda capturing a local and one capturing `this` — the two capture shapes a fixed
// parameter index gets wrong; every route ends in `uri`, one `http://`, one `lb://`. And one
// route whose predicates DEMAND something of the request — `header("X-Api", "v2")` then
// `query("debug")` (spec 2026-09-19 §5c): the route still serves its path, and the two
// demands reach `endpoint_metadata` as `required` requirements of that row.
package com.acme.gw;

import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;

@Configuration
public class GatewayRoutes {
    private final String billing = "http://billing-service";

    @Bean
    public RouteLocator routes(RouteLocatorBuilder builder) {
        String prefix = "/legacy";
        return builder.routes()
            .route("orders", r -> r.path("/orders/**").uri("http://orders-service"))
            .route("orders-write", r -> r.path("/orders/**").and().method(HttpMethod.POST, HttpMethod.PUT)
                                         .filters(f -> f.stripPrefix(1)).uri("lb://orders-service"))
            .route("either", r -> r.path("/a/**").or().path("/b/**").uri("http://ab-service"))
            .route("not-admin", r -> r.not(p -> p.path("/admin/**")).uri("http://public-service"))
            .route("legacy", r -> r.path(prefix + "/**").uri("http://legacy-service"))          // captures a local
            .route("billing", r -> r.path("/billing/**").uri(billing))                          // captures this
            .route(r -> r.host("**.example.org").uri("http://host-service"))                    // route(Function): host only → /**
            .route("guarded", r -> r.path("/guarded/**").and().header("X-Api", "v2").and().query("debug")
                                         .uri("http://guarded-service"))                        // header + query requirements
            .build();
    }
}
