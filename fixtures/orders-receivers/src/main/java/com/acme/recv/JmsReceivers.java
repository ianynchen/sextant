package com.acme.recv;

import jakarta.jms.Message;
import org.springframework.jms.core.JmsTemplate;

public class JmsReceivers {
    private final JmsTemplate template;

    public JmsReceivers(JmsTemplate template) {
        this.template = template;
    }

    public Message pollRaw() {
        return template.receive("recv.jms.raw");
    }

    public Message pollSelected() {
        return template.receiveSelected("recv.jms.selected", "priority > 5");
    }

    public Object pollConverted() {
        return template.receiveAndConvert("recv.jms.converted");
    }

    public Object pollSelectedConverted() {
        return template.receiveSelectedAndConvert("recv.jms.selected.converted", "kind = 'order'");
    }

    /** The trap: arity 1 `receiveSelected` takes a SELECTOR and reads the default destination. */
    public Message pollDefaultSelected() {
        return template.receiveSelected("priority > 5");
    }
}
