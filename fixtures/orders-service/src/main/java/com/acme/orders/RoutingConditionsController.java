package com.acme.orders;

import com.acme.orders.contracts.OrderView;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

// W28. Two handlers on ONE address that Spring registers happily, because a condition
// separates them — the false positive a duplicate detector has to not report.
//
// `RequestMappingInfo.equals` compares seven conditions and `params` is one of them, so
// these two are different mappings however identical their path and verb look. Measured
// across all six corpora before this was written: `params=` and `headers=` appear
// ZERO times, so nothing else here exercises the attribute the detector reads.
@RestController
@RequestMapping("/v1/routing")
public class RoutingConditionsController {

    @GetMapping(value = "/orders", params = "view=summary")
    public OrderView summary() {
        return null;
    }

    @GetMapping(value = "/orders", params = "view=full")
    public OrderView full() {
        return null;
    }

    // A third handler on the same path and verb, separated by a HEADER rather than a
    // parameter — the other discriminator, and the one that would go unread if the
    // catalog named only `params`.
    @GetMapping(value = "/orders", headers = "X-Orders-Api=2")
    public OrderView versioned() {
        return null;
    }
}
