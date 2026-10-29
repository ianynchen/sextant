package com.acme.orders.quartz;

import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;
import org.springframework.scheduling.quartz.QuartzJobBean;

/** The Spring bean form: the handler is `executeInternal`, not `execute`. */
public class SweepJob extends QuartzJobBean {
    @Override
    protected void executeInternal(JobExecutionContext context) throws JobExecutionException {
        context.getJobDetail();
    }
}
