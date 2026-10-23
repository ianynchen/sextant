// A client the `prod` profile alone wires (ConditionalClientsConfig#auditClient): its outbound
// `POST http://audit/events` exists only where that bean does, and the document states so.
package com.acme.orders.conditional;

import org.springframework.web.client.RestTemplate;

public class HttpAuditClient implements AuditClient {
    private final RestTemplate restTemplate;

    public HttpAuditClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    @Override
    public void record(String event) {
        restTemplate.postForObject("http://audit/events", event, String.class);
    }
}
