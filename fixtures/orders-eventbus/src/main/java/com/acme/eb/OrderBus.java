package com.acme.eb;

import io.vertx.core.Future;
import io.vertx.core.Vertx;
import io.vertx.core.eventbus.DeliveryOptions;
import io.vertx.core.eventbus.EventBus;
import io.vertx.core.eventbus.Message;
import io.vertx.core.eventbus.MessageConsumer;

/**
 * The raw event-bus arms of spec §4's second fixture: the one-call forms
 * (`vertx-eventbus.yml`), the two-step chains (`vertx-eventbus-chain.yml`), and the
 * handler-less consumer that must derive NOTHING (M6).
 */
public class OrderBus {

    private final EventBus bus;

    public OrderBus(Vertx vertx) {
        this.bus = vertx.eventBus();
    }

    /** One-call outbound, point-to-point. */
    public void placeOrder(Order order) {
        bus.send("orders.created", order);
    }

    /** One-call outbound, fan-out. */
    public void announceOrder(Order order) {
        bus.publish("orders.events", order);
    }

    /** One-call outbound with a reply. The reply type is not an ARGUMENT of the call. */
    public Future<Message<Order>> lookupOrder(Order order) {
        return bus.request("orders.lookup", order);
    }

    /** One-call outbound with delivery options — the three-argument overload. */
    public void placeOrderWithOptions(Order order) {
        bus.send("orders.priority", order, new DeliveryOptions().setSendTimeout(500L));
    }

    /** One-call inbound: the address and the handler arrive together. */
    public void receiveOrders() {
        bus.<Order>consumer("orders.inbox", message -> handle(message));
    }

    /** One-call inbound, node-local only. */
    public void receiveLocalOrders() {
        bus.<Order>localConsumer("orders.local", message -> handle(message));
    }

    /**
     * The two-step chain: `consumer(addr)` alone registers nothing, and `handler(h)` is
     * where the registration happens (M6). This arm derives one inbound row.
     */
    public void receiveOrdersInTwoSteps() {
        MessageConsumer<Order> consumer = bus.consumer("orders.twostep");
        consumer.handler(message -> handle(message));
    }

    /** The outbound chain: `sender(addr)` then `write(body)`. */
    public void shipOrder(Order order) {
        bus.sender("orders.shipments").write(order);
    }

    /**
     * THE ARM THAT MUST DERIVE NOTHING (spec §4, M6). `consumer(addr)` builds a
     * `MessageConsumer` and no handler is ever given to it, so the framework registers
     * nothing and this address receives no message. A row here would be an endpoint
     * nobody serves.
     */
    public void prepareUnhandledConsumer() {
        MessageConsumer<Order> consumer = bus.consumer("orders.unhandled");
        consumer.setMaxBufferedMessages(16);
    }

    private void handle(Message<Order> message) {
        Order order = message.body();
        if (order != null) {
            order.getId();
        }
    }
}
