package com.example.orders.ws;
import com.acme.orders.contracts.OrderView;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Component;

/** The OUTBOUND half of this module's STOMP surface (W43). `OrderStompController`
 *  receives; nothing here sent, so the module was published with half its
 *  messaging boundary and nothing saying which half. */
@Component
public class OrderStompPublisher {

    private final SimpMessagingTemplate template;

    public OrderStompPublisher(SimpMessagingTemplate template) { this.template = template; }

    /** The destination is a String in the source and an Object in the descriptor:
     *  `convertAndSend` is declared on `MessageSendingOperations<D>` and `D` erases. */
    public void announce(OrderView order) {
        template.convertAndSend("/topic/order-announced", order);
    }

    /** No destination argument at all — the template's configured default carries
     *  it — so this publishes a boundary with an unresolved address rather than
     *  vanishing. */
    public void announceToDefault(OrderView order) {
        template.convertAndSend(order);
    }
}
