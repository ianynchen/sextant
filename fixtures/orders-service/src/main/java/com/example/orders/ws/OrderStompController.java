package com.example.orders.ws;
import com.acme.orders.contracts.OrderView;
import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
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

    // W47, `G-35`: STOMP's error contract. The HTTP twin has shipped `error_handlers`
    // since 2O and this direction was absent from the checklist entirely, so a service
    // whose messaging errors ARE handled looked like one whose are not.
    //
    // No `@ResponseStatus` beside it, deliberately: there is no HTTP response here, and
    // the annotation would change nothing Spring does.
    @MessageExceptionHandler(IllegalArgumentException.class)
    public String onBadOrder(IllegalArgumentException failure) { return failure.getMessage(); }
}
