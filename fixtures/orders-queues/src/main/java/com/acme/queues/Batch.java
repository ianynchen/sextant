package com.acme.queues;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

/**
 * A queue local to one method, used between its put and its take ({@code isEmpty}): calls
 * made on a queue do not make it another queue.
 */
public class Batch {

    public List<Job> runAll(List<Job> jobs) throws InterruptedException {
        BlockingQueue<Job> pending = new ArrayBlockingQueue<>(jobs.size());
        for (Job job : jobs) {
            pending.put(job);
        }
        List<Job> done = new ArrayList<>();
        while (!pending.isEmpty()) {
            done.add(pending.take());
        }
        return done;
    }
}
