package com.acme.queues;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

/**
 * A queue nothing in the module takes from: values are put on it and only ever discarded by
 * {@code removeIf}, which hands them to no code that handles them.
 */
public class Outbox {

    private final BlockingQueue<Job> pending = new LinkedBlockingQueue<>();

    public void send(Job job) throws InterruptedException {
        pending.put(job);
    }

    public void purge(String id) {
        pending.removeIf(job -> job.id().equals(id));
    }
}
