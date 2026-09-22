package com.acme.eb;

import io.quarkus.vertx.ConsumeEvent;
import io.vertx.core.MultiMap;
import io.vertx.core.eventbus.Message;

/**
 * The Quarkus arm of spec §4's second fixture. Six `@ConsumeEvent` methods, one per rule
 * `quarkus-consume-event.yml` carries:
 *
 * <ul>
 *   <li>an explicit address;
 *   <li>a BARE annotation, whose address is this class's fully-qualified name (M8);
 *   <li>`local = false`, the cluster-reachable consumer;
 *   <li>a `${…}` address, carried verbatim and unresolved;
 *   <li>a `(MultiMap, Order)` method — Quarkus's own headers/body split, where the
 *       payload is the SECOND parameter;
 *   <li>a `Message&lt;Order&gt;` method on the SAME address as the first one — the bus's
 *       own envelope, whose payload is what the envelope holds.
 * </ul>
 */
public class OrderConsumers {

    @ConsumeEvent("orders.created")
    public void onOrderCreated(Order order) {
        order.getId();
    }

    /** No attribute at all: the address is `com.acme.eb.OrderConsumers` (M8). */
    @ConsumeEvent
    public void onAnyOrder(Order order) {
        order.getQuantity();
    }

    /** `local()` defaults to true, so this is the one consumer reachable across a cluster. */
    @ConsumeEvent(value = "orders.cluster", local = false)
    public void onClusteredOrder(Order order) {
        order.getId();
    }

    /** A placeholder the framework resolves out of configuration at startup. */
    @ConsumeEvent("${orders.address}")
    public void onConfiguredOrder(Order order) {
        order.getId();
    }

    /** Headers first, body second — the split Quarkus's own processor enforces. */
    @ConsumeEvent("orders.headers")
    public void onOrderWithHeaders(MultiMap headers, Order order) {
        headers.get("tenant");
        order.getId();
    }

    /**
     * The SECOND spelling of `orders.created`, and the one this arm exists for: the
     * parameter is the bus's own envelope rather than the payload. Quarkus permits it —
     * `VertxProcessor` requires only that such a method return `void` (CP-31 Q12,
     * quarkus-vertx-deployment 3.17.5), which is why this one does — so a real module can
     * spell the same wire contract either way. What crossed the wire is `body()`, so this
     * row's `request_shape` must be `Order`, EQUAL to `onOrderCreated`'s above; a row that
     * recorded `Message` instead would put two shapes on one address and neither half of a
     * request/reply pair would link, since the consumer answering one replies with an
     * `Order`.
     */
    @ConsumeEvent("orders.created")
    public void onOrderCreatedEnvelope(Message<Order> message) {
        message.body().getId();
    }
}
