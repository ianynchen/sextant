package com.acme.api;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

/** The CALLING side. Three calls, one per outcome the matcher has to distinguish.
 *  Under `@Profile("prod")` since 2026-10-22 (spec 2026-10-22-conditional-beans): the
 *  client is a bean that exists in `prod` only, so every call it makes does — a property of
 *  the OUTBOUND endpoint, which the link states beside its calling side just as it states
 *  where the inbound endpoint exists. */
@Profile("prod")
@Component
public class BillingClient {

    private final RestTemplate restTemplate = new RestTemplate();

    /** Links: the client states `billing`, which is what `billing-api` registers as, and
     *  `/balances` is a route it serves. One endpoint link at `declared`. */
    public String balances() {
        return restTemplate.getForObject("http://billing/balances", String.class);
    }

    /** Does NOT link: nothing in this reactor is called `payments`. An unmatched outbound
     *  endpoint — M06's "a service outside the system, a participant nobody added, or a
     *  dependency nobody documented" — and never a link to whoever happens to serve it. */
    public String external() {
        return restTemplate.getForObject("http://payments/charges", String.class);
    }

    /** Does NOT link: the host comes from outside and the path is read, so the row is
     *  `<host>/balances`. `billing` serves `/balances` UNIQUELY, and this still refuses —
     *  the user's decision 6, because uniqueness inside the reactor cannot rule out a
     *  target outside it. */
    public String viaUnreadHost(String base) {
        return restTemplate.getForObject(base + "/balances", String.class);
    }
}
