package com.acme.tp.client;

import io.temporal.workflow.WorkflowInterface;
import io.temporal.workflow.WorkflowMethod;

/**
 * The client-side contract this module does NOT implement — proves the
 * outbound (interface-declared) row a caller-only module derives, with no
 * implementor anywhere to flip its direction or fence it. Exactly one
 * {@code @WorkflowMethod} and nothing else (controller ruling), so the later
 * e2e assertion is exact.
 */
@WorkflowInterface
public interface PaymentsWorkflow {

    @WorkflowMethod
    void processPayment(String orderId);
}
