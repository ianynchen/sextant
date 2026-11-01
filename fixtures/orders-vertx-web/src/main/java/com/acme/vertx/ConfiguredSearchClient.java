package com.acme.vertx;

import io.vertx.core.Future;
import io.vertx.core.Vertx;
import io.vertx.core.buffer.Buffer;
import io.vertx.ext.web.client.HttpResponse;
import io.vertx.ext.web.client.WebClient;
import io.vertx.ext.web.client.WebClientOptions;

/**
 * Hono's shape (`AbstractProtocolAdapterApplication.prometheusResourceLimitChecks`): the
 * options are configured statement by statement from a config object's getters, beside
 * calls that set no address, and the config object is handed in by the framework, so where
 * its host comes from is outside this module.
 */
public class ConfiguredSearchClient {

    private final WebClient client;

    public ConfiguredSearchClient(Vertx vertx, SearchConfig config) {
        WebClientOptions options = new WebClientOptions();
        options.setConnectTimeout(config.getConnectTimeout());
        options.setDefaultHost(config.getHost());
        options.setDefaultPort(config.getPort());
        options.setSsl(config.isTlsEnabled());
        this.client = WebClient.create(vertx, options);
    }

    public Future<HttpResponse<Buffer>> suggest() {
        return client.get("/suggest").send();
    }

    /** Names its own host, so only the default port is the client's. */
    public Future<HttpResponse<Buffer>> alternate() {
        return client.get("search-alt", "/alt").send();
    }
}
