package com.acme.held;

import java.io.IOException;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

/** `okhttp.yml` in the variable style: the address and the verb are each set on the held
 *  builder in a statement of their own. One row, `POST https://h/orders`. */
public class HeldOkHttp {
    private final OkHttpClient client;

    public HeldOkHttp(OkHttpClient client) {
        this.client = client;
    }

    public Response submit(String payload) throws IOException {
        Request.Builder builder = new Request.Builder();
        builder.url("https://h/orders");
        builder.post(RequestBody.create(payload, MediaType.get("application/json")));
        return client.newCall(builder.build()).execute();
    }
}
