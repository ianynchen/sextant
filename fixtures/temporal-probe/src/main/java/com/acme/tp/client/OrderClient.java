package com.acme.tp.client;

import com.acme.tp.OrderWorkflow;
import io.temporal.client.WorkflowClient;
import io.temporal.client.WorkflowStub;

/**
 * The three call-site arms §2f/§2g draw a boundary around: one that derives
 * a row, and two that must derive nothing.
 */
public class OrderClient {

    // `WorkflowClient.newUntypedWorkflowStub(String, ...)` — the string
    // argument is the workflow TYPE (M10), so this row's path matches what
    // the inbound catalog derives for `OrderWorkflow` itself.
    // -> one outbound row, "OrderWorkflow" (`temporal-untyped.yml`)
    public WorkflowStub startUntyped(WorkflowClient client) {
        return client.newUntypedWorkflowStub("OrderWorkflow");
    }

    // `WorkflowStub.signal(String, Object...)` names a MEMBER with no
    // workflow type anywhere at the call site — the bare path "cancel" would
    // collide with every other workflow's signal of that name (§2f).
    // Under-reporting is honest; this is NOT declared as a catalog row.
    // -> derives NOTHING
    public void signalUntyped(WorkflowStub stub) {
        stub.signal("cancel", "late");
    }

    // `WorkflowClient.newWorkflowStub(Class, String workflowId)` addresses a
    // RUNNING execution and starts nothing — no call site is read for it at
    // all under §2 (§2g).
    // -> derives NOTHING
    public OrderWorkflow attachToRunning(WorkflowClient client) {
        return client.newWorkflowStub(OrderWorkflow.class, "wf-123");
    }
}
