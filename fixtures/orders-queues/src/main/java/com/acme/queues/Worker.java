package com.acme.queues;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

/** Takes from the queue its constructor is given, which another class puts on. */
public class Worker implements Runnable {

    private final BlockingQueue<Job> queue;

    Worker(BlockingQueue<Job> queue) {
        this.queue = queue;
    }

    @Override
    public void run() {
        try {
            handle(queue.take());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    public Job tryNext() throws InterruptedException {
        return queue.poll(1, TimeUnit.SECONDS);
    }

    private void handle(Job job) {
        System.out.println(job.id());
    }
}
