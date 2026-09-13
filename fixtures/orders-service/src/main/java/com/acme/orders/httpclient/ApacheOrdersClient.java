// Apache HttpClient 5 (`apache-httpclient`, spec §12/§14): the two ways a classic request is
// spelled. The builder form — `ClassicRequestBuilder.get("…").build()` handed to `execute` —
// is `okhttp.yml`'s exact shape, a static root joined to the client through the argument
// `source` id. The constructor form — `new HttpPost("…")`, `new HttpGet(URI.create(…))` —
// is a `<init>` root that is ITSELF the value handed to `execute`, with no `build()` between.
package com.acme.orders.httpclient;

import java.io.IOException;
import java.net.URI;
import org.apache.hc.client5.http.classic.methods.HttpGet;
import org.apache.hc.client5.http.classic.methods.HttpPost;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.core5.http.ClassicHttpRequest;
import org.apache.hc.core5.http.io.support.ClassicRequestBuilder;

public class ApacheOrdersClient {
    private final CloseableHttpClient client = HttpClients.createDefault();

    public String list() throws IOException {
        ClassicHttpRequest request = ClassicRequestBuilder.get("https://orders.example.com/v1/orders").build();
        return client.execute(request, response -> String.valueOf(response.getCode()));
    }

    public String create() throws IOException {
        HttpPost post = new HttpPost("https://orders.example.com/v1/orders");
        return client.execute(post, response -> String.valueOf(response.getCode()));
    }

    public String fetch() throws IOException {
        HttpGet get = new HttpGet(URI.create("https://orders.example.com/v1/orders/7"));
        return client.execute(get, response -> String.valueOf(response.getCode()));
    }
}
