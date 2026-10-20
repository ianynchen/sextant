package com.acme.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** One route behind the gateway, so the composition has exactly one endpoint to reach. */
@RestController
public class OrderController {

    @GetMapping("/orders")
    public String orders() {
        return "[]";
    }
}
