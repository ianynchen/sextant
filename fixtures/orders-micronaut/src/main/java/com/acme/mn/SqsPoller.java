// A Micronaut module reaching SQS through the raw AWS SDK client, not a first-party
// annotation — `micronaut-jms-sqs` is a JMS `ConnectionFactory` over SQS (see
// `OrderMessaging`'s `@JMSListener`/`@JMSProducer` pair, which derives protocol `jms`,
// never `sqs`). `aws-sqs-sdk.yml` already reads this call framework-independently off
// `orders-service`; this fixture pins that it does so inside a Micronaut module too.
package com.acme.mn;

import jakarta.inject.Singleton;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

@Singleton
public class SqsPoller {
    private final SqsClient client;

    public SqsPoller(SqsClient client) {
        this.client = client;
    }

    // Real code, derives nothing: `receiveMessage` is outside `aws-sqs-sdk.yml`'s own
    // declared slice (G-43 — the whole inbound direction), so a poller that only
    // consumes looks like a module that does not touch SQS at all.
    public void poll() {
        client.receiveMessage(
                ReceiveMessageRequest.builder()
                        .queueUrl("https://sqs.eu-west-1.amazonaws.com/123456789012/mn-orders")
                        .build());
    }

    // The one call the catalog reads: a `SendMessageRequest.builder()` chain terminating
    // in `sendMessage`, the builder form — not the `Consumer<Builder>` lambda overload the
    // catalog's own slice note says derives nothing.
    public void audit(String body) {
        SendMessageRequest request =
                SendMessageRequest.builder()
                        .queueUrl("https://sqs.eu-west-1.amazonaws.com/123456789012/mn-audit")
                        .messageBody(body)
                        .build();
        client.sendMessage(request);
    }
}
