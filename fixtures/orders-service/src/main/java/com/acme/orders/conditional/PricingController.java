// Calls `PricingPolicy#price` through an injected field. The candidates are `StandardPricing` (a
// `@ConditionalOnMissingBean` default) and `PromoPricing` (`@Profile("prod")`).
package com.acme.orders.conditional;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PricingController {
    @Autowired
    private PricingPolicy policy;

    @GetMapping("/pricing")
    public long price() {
        return policy.price("sku");
    }
}
