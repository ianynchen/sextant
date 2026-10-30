package com.acme.inherited;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Overrides nothing: serves `GET /orders/list` and `POST /orders` through the base, and
 * only where `orders.enabled` is `true` — the condition is this class's, never the base's.
 */
@RestController
@RequestMapping("/orders")
@ConditionalOnProperty(name = "orders.enabled", havingValue = "true")
public class OrderController extends CrudController<Order> {
}
