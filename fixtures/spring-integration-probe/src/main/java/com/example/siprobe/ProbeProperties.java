package com.example.siprobe;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** A `@ConfigurationProperties` holder — the "destination comes from a bound
 *  properties bean" arm of the probe (Q5). */
@ConfigurationProperties(prefix = "probe")
public class ProbeProperties {
    private String queue = "props.orders.queue";
    private String topic = "props.orders.topic";

    public String getQueue() {
        return this.queue;
    }

    public void setQueue(String queue) {
        this.queue = queue;
    }

    public String getTopic() {
        return this.topic;
    }

    public void setTopic(String topic) {
        this.topic = topic;
    }
}
