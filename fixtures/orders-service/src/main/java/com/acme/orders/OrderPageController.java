package com.acme.orders;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;

// A server-rendered controller — `@Controller`, not `@RestController` — so
// the fixture also exercises the spring-mvc catalog, not just spring-web.
@Controller
@RequestMapping("/orders")
public class OrderPageController {

    @GetMapping
    public String list() {
        return "orders/list";
    }

    @PostMapping("/new")
    public String create() {
        return "redirect:/orders";
    }
}
