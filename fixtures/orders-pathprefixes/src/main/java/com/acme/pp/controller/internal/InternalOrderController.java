package com.acme.pp.controller.internal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Served at `/internal-api/orders/{id}`, through the prefix `PrefixConfig.putPathPrefix`
 *  installs from an `ApiGroups.Api` object — `ruoyi`'s own shape, where ONE `put` site
 *  declares every prefix and the prefix must be paired with its own pattern. */
@RestController
@RequestMapping("/orders")
public class InternalOrderController {

    @GetMapping("/{id}")
    public String get(String id) {
        return id;
    }
}
