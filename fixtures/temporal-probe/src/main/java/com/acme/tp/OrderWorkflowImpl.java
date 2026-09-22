package com.acme.tp;

import io.temporal.spring.boot.WorkflowImpl;

/**
 * The starter annotation is load-bearing evidence, not decoration (task-6
 * brief): {@code @WorkflowImpl(taskQueues = "orders")} is what the
 * `resolves.direction` rule reads to flip {@link OrderWorkflow}'s row to
 * INBOUND, and its `taskQueues` attribute is what {@code metadata_from} turns
 * into the workflow row's `task_queue` metadata ("orders"). Every interface
 * method is overridden so the inheritance walk has a real (non-synthetic)
 * annotation row to reach on each one.
 */
@WorkflowImpl(taskQueues = "orders")
public class OrderWorkflowImpl implements OrderWorkflow {

    @Override
    public void processOrder(String id) {
        // never runs
    }

    @Override
    public void cancel(String reason) {
        // never runs
    }

    @Override
    public String status() {
        return "";
    }

    @Override
    public String amend(String patch) {
        return "";
    }

    @Override
    public String helper() {
        return "x";
    }
}
