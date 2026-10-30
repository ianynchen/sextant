package com.acme.dc;

import org.springframework.web.client.RestTemplate;

/**
 * A helper that builds its address from a host String, called with a literal and with a String
 * its own caller supplied.
 *
 * <p>`fetch` is two calling contexts: one names `billing-service`, the other reads nothing. Each
 * context is its own row: the literal one names its peer at `resolved`, and the one reading
 * nothing states the path it knows at `partial` with no peer. Before a concatenation hole kept
 * the context it could not fill, the second call was dropped and only the `billing-service`
 * row existed, as if that were the one host the helper reaches.
 */
public class StringHostClient {

    private final RestTemplate restTemplate = new RestTemplate();

    private String fetch(String host) {
        return restTemplate.getForObject("http://" + host + "/stock", String.class);
    }

    public String viaLiteral() {
        return fetch("billing-service");
    }

    public String viaSuppliedHost(String supplied) {
        return fetch(supplied);
    }
}
