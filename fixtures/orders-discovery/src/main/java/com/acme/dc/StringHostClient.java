package com.acme.dc;

import org.springframework.web.client.RestTemplate;

/**
 * A helper that builds its address from a host String, called with a literal and with a String
 * its own caller supplied.
 *
 * <p>`fetch` is two calling contexts: one names `billing-service`, the other reads nothing. A
 * peer column states who is called, not who is called sometimes, so the row must publish no
 * peer. Before a concatenation hole kept the context it could not fill, the second call was
 * dropped and the row stated `billing-service` as if it were the only host.
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
