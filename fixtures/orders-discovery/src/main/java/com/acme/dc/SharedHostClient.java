package com.acme.dc;

import java.net.URI;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.web.client.RestTemplate;

/**
 * The same discovery lookup, reached through a helper that ANOTHER caller hands its own host.
 *
 * <p>`OwnerClient` is the honest shape: one caller, one authority, so the peer is that service.
 * Here the concat lives in `fetch`, and `fetch` is two calling contexts — one a registry lookup
 * naming `customers-service`, one a `URI` this module's own caller supplied and nothing in the
 * facts reads. A peer column states who is called, not who is called sometimes, so the row must
 * keep saying `<host>/orders` with no peer.
 *
 * <p>Measured before the refusal existed: peer `customers-service`, for a helper half of whose
 * calls go somewhere the code never states.
 */
public class SharedHostClient {

    private final RestTemplate restTemplate = new RestTemplate();
    private final DiscoveryClient discoveryClient;

    public SharedHostClient(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    private String fetch(URI host) {
        return restTemplate.getForObject(host + "/orders", String.class);
    }

    public String viaDiscovery() {
        return fetch(discoveryClient.getInstances("customers-service").get(0).getUri());
    }

    public String viaCallersHost(URI supplied) {
        return fetch(supplied);
    }
}
