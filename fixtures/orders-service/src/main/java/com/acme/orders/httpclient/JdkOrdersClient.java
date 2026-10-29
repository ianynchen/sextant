// JDK `HttpClient` (`jdk-httpclient`, spec §14): the builder chain `okhttp.yml` already reads on
// OkHttp — a static root, verb-setting steps, `build()` handed to `send`. Both `newBuilder`
// overloads; `uri(URI.create(…))` and `uri(new URI(…))`; `method("PATCH", …)`; a request
// built in a helper and sent elsewhere — one row, the execute-join follows the return (Task 6).
//
// `POST /v1/orders` is ALSO what `OrdersLoopClient` calls through Feign, on purpose (A2 Task
// 8 fix round 1): an outbound row is per caller and peer, so both rows stand — the
// annotation-driven insert used to compare wire identity alone and dropped the Feign row.
package com.acme.orders.httpclient;

import java.net.URI;
import java.net.URISyntaxException;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class JdkOrdersClient {
    private final HttpClient client = HttpClient.newHttpClient();

    public String create(String body) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://orders.example.com/v1/orders"))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(body))
            .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString()).body();
    }

    public String fetchSeventh() throws Exception {
        return client.send(HttpRequest.newBuilder(new URI("https://orders.example.com/v1/orders/7")).GET().build(),
                           HttpResponse.BodyHandlers.ofString()).body();
    }

    public String fetch(String id) throws Exception {
        return client.send(HttpRequest.newBuilder(new URI("https://orders.example.com/v1/orders/" + id)).GET().build(),
                           HttpResponse.BodyHandlers.ofString()).body();
    }

    public void patch(String id, String body) {
        client.sendAsync(HttpRequest.newBuilder(URI.create("https://orders.example.com/v1/orders/42"))
                             .method("PATCH", HttpRequest.BodyPublishers.ofString(body)).build(),
                         HttpResponse.BodyHandlers.discarding());
    }

    public String viaHelper() throws Exception {
        return client.send(deleteRequest(), HttpResponse.BodyHandlers.ofString()).body();
    }

    private HttpRequest deleteRequest() {
        return HttpRequest.newBuilder(URI.create("https://orders.example.com/v1/orders/42")).DELETE().build();
    }
}
