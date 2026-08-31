// The raw SQS half: `SqsClient#sendMessage` off a `SendMessageRequest` built
// with a literal queue URL — the raw-client sibling of `EventProducers`'
// `SqsTemplate` calls.
package com.acme.orders.messaging.raw;

import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

public class RawSqsClientSender {
    private final SqsClient client;

    public RawSqsClientSender(SqsClient client) {
        this.client = client;
    }

    public void send(String body) {
        SendMessageRequest request =
                SendMessageRequest.builder()
                        .queueUrl("https://sqs.us-east-1.amazonaws.com/123456789012/raw-queue")
                        .messageBody(body)
                        .build();
        client.sendMessage(request);
    }
}
