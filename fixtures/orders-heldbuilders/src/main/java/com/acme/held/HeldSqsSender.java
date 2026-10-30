package com.acme.held;

import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

/** `aws-sqs-sdk.yml` in the variable style. One row, the queue `orders`. */
public class HeldSqsSender {
    private final SqsClient client;

    public HeldSqsSender(SqsClient client) {
        this.client = client;
    }

    public void send(String body) {
        SendMessageRequest.Builder builder = SendMessageRequest.builder();
        builder.queueUrl("https://sqs.us-east-1.amazonaws.com/123456789012/orders");
        builder.messageBody(body);
        client.sendMessage(builder.build());
    }
}
