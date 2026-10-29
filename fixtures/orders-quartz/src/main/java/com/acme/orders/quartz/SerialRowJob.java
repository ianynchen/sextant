package com.acme.orders.quartz;

import org.quartz.DisallowConcurrentExecution;
import org.quartz.JobExecutionContext;

@DisallowConcurrentExecution
public class SerialRowJob extends BaseRowJob {
    @Override
    protected void run(JobExecutionContext context) {
        context.getJobDetail();
    }
}
