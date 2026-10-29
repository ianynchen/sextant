package com.acme.orders.quartz;

import org.quartz.JobExecutionContext;

public class ConcurrentRowJob extends BaseRowJob {
    @Override
    protected void run(JobExecutionContext context) {
        context.getJobDetail();
    }
}
