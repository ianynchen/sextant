// JDK `HttpClient` (`jdk-httpclient`, spec §14): the builder chain `okhttp.yml` already reads on
// OkHttp — a static root, verb-setting steps, `build()` handed to `send`. Both `newBuilder`
// overloads; `uri(URI.create(…))` and `uri(new URI(…))`; `method("PATCH", …)`; a request
// built in a helper and sent elsewhere — nothing, `fluent`'s split-builder rule (spec §13 case 9).
//
// `dispatch.example.com/v1/dispatches`, not `/v1/orders`: `OrdersLoopClient` already calls
// `POST /v1/orders` through Feign, and the annotation-driven insert dedups on wire identity
// alone (`insert_endpoints.sql`: protocol, direction, method, path — no caller, no peer),
// so a call-side row minted first on that identity would DROP the Feign row. Measured on
// this fixture (A2 Task 8); logged for the register, and the fixture stays off the path.
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
            .uri(URI.create("https://dispatch.example.com/v1/dispatches"))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(body))
            .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString()).body();
    }

    public String fetch(String id) throws Exception {
        return client.send(HttpRequest.newBuilder(new URI("https://dispatch.example.com/v1/dispatches/" + id)).GET().build(),
                           HttpResponse.BodyHandlers.ofString()).body();
    }

    public void patch(String id, String body) {
        client.sendAsync(HttpRequest.newBuilder(URI.create("https://dispatch.example.com/v1/dispatches/42"))
                             .method("PATCH", HttpRequest.BodyPublishers.ofString(body)).build(),
                         HttpResponse.BodyHandlers.discarding());
    }

    public String viaHelper() throws Exception {
        return client.send(deleteRequest(), HttpResponse.BodyHandlers.ofString()).body();
    }

    private HttpRequest deleteRequest() {
        return HttpRequest.newBuilder(URI.create("https://dispatch.example.com/v1/dispatches/42")).DELETE().build();
    }
}
