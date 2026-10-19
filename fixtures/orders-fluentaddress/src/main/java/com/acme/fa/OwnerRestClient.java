package com.acme.fa;

import org.springframework.web.client.RestTemplate;

/** The SAME assembled address through `RestTemplate` — the `single_call` engine. The two
 *  rows must agree: one piece of evidence, one answer. */
public class OwnerRestClient {

    private final RestTemplate restTemplate = new RestTemplate();

    public String owners(String base) {
        return restTemplate.getForObject(base + "/owners", String.class);
    }
}
