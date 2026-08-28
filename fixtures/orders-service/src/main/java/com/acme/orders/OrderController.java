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

    private final OrderService service = new OrderService();

    @PostMapping
    public OrderResult create(@RequestBody OrderCommand command) {
        return service.place(command);
    }

    @GetMapping("/{id}")
    public OrderResult get(@PathVariable long id) {
        return service.find(id);
    }

    @GetMapping
    public List<OrderResult> list() {
        return service.list();
    }
}
