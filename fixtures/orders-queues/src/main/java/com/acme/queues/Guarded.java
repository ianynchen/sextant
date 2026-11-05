package com.acme.queues;

import java.util.Objects;
import java.util.concurrent.BlockingQueue;

/** Keeps the queue it is given through a null check, the usual constructor shape. */
public class Guarded {

    private final BlockingQueue<Job> queue;

    public Guarded(BlockingQueue<Job> queue) {
        this.queue = Objects.requireNonNull(queue, "queue");
    }

    public Job next() throws InterruptedException {
        return queue.take();
    }
}
