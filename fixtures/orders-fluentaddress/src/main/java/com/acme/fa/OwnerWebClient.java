package com.acme.fa;

import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

/** A `WebClient` chain whose address is assembled — the `fluent` engine. */
public class OwnerWebClient {

    private final WebClient.Builder builder;

    public OwnerWebClient(WebClient.Builder builder) {
        this.builder = builder;
    }

    /** The host comes from outside and the PATH is stated: `<host>/owners`, partial. Before
     *  `OI-144` this published `path` NULL at `unresolved` while `single_call` published the
     *  path for identical code. */
    public Mono<String> owners(String base) {
        return builder.build().get().uri(base + "/owners").retrieve().bodyToMono(String.class);
    }

    /** A whole literal, which worked before and must keep working. */
    public Mono<String> vets() {
        return builder.build().get()
            .uri("http://vets-service/vets")
            .retrieve()
            .bodyToMono(String.class);
    }
}
