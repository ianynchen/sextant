package com.acme.pv;

import org.springframework.web.client.RestTemplate;

/**
 * A path segment built from a method PARAMETER — `single_call`'s engine.
 *
 * <p>The published path is `/owners/{ownerId}/pets`: the pattern is fully determined and the
 * variable is NAMED after the parameter that fills it, which is how the server states the
 * same route (`@GetMapping("/owners/{ownerId}/pets")`). An anonymous `{}` said "something
 * here" about a value the facts name.
 */
public class OwnerRestClient {

    private final RestTemplate restTemplate = new RestTemplate();

    public String pets(int ownerId) {
        return restTemplate.getForObject(
            "http://customers-service/owners/" + ownerId + "/pets", String.class);
    }

    /** Two variables in one address, and a literal between them. */
    public String visits(int ownerId, int petId) {
        return restTemplate.getForObject(
            "http://visits-service/owners/" + ownerId + "/pets/" + petId + "/visits",
            String.class);
    }

    /** A hole with NO name to take: the operand is a call's result, so `{}` is the honest
     *  answer and the row says the pattern is partly known.
     *
     *  <p>The QUERY STRING comes off the address (`OI-151`), so the row publishes
     *  `/pets/visits` — what `visits-service` serves — and each parameter is an
     *  `endpoint_metadata` entry. The row stays `partial` because `petId`'s VALUE was not
     *  read, which the entry also says. `token` is here because this engine became a writer
     *  of that table with `OI-151` and a value it writes must be masked where it is read. */
    public String batch(java.util.List<Integer> petIds) {
        return restTemplate.getForObject(
            "http://visits-service/pets/visits?petId=" + join(petIds) + "&token=sk-live-pv",
            String.class);
    }

    private String join(java.util.List<Integer> petIds) {
        return petIds.toString();
    }
}
