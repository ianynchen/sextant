package com.acme.queues;

import java.util.Objects;
import java.util.concurrent.BlockingQueue;

/**
 * A queue a container injects, kept through a null check: nothing in the module constructs an
 * {@code Injected}, so where the queue was made is not read, but its put and its take act on
 * the one object the check hands back.
 */
public class Injected {

    private final BlockingQueue<Job> queue;

    public Injected(BlockingQueue<Job> queue) {
        this.queue = Objects.requireNonNull(queue);
    }

    public void submit(Job job) throws InterruptedException {
        queue.put(job);
    }

    public Job poll() throws InterruptedException {
        return queue.take();
    }
}
