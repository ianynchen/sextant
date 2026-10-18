package com.acme.pp.controller.admin;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Served at `/admin-api/orders/{id}` — and nothing here says `/admin-api`. The only
 *  evidence is the prefix map in `PrefixConfig`, keyed on this class's PACKAGE. */
@RestController
@RequestMapping("/orders")
public class AdminOrderController {

    @GetMapping("/{id}")
    public String get(String id) {
        return id;
    }
}
