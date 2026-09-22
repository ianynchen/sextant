package com.acme.eb;

import io.smallrye.mutiny.Uni;
import io.vertx.mutiny.core.Vertx;
import io.vertx.mutiny.core.eventbus.EventBus;
import io.vertx.mutiny.core.eventbus.Message;

/**
 * The Mutiny facade arm (fix round 1). `io.vertx.mutiny.core.eventbus.EventBus` is what a
 * Quarkus service injects, and CP-31 Q8 measured that it shares NO descriptor with
 * `io.vertx.core.eventbus.EventBus` — so `vertx-eventbus-mutiny.yml` is what reads these
 * four calls, not `vertx-eventbus.yml`.
 */
public class MutinyOrderBus {

    private final EventBus bus;

    public MutinyOrderBus(Vertx vertx) {
        this.bus = vertx.eventBus();
    }

    /** One-call outbound, point-to-point, through the facade. */
    public void placeOrder(Order order) {
        bus.send("mutiny.orders.created", order);
    }

    /** One-call outbound, fan-out. */
    public void announceOrder(Order order) {
        bus.publish("mutiny.orders.events", order);
    }

    /** Request/reply: the reply arrives in a `Uni`, which is the call's RETURN type. */
    public Uni<Message<Order>> lookupOrder(Order order) {
        return bus.request("mutiny.orders.lookup", order);
    }

    /** One-call inbound: the facade's consumer takes a `java.util.function.Consumer`. */
    public void receiveOrders() {
        bus.<Order>consumer("mutiny.orders.inbox", message -> handle(message));
    }

    private void handle(Message<Order> message) {
        Order order = message.body();
        if (order != null) {
            order.getId();
        }
    }
}
