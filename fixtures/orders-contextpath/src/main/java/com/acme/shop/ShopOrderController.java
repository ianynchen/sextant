package com.acme.shop;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * An ordinary controller in a module whose `application.properties` sets a context path and a
 * DispatcherServlet path. Nothing here says so — which is the point: the served address is
 * `/shop/api/orders/{id}`, and the only evidence for `/shop/api` is configuration.
 */
@RestController
@RequestMapping("/orders")
public class ShopOrderController {

    @GetMapping("/{id}")
    public String get(@PathVariable String id) {
        return id;
    }

    @PostMapping
    public String create() {
        return "created";
    }
}
