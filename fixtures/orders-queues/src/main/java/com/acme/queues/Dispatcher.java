package com.acme.queues;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

/** Puts on the queue it hands to a {@link Guarded}, which keeps it through a null check. */
public class Dispatcher {

    private final BlockingQueue<Job> queue = new LinkedBlockingQueue<>();
    private final Guarded guarded = new Guarded(queue);

    public void send(Job job) throws InterruptedException {
        queue.put(job);
    }

    public Guarded guarded() {
        return guarded;
    }
}
