package com.acme.queues;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

/**
 * {@code remove()} takes the head ({@code dolphinscheduler-eventbus}'s shape);
 * {@code remove(Object)} only discards a value, which nothing then handles.
 */
public class Mailbox {

    private final BlockingQueue<Job> inbox = new LinkedBlockingQueue<>();

    public void deliver(Job job) throws InterruptedException {
        inbox.put(job);
    }

    public Job next() {
        return inbox.remove();
    }

    public boolean discard(Job job) {
        return inbox.remove(job);
    }
}
