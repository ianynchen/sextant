package com.acme.tp;

import io.temporal.workflow.WorkflowInterface;
import io.temporal.workflow.WorkflowMethod;

/**
 * Nothing in this module implements this interface. Proves the default
 * (explicit-name) branch of M1 AGAINST the fallback {@link OrderWorkflow}
 * proves, and — because no implementor carries {@code @WorkflowImpl} — the
 * `resolves.direction` condition never fires, so this stays the catalog's
 * DEFAULT direction (outbound), unsubtracted (nothing implements it here to
 * fence it).
 */
@WorkflowInterface
public interface ShipmentWorkflow {

    // Explicit name wins over the fallback outright — the prefix/fallback
    // machinery is never reached, by construction (M1).
    // -> one outbound row, "ShipOrder"
    @WorkflowMethod(name = "ShipOrder")
    void ship(String id);
}
