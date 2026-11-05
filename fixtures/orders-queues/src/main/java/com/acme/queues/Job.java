package com.acme.queues;

/** A unit of work handed from a producer to a consumer through a queue. */
public record Job(String id) {}
