package com.acme.dc;

import java.net.URI;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.web.client.RestTemplate;

/**
 * `petclinic-genai`'s own shape: the peer is a service NAME and the host is a registry lookup.
 *
 * <p>Nothing here states an address. What the code states is `customers-service`, three calls
 * back from the position the catalog asks about — `getInstances(name)`, then `get(0)`, then
 * `getUri()`, and javac inserts `String.valueOf` around the `URI` operand of the
 * concatenation. The published row should name the PEER and take the path from the literal
 * beside it (`OI-142`'s ruling 2: peer and path from separate evidence).
 */
public class OwnerClient {

    private final RestTemplate restTemplate = new RestTemplate();
    private final DiscoveryClient discoveryClient;

    public OwnerClient(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    private URI customers() {
        return discoveryClient.getInstances("customers-service").get(0).getUri();
    }

    public String owners() {
        return restTemplate.getForObject(customers() + "/owners", String.class);
    }

    public String pets(int ownerId) {
        return restTemplate.getForObject(
            customers() + "/owners/" + ownerId + "/pets", String.class);
    }
}
