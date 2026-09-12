package com.acme.recv;

import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.core.ParameterizedTypeReference;

/** Synchronous receives the way a batch job or a poller writes them. */
public class RabbitReceivers {
    private final RabbitTemplate template;

    public RabbitReceivers(RabbitTemplate template) {
        this.template = template;
    }

    public Message pollRaw() {
        return template.receive("recv.orders.raw");
    }

    public Object pollConverted() {
        return template.receiveAndConvert("recv.orders.converted", 500L);
    }

    public OrderEvent pollTyped() {
        return template.receiveAndConvert("recv.orders.typed",
                new ParameterizedTypeReference<OrderEvent>() {});
    }

    public boolean serveOne() {
        return template.receiveAndReply("recv.orders.rpc", (OrderEvent e) -> new OrderEvent(e.id(), "served"));
    }

    public record OrderEvent(String id, String status) {}
}
