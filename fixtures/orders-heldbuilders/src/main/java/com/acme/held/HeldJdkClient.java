package com.acme.held;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

/** `jdk-httpclient.yml` in the variable style. One row, `POST https://h/orders`. */
public class HeldJdkClient {
    private final HttpClient client = HttpClient.newHttpClient();

    public String submit(String body) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder();
        builder.uri(URI.create("https://h/orders"));
        builder.header("Content-Type", "application/json");
        builder.POST(HttpRequest.BodyPublishers.ofString(body));
        return client.send(builder.build(), HttpResponse.BodyHandlers.ofString()).body();
    }
}
