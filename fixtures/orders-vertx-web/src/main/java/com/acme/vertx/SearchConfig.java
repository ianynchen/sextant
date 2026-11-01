package com.acme.vertx;

/**
 * A configuration object a framework fills from its own sources, as Hono's are; its port is
 * a fixed constant, as Hono's `DEFAULT_*` values are.
 */
public class SearchConfig {

    public static final int DEFAULT_PORT = 9200;

    private String host;
    private int connectTimeout;
    private boolean tlsEnabled;

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public int getPort() {
        return DEFAULT_PORT;
    }

    public int getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(int connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public boolean isTlsEnabled() {
        return tlsEnabled;
    }

    public void setTlsEnabled(boolean tlsEnabled) {
        this.tlsEnabled = tlsEnabled;
    }
}
