// RestClient is WebClient's synchronous twin: same fluent shape, same
// `fluent` engine and the same spring-restclient.yml step names — no Mono
// or Flux anywhere, `retrieve().body(...)` returns the value directly.
package com.acme.orders.clients;

import com.acme.orders.contracts.OrderRequest;
import com.acme.orders.contracts.OrderView;
import org.springframework.web.client.RestClient;

public class OrdersRestClient {
    private final RestClient restClient;

    public OrdersRestClient(RestClient restClient) {
        this.restClient = restClient;
    }

    // get() -> uri() -> retrieve() -> body(Class): the same class-literal
    // response shape as WebClient's getLevels, on the synchronous chain.
    public OrderView mirror() {
        return restClient.get()
                .uri("/v2/orders/mirror")
                .retrieve()
                .body(OrderView.class);
    }

    // post() -> uri() -> body(Object) -> retrieve() -> body(Class): the
    // request body step sits between uri and retrieve, same as WebClient's
    // bodyValue but named `body` on this fluent surface.
    public OrderView submitMirror(OrderRequest request) {
        return restClient.post()
                .uri("/v2/orders/mirror")
                .body(request)
                .retrieve()
                .body(OrderView.class);
    }
}
