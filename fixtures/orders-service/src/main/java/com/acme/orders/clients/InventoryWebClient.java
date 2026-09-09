// The `fluent` engine's asynchronous exemplar: chain reconstruction joins
// these calls through result/receiver ids within one method — including one
// method whose terminal call sits inside a lambda body, and one whose URL
// is itself built by a lambda the engine only follows one hop into.
package com.acme.orders.clients;

import com.acme.orders.contracts.OrderRequest;
import com.acme.orders.contracts.OrderView;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class InventoryWebClient {
    private final WebClient webClient;

    public InventoryWebClient(WebClient webClient) {
        this.webClient = webClient;
    }

    // bodyToMono with a class literal: the fluent mirror of RestTemplate's
    // getForObject, reconstructed from get() -> uri() -> retrieve() ->
    // bodyToMono() rather than read off one call's arguments.
    public Mono<OrderView> getLevels() {
        return webClient.get()
                .uri("/v2/inventory/levels")
                .retrieve()
                .bodyToMono(OrderView.class);
    }

    // bodyValue supplies the request body on its own step, outside the uri
    // chain entirely — captures.body reads arg0 off *this* step, never off
    // post().
    public Mono<OrderView> reserve(OrderRequest request) {
        return webClient.post()
                .uri("/v2/inventory/reserve")
                .bodyValue(request)
                .retrieve()
                .bodyToMono(OrderView.class);
    }

    // `OI-73`, and the half `search` below does not reach: TWO query parameters, one of
    // them a LITERAL. `search` passes only a method parameter, so every entry it
    // contributes is `unresolved` and a rule that never read a value would look correct.
    //
    // Its own path, deliberately: an outbound fluent row dedups on
    // (protocol, direction, verb, path), so a second chain on `/v2/inventory/search`
    // would collapse into `search`'s row and take its entries with it.
    public Mono<OrderView> lookup(String sku) {
        return webClient.get()
                .uri(builder -> builder.path("/v2/inventory/lookup")
                        .queryParam("sku", sku)
                        .queryParam("region", "eu")
                        .build())
                .retrieve()
                .bodyToMono(OrderView.class);
    }

    // W29 (F5 §6.2). What an outbound call carries BESIDE its address and payload.
    //
    // THREE headers on one chain, because a capture is last-wins and would keep only the
    // third: `.header(...)` is repeatable and the wire carries all of them.
    //
    // `Authorization` is here to be REDACTED. Its value is a literal in bytecode, which
    // is realistic — and nothing in this system reads a metadata value, so the masked
    // string is the only one ever written down rather than being masked later at export.
    //
    // `X-Trace-Id` takes a VARIABLE, so its value cannot be read: the entry is present
    // and `unresolved`, which is a different and more useful answer than absent. That
    // distinction is what the per-entry trust columns exist for.
    public Mono<OrderView> tagged(String traceId) {
        return webClient.get()
                .uri("/v2/inventory/tagged")
                .header("Authorization", "Bearer sk-live-fixture-secret")
                .header("X-Tenant", "acme")
                .header("X-Trace-Id", traceId)
                .retrieve()
                .bodyToMono(OrderView.class);
    }

    // bodyToFlux: response_is: array in the catalog, same class-literal
    // response otherwise — a collection wire shape with no List<> generic
    // anywhere in the call.
    public Flux<OrderView> history() {
        return webClient.get()
                .uri("/v2/inventory/history")
                .retrieve()
                .bodyToFlux(OrderView.class);
    }

    // uri(Function<UriBuilder, URI>): the lambda linkage is recorded on the
    // call_site fact, but the fluent engine only follows one hop from a
    // captured argument — this path's url stays honestly `unresolved`
    // rather than guessed from the literal inside the builder.
    public Mono<OrderView> search(String term) {
        return webClient.get()
                .uri(uriBuilder -> uriBuilder.path("/v2/inventory/search").queryParam("q", term).build())
                .retrieve()
                .bodyToMono(OrderView.class);
    }

    // flatMap: the lambda body issues a second, complete chain of its own —
    // the dataflow pass has to scan the flatMap lambda's synthetic method,
    // not just this enclosing one, to find it.
    public Mono<OrderView> reserveAfterLevels(OrderRequest request) {
        return webClient.get()
                .uri("/v2/inventory/levels")
                .retrieve()
                .bodyToMono(OrderView.class)
                .flatMap(level -> webClient.post()
                        .uri("/v2/inventory/reserve")
                        .bodyValue(request)
                        .retrieve()
                        .bodyToMono(OrderView.class));
    }
}
