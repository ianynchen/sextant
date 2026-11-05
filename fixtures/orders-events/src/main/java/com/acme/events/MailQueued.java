package com.acme.events;

/** An event built with chained setters, each returning the event itself (Lombok's
 * `@Accessors(chain = true)`, the shape ruoyi-vue-pro builds every event in): the value
 * published is the last setter's result, whose declared return type is the event's class. */
public class MailQueued {
    private String to;
    private String subject;

    public MailQueued setTo(String to) {
        this.to = to;
        return this;
    }

    public MailQueued setSubject(String subject) {
        this.subject = subject;
        return this;
    }

    public String to() {
        return to;
    }
}
