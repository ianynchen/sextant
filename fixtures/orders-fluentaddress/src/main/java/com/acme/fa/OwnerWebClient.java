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

    /** `OI-151` through the fluent engine: the query string is not part of the address, so
     *  this publishes `/pets/visits` — which is what `visits-service` SERVES — plus one
     *  `endpoint_metadata` entry per parameter. `page` is a literal and is read; `petId` is
     *  a runtime value and is not. The `token` parameter is here because the entry's value
     *  is masked by the parameter's own name, and a credential in a query string is an
     *  ordinary way to write an outbound call. */
    public Mono<String> visits(String petId) {
        return builder.build().get()
            .uri("http://visits-service/pets/visits?petId=" + petId + "&page=2&token=sk-live-xyz")
            .retrieve()
            .bodyToMono(String.class);
    }

    /** A whole literal, which worked before and must keep working. */
    public Mono<String> vets() {
        return builder.build().get()
            .uri("http://vets-service/vets")
            .retrieve()
            .bodyToMono(String.class);
    }
}
