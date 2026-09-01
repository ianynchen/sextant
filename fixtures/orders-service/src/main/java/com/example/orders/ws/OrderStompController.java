package com.example.orders.ws;
import com.acme.orders.contracts.OrderView;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.annotation.SubscribeMapping;
import org.springframework.stereotype.Controller;

@Controller
@MessageMapping("/orders")
public class OrderStompController {

    @MessageMapping("/place")             // composes to /orders/place
    @SendTo("/topic/order-placed")
    public OrderView place(OrderView order) { return order; }

    @SubscribeMapping("/board")           // composes to /orders/board
    public OrderView board() { return null; }
}
