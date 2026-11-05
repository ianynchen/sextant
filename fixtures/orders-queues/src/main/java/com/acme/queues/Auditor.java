package com.acme.queues;

import com.google.common.collect.Queues;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * Values taken in batches ({@code apollo-portal}'s audit shape): Guava's {@code Queues.drain},
 * handed the queue as an argument, and the queue's own {@code drainTo}.
 */
public class Auditor {

    private final BlockingQueue<Job> audits = Queues.newLinkedBlockingQueue(100);

    public boolean record(Job job) {
        return audits.offer(job);
    }

    public List<Job> flushBatch() throws InterruptedException {
        List<Job> batch = new ArrayList<>();
        Queues.drain(audits, batch, 10, 1, TimeUnit.SECONDS);
        return batch;
    }

    public List<Job> flushQuietly() {
        List<Job> batch = new ArrayList<>();
        Queues.drainUninterruptibly(audits, batch, 10, 1, TimeUnit.SECONDS);
        return batch;
    }

    public List<Job> flushSome() {
        List<Job> some = new ArrayList<>();
        audits.drainTo(some, 5);
        return some;
    }

    public List<Job> flushRest() {
        List<Job> rest = new ArrayList<>();
        audits.drainTo(rest);
        return rest;
    }
}
