package com.acme.orders.clients;

import com.acme.orders.contracts.OrderView;
import org.springframework.web.client.RestTemplate;

// F5 §6.1 rule 1: TWO CALLERS, ONE PATH, TWO HOSTS — and therefore two rows.
//
// This is the shape nothing in six repositories had, which is why the defect it pins
// survived W27: the `seen` set in `single_call`/`fluent` spanned the whole module and
// keyed on `(protocol, direction, verb, path)`, so the second caller was dropped
// OUTRIGHT — no row, no peer, no gap row, no open question. `peer` is not part of
// endpoint identity (RC-5) and that is exactly why it has to be in the dedup key: two
// calls to one path at two addresses are two calls, and only the address separates them.
//
// `alpha` and `bravo` differ in host as well as caller, so a fix that keyed on the caller
// alone would still pass while leaving the address half of RC-5 unaddressed.
public class SharedPathClients {
    private final RestTemplate restTemplate;

    public SharedPathClients(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public OrderView alpha() {
        return restTemplate.getForObject("http://alpha.internal/shared/path", OrderView.class);
    }

    public OrderView bravo() {
        return restTemplate.getForObject("http://bravo.internal/shared/path", OrderView.class);
    }
}
