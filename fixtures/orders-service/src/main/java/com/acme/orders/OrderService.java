package com.acme.orders;

import java.util.List;

public class OrderService {
    public OrderResult place(OrderCommand command) { return new OrderResult(); }
    public OrderResult find(long id) { return new OrderResult(); }
    public List<OrderResult> list() { return List.of(); }
}
