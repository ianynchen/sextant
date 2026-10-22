package com.acme.billing;

import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** The SERVED side of the link: `billing-api` registers as `billing` and serves this.
 *  Under `@Profile("prod")` since 2026-10-22 (spec 2026-10-21-conditional-controllers,
 *  ruling 2): the controller exists in `prod` only, which is a property of the INBOUND
 *  endpoint — the link to it is matched and kept as any other, and the system document
 *  states where the endpoint exists beside the link. */
@Profile("prod")
@RestController
public class BalanceController {

    @GetMapping("/balances")
    public String balances() {
        return "[]";
    }

    /** Served but never called from inside the reactor — an UNCALLED inbound endpoint,
     *  which is one of M06's two findings that are not errors. */
    @GetMapping("/ledgers")
    public String ledgers() {
        return "[]";
    }
}
