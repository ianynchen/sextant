package com.acme.eb;

import io.quarkus.vertx.ConsumeEvent;
import io.vertx.core.MultiMap;
import io.vertx.core.eventbus.Message;

/**
 * The Quarkus arm of spec §4's second fixture. Eight `@ConsumeEvent` methods, one per rule
 * `quarkus-consume-event.yml` carries:
 *
 * <ul>
 *   <li>an explicit address;
 *   <li>a BARE annotation, whose address is this class's fully-qualified name (M8);
 *   <li>`local = false`, the cluster-reachable consumer;
 *   <li>a `${…}` address, carried verbatim and unresolved;
 *   <li>a `(MultiMap, Order)` method — Quarkus's own headers/body split, where the
 *       payload is the SECOND parameter;
 *   <li>the SAME split spelled with the Mutiny `MultiMap`, which Quarkus's own
 *       `isMessageHeaders` accepts alongside the core one (CP-31 Q11);
 *   <li>a `Message&lt;Order&gt;` method on the SAME address as the first one — the bus's
 *       own envelope, whose payload is what the envelope holds;
 *   <li>the same envelope spelled with the Mutiny `Message`, the second type
 *       `isMessage` accepts.
 * </ul>
 *
 * <p>The last four are deliberately PAIRED — core spelling and Mutiny spelling of one rule
 * — because the catalog entry each proves is a pair too, and a list with one arm per pair
 * would leave the second entry of each declared and unexercised.
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

    /**
     * The headers/body split spelled with the MUTINY `MultiMap`. MEASURED (CP-31 Q11,
     * quarkus-vertx-deployment 3.17.5): `VertxConstants.isMessageHeaders` accepts
     * `io.vertx.mutiny.core.MultiMap` exactly as it accepts the core one, so this is the
     * same rule as `onOrderWithHeaders` above and not a second one. It is the mainstream
     * spelling in a Quarkus service, which injects the Mutiny facade throughout — and
     * `io.vertx.mutiny.core.eventbus.Message.headers()` returns this type (CP-31 Q10c), so
     * a handler that read headers off the envelope and then declared them as a parameter
     * would reach for this name rather than the core one. Its payload is `Order`, its
     * SECOND parameter, identical to its core sibling.
     */
    @ConsumeEvent("orders.mutiny.headers")
    public void onMutinyHeaderOrder(io.vertx.mutiny.core.MultiMap headers, Order order) {
        headers.get("tenant");
        order.getId();
    }

    /**
     * The envelope spelled with the MUTINY `Message`, the second type `isMessage` accepts
     * (CP-31 Q11). A different type from its core sibling — a class holding the core
     * interface in a private `delegate` field, whose `headers()` returns the Mutiny
     * `MultiMap` (CP-31 Q10c) — and the same wire contract, so its `request_shape` is
     * `Order` too. `void`, for the return-type rule CP-31 Q12 measured.
     */
    @ConsumeEvent("orders.mutiny.created")
    public void onMutinyOrderEnvelope(io.vertx.mutiny.core.eventbus.Message<Order> message) {
        message.body().getId();
    }
}
