package com.acme.pp.controller.ops;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Served at `/ops-api/orders/{id}`. Its prefix and `InternalOrderController`'s are
 *  declared at the SAME call site, which is what makes the pairing a real question: the
 *  walk reaches both prefixes and both patterns from there. */
@RestController
@RequestMapping("/orders")
public class OpsOrderController {

    @GetMapping("/{id}")
    public String get(String id) {
        return id;
    }
}
