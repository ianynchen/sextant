package com.acme.orders.quartz;

import org.quartz.Job;
import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;

/** The RuoYi shape: one `execute` that calls the abstract `run`, which each subclass fills. */
public abstract class BaseRowJob implements Job {
    @Override
    public void execute(JobExecutionContext context) throws JobExecutionException {
        run(context);
    }

    protected abstract void run(JobExecutionContext context);
}
