package com.acme.orders.quartz;

import static org.quartz.JobBuilder.newJob;

import org.quartz.Job;
import org.quartz.JobDetail;

/** The dolphinscheduler shape, half one: the job is built here, its class a parameter. */
public class JobFactory {

    public JobDetail build(Class<? extends Job> type) {
        return newJob(type).build();
    }
}
