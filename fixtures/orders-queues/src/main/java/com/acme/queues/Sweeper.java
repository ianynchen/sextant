package com.acme.queues;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * The module's own {@code drain} helper, named and shaped like Guava's but not Guava's: the
 * receive is the {@code drainTo} inside it, never the call to it.
 */
public class Sweeper {

    private final BlockingQueue<Job> swept = new LinkedBlockingQueue<>();

    public void add(Job job) throws InterruptedException {
        swept.put(job);
    }

    public List<Job> sweep() {
        List<Job> out = new ArrayList<>();
        drain(swept, out, 10, 1, TimeUnit.SECONDS);
        return out;
    }

    static int drain(
            BlockingQueue<Job> queue, Collection<Job> into, int max, long timeout, TimeUnit unit) {
        return queue.drainTo(into, max);
    }
}
