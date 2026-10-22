// The second condition the cell reads: `@ConditionalOnProperty` — the bean exists where
// `orders.legacy` resolves to `true`, which `application-prod.yml` sets and `application.yml`
// does not (CP-43: a `havingValue` compares case-insensitively; an absent key is decided by
// `matchIfMissing`, false here). The verdict per environment comes from `resolved_config`.
package com.acme.orders.conditional;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@ConditionalOnProperty(name = "orders.legacy", havingValue = "true")
@RestController
public class LegacyOrdersController {
    @GetMapping("/legacy/orders/all")
    public String all() {
        return "[]";
    }
}
