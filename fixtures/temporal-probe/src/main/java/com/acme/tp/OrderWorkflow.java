package com.acme.tp;

import io.temporal.workflow.QueryMethod;
import io.temporal.workflow.SignalMethod;
import io.temporal.workflow.UpdateMethod;
import io.temporal.workflow.WorkflowInterface;
import io.temporal.workflow.WorkflowMethod;

/**
 * Every naming branch CP-30 measured, on one interface. Implemented in this
 * module by {@link OrderWorkflowImpl}, which carries the Spring Boot starter
 * annotation ({@code @WorkflowImpl}) — under the design's §2d/controller-ruling
 * catalog shape (`declared_on: interface` + `resolves.direction` keyed on
 * {@code owner_implemented_by_type_annotated: [WorkflowImpl]}), that flips
 * this interface's row to INBOUND rather than subtracting it, and every name
 * below is read off THIS interface (the contract), never off the implementor.
 */
@WorkflowInterface
public interface OrderWorkflow {

    // No explicit name -> falls back to `declaring_type_simple_name`, which
    // reads the type that DECLARED the annotation (this interface) even
    // though the row's handler is the implementor's override (M1, CP-30 Q1).
    // -> "OrderWorkflow"
    @WorkflowMethod
    void processOrder(String id);

    // `construct_name`, composed `<workflow type>/<member>` with the workflow
    // type from the same `declaring_type_simple_name` read above.
    // -> "OrderWorkflow/cancel"
    @SignalMethod
    void cancel(String reason);

    // -> "OrderWorkflow/status"
    @QueryMethod
    String status();

    // -> "OrderWorkflow/amend"
    @UpdateMethod
    String amend(String patch);

    // No Temporal annotation at all -> not a member of any Temporal-driven
    // catalog; derives NOTHING.
    default String helper() {
        return "x";
    }
}
