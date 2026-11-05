package com.acme.queues;

import java.util.ArrayDeque;
import java.util.Queue;

/** A plain {@link Queue}, not a blocking one: a local data structure, no hand-over. */
public class Scratch {

    public Job roundTrip(Job job) {
        Queue<Job> pending = new ArrayDeque<>();
        pending.offer(job);
        return pending.poll();
    }
}
