package com.acme.orders.quartz;

import java.util.Set;
import org.quartz.Job;
import org.quartz.Scheduler;
import org.quartz.SchedulerException;

/** The dolphinscheduler shape: job and trigger are built elsewhere and paired here. */
public class SetScheduler {
    private final JobFactory jobs = new JobFactory();
    private final TriggerMaker triggers = new TriggerMaker();

    public void schedule(Scheduler scheduler, Class<? extends Job> type, String cron)
            throws SchedulerException {
        scheduler.scheduleJob(jobs.build(type), Set.of(triggers.make(cron)), true);
    }
}
