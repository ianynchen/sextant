package com.acme.queues;

import com.google.common.collect.Queues;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

/** A queue made by a library static factory ({@code examples/apollo}'s shape). */
public class Cleaner {

    private final BlockingQueue<Long> toClean = Queues.newLinkedBlockingQueue(100);

    public boolean schedule(long id) {
        return toClean.offer(id);
    }

    public Long nextToClean() throws InterruptedException {
        return toClean.poll(1, TimeUnit.SECONDS);
    }
}
