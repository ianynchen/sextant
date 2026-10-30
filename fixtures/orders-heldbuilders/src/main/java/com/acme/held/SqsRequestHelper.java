package com.acme.held;

import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

/** A request STARTED in a helper and finished and sent by its caller (ruling 5, spec
 *  2026-10-30): `base()` returns the builder with its queue set, and `send` adds the body,
 *  builds and sends. Read by the cross-method walk. */
public class SqsRequestHelper {
    private final SqsClient client;

    public SqsRequestHelper(SqsClient client) {
        this.client = client;
    }

    public void send(String body) {
        client.sendMessage(base().messageBody(body).build());
    }

    private SendMessageRequest.Builder base() {
        return SendMessageRequest.builder()
                .queueUrl("https://sqs.us-east-1.amazonaws.com/123456789012/helper-orders");
    }
}
