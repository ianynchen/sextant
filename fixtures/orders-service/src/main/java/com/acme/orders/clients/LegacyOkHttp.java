// OkHttp has no fluent client object to chain off of: Request.Builder
// builds a value that is handed to a separate OkHttpClient call, so the two
// halves are only joined by the `source` id on newCall's argument — the
// join spring-webclient.yml and spring-restclient.yml never need. No
// lambdas anywhere in this file: every step is a plain method call.
package com.acme.orders.clients;

import java.io.IOException;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

public class LegacyOkHttp {
    private final OkHttpClient client;

    public LegacyOkHttp(OkHttpClient client) {
        this.client = client;
    }

    // build() and newCall() are two separate call sites; the request value
    // build() returns is the argument newCall() consumes, and that argument's
    // `source` id is the only thing that reconstructs this as one chain.
    public Response fetchExports() throws IOException {
        Request request = new Request.Builder()
                .url("https://legacy.acme.internal/legacy/exports")
                .get()
                .build();
        return client.newCall(request).execute();
    }

    // Same split, POST verb: post(RequestBody) carries the body argument
    // directly, no separate body-step call the way WebClient/RestClient
    // need one.
    public Response submitExport(String payload) throws IOException {
        RequestBody body = RequestBody.create(payload, MediaType.get("application/json"));
        Request request = new Request.Builder()
                .url("https://legacy.acme.internal/legacy/exports")
                .post(body)
                .build();
        return client.newCall(request).execute();
    }
}
