// Functional-endpoint handlers for OrderRoutes. Bodies stay inert -- no
// WebClient/RestTemplate/OkHttp/Kafka/JMS calls -- so this fixture doesn't
// derive rows through any shipped catalog before the combinator engine
// (Tasks 5-9) exists to walk RouterFunctions itself.
package com.acme.orders.routes;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
public class RouteHandlers {

    public Mono<ServerResponse> listOrders(ServerRequest request) {
        return ServerResponse.ok().build();
    }

    public Mono<ServerResponse> createOrder(ServerRequest request) {
        return ServerResponse.ok().build();
    }

    public Mono<ServerResponse> health(ServerRequest request) {
        return ServerResponse.ok().build();
    }
}
