// `SqsTemplate.receive*` with the queue named inside the options lambda (`sqs-template-receive`,
// spec §12): the receive twin of the `send(to -> to.queue(…))` shape `spring-sqs-template.yml`
// reads. Four forms, one queue, so the catalog's four rules are each exercised. MEASURED
// (`javap -p -s`, spring-cloud-aws-sqs 3.1.1 and 4.1.1): no overload takes the queue as a
// plain argument — every one takes `Consumer<SqsReceiveOptions>` at argument 0 — so there is
// no direct form to put on a second queue.
package com.acme.orders.messaging;

import com.acme.orders.contracts.OrderEvent;
import io.awspring.cloud.sqs.operations.SqsTemplate;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Service;

import java.util.Collection;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;

@Service
public class OrderPoller {
    private final SqsTemplate template;

    public OrderPoller(SqsTemplate template) {
        this.template = template;
    }

    public Optional<Message<OrderEvent>> pollOne() {
        return template.receive(opts -> opts.queue("orders-poll"), OrderEvent.class);
    }

    public Collection<Message<OrderEvent>> pollMany() {
        return template.receiveMany(opts -> opts.queue("orders-poll"), OrderEvent.class);
    }

    public CompletableFuture<Optional<Message<OrderEvent>>> pollOneAsync() {
        return template.receiveAsync(opts -> opts.queue("orders-poll"), OrderEvent.class);
    }

    public CompletableFuture<Collection<Message<OrderEvent>>> pollManyAsync() {
        return template.receiveManyAsync(opts -> opts.queue("orders-poll"), OrderEvent.class);
    }
}
