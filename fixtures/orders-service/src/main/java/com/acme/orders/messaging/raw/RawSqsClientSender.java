// The raw SQS half: `SqsClient#sendMessage` off a `SendMessageRequest` built
// with a literal queue URL — the raw-client sibling of `EventProducers`'
// `SqsTemplate` calls.
package com.acme.orders.messaging.raw;

import software.amazon.awssdk.services.sqs.SqsAsyncClient;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

public class RawSqsClientSender {
    private final SqsClient client;
    private final SqsAsyncClient asyncClient;

    public RawSqsClientSender(SqsClient client, SqsAsyncClient asyncClient) {
        this.client = client;
        this.asyncClient = asyncClient;
    }

    public void send(String body) {
        SendMessageRequest request =
                SendMessageRequest.builder()
                        .queueUrl("https://sqs.us-east-1.amazonaws.com/123456789012/raw-queue")
                        .messageBody(body)
                        .build();
        client.sendMessage(request);
    }

    // Spring Cloud AWS 3.x auto-configures `SqsAsyncClient` and backs `SqsTemplate` with
    // it, so this is the client a module actually receives — the SYNCHRONOUS one above is
    // the deliberate choice.
    public void sendAsync(String body) {
        SendMessageRequest request =
                SendMessageRequest.builder()
                        .queueUrl("https://sqs.us-east-1.amazonaws.com/123456789012/async-queue")
                        .messageBody(body)
                        .build();
        asyncClient.sendMessage(request);
    }
}
