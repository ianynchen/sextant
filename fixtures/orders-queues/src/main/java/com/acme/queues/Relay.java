package com.acme.queues;

import java.util.concurrent.BlockingQueue;

/**
 * A queue from OUTSIDE the module: nothing here constructs a {@code Relay}, so the queue its
 * constructor is given (by a container, say) is an object this module never makes.
 */
public class Relay {

    private final BlockingQueue<Job> inbox;

    public Relay(BlockingQueue<Job> inbox) {
        this.inbox = inbox;
    }

    public void forward(Job job) throws InterruptedException {
        inbox.put(job);
    }

    public Job receive() throws InterruptedException {
        return inbox.take();
    }
}
