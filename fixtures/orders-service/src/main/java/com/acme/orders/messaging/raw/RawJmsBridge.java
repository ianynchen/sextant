// The raw JMS half: no `JmsTemplate`, just `Session#createProducer` and
// `Session#createConsumer` off a `Session#createQueue` destination — the raw
// driver shape the templated `EventProducers`/`AuditJmsListener` pair doesn't
// exercise.
package com.acme.orders.messaging.raw;

import jakarta.jms.JMSException;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;

public class RawJmsBridge {
    private final Session session;

    public RawJmsBridge(Session session) {
        this.session = session;
    }

    public MessageProducer createAuditProducer() throws JMSException {
        return session.createProducer(session.createQueue("raw-audit"));
    }

    public MessageConsumer createIntakeConsumer() throws JMSException {
        return session.createConsumer(session.createQueue("raw-intake"));
    }
}
