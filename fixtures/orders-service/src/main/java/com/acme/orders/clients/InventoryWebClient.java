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
