package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.Vertx;
import io.vertx.core.buffer.Buffer;
import io.vertx.ext.web.client.HttpResponse;
import io.vertx.ext.web.client.WebClient;
import io.vertx.ext.web.client.WebClientOptions;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

/** The same, with the host from a config getter backed by `application.properties`. */
public class ConfiguredSearchClient {

    private final WebClient client;

    public ConfiguredSearchClient(Vertx vertx) {
        this.client = WebClient.create(vertx, new WebClientOptions().setDefaultHost(getHost()));
    }

    String getHost() {
        Properties properties = new Properties();
        try (InputStream in = ConfiguredSearchClient.class.getResourceAsStream("/application.properties")) {
            properties.load(in);
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
        return properties.getProperty("search.host");
    }

    public Future<HttpResponse<Buffer>> suggest() {
        return client.get("/suggest").send();
    }
}
