package com.acme.orders;

import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/orders")
public class OrderController {

    @GetMapping
    public List<String> list() {
        return List.of();
    }

    @GetMapping("/{id}")
    public String get(@PathVariable long id) {
        return "order-" + id;
    }

    @PostMapping
    public String create(@RequestBody String body) {
        return body;
    }
}
