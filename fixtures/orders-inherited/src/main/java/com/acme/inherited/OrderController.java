package com.acme.inherited;

import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Overrides nothing: serves `GET /orders/list` and `POST /orders` through the base. */
@RestController
@RequestMapping("/orders")
public class OrderController extends CrudController<Order> {
}
