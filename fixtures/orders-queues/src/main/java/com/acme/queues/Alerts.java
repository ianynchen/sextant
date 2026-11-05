package com.acme.queues;

import java.util.concurrent.LinkedBlockingQueue;

/**
 * A queue held in a field typed by the CLASS ({@code dolphinscheduler-alert}'s shape): javac
 * writes {@code LinkedBlockingQueue} as every call's owner.
 */
public class Alerts {

    private final LinkedBlockingQueue<String> pending;

    public Alerts(int capacity) {
        this.pending = new LinkedBlockingQueue<>(capacity);
    }

    public void push(String alert) throws InterruptedException {
        pending.put(alert);
    }

    public String next() throws InterruptedException {
        return pending.take();
    }
}
