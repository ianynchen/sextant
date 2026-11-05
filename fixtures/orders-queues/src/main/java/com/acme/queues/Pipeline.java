package com.acme.queues;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * Two queues of ONE type: {@code jobs}, handed to a {@link Worker} that takes from it, and
 * {@code audit}, taken from here. A value put on one is never taken from the other.
 */
public class Pipeline {

    private final BlockingQueue<Job> jobs = new LinkedBlockingQueue<>();
    private final BlockingQueue<Job> audit = new LinkedBlockingQueue<>();
    private final Worker worker;

    public Pipeline() {
        this.worker = new Worker(jobs);
    }

    public void submit(Job job) throws InterruptedException {
        jobs.put(job);
    }

    public boolean trySubmit(Job job) throws InterruptedException {
        return jobs.offer(job, 1, TimeUnit.SECONDS);
    }

    public void record(Job job) {
        audit.add(job);
    }

    public boolean tryRecord(Job job) {
        return audit.offer(job);
    }

    public Job nextAudit() throws InterruptedException {
        return audit.take();
    }

    public Job pollAudit() {
        return audit.poll();
    }

    public Worker worker() {
        return worker;
    }
}
