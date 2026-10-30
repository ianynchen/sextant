package com.acme.held;

import java.io.IOException;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;

/** One request helper, two callers, each with its own service (ruling 5, spec 2026-10-30):
 *  `req(svc)` returns a builder whose address holds the caller's argument, and each caller
 *  builds and sends it. Two rows, one per caller, each with its own peer. */
public class OkHttpRequestHelper {
    private final OkHttpClient client;

    public OkHttpRequestHelper(OkHttpClient client) {
        this.client = client;
    }

    public Response callA() throws IOException {
        return client.newCall(req("svc-a").build()).execute();
    }

    public Response callB() throws IOException {
        return client.newCall(req("svc-b").build()).execute();
    }

    private Request.Builder req(String svc) {
        return new Request.Builder().url("http://" + svc + "/x");
    }
}
