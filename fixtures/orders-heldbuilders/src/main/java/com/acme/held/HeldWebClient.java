package com.acme.held;

import org.springframework.http.HttpStatusCode;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

/** `spring-webclient.yml` in the variable style: the request spec and the response spec are
 *  each held, and `onStatus` is a statement of its own before the body is read. Two rows,
 *  `GET /x` and `POST /x`, each with its response shape. */
public class HeldWebClient {
    private final WebClient client;

    public HeldWebClient(WebClient client) {
        this.client = client;
    }

    public Mono<Order> fetch() {
        WebClient.RequestHeadersUriSpec<?> request = client.get();
        request.uri("/x");
        request.header("X-Trace", "held");
        WebClient.ResponseSpec response = request.retrieve();
        response.onStatus(HttpStatusCode::isError, failed -> Mono.error(new IllegalStateException()));
        return response.bodyToMono(Order.class);
    }

    public Mono<Order> create(Order order) {
        WebClient.RequestBodyUriSpec request = client.post();
        request.uri("/x");
        request.bodyValue(order);
        WebClient.ResponseSpec response = request.retrieve();
        response.onStatus(HttpStatusCode::isError, failed -> Mono.error(new IllegalStateException()));
        return response.bodyToMono(Order.class);
    }
}
