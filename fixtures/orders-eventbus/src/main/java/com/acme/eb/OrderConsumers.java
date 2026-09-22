package com.acme.eb;

import io.quarkus.vertx.ConsumeEvent;
import io.vertx.core.MultiMap;

/**
 * The Quarkus arm of spec §4's second fixture. Five `@ConsumeEvent` methods, one per rule
 * `quarkus-consume-event.yml` carries:
 *
 * <ul>
 *   <li>an explicit address;
 *   <li>a BARE annotation, whose address is this class's fully-qualified name (M8);
 *   <li>`local = false`, the cluster-reachable consumer;
 *   <li>a `${…}` address, carried verbatim and unresolved;
 *   <li>a `(MultiMap, Order)` method — Quarkus's own headers/body split, where the
 *       payload is the SECOND parameter.
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
}
