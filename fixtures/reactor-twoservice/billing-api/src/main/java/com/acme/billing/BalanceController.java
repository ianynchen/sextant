package com.acme.billing;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** The SERVED side of the link: `billing-api` registers as `billing` and serves this. */
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
