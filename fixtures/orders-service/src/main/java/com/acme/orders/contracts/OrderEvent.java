package com.acme.orders.contracts;

import java.math.BigDecimal;
import java.time.Instant;

// The messaging layer's payload type: the value carried on every Kafka, JMS,
// SQS and PubSub call the fixture makes (Phase 2D). A plain first-party DTO,
// same shape-expansion rules as OrderRequest/OrderView, just routed through a
// broker instead of a wire endpoint.
public class OrderEvent {
    public String orderId;
    public BigDecimal total;
    public Instant placedAt;
}
