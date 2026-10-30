package com.acme.orders.quartz;

import static org.quartz.JobBuilder.newJob;
import static org.quartz.TriggerBuilder.newTrigger;

import org.quartz.CronScheduleBuilder;
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.Scheduler;
import org.quartz.SchedulerException;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;

/** Every builder held in a local and configured over statements of its own, each result
 *  dropped (ruling 4, spec 2026-10-30): the trigger's key, its schedule and the schedule's
 *  misfire policy are each set on the builder the call returns, which is the builder it was
 *  called on. The entry is the one the chained form gives: `DEFAULT.x`, the cron as written. */
public class HeldTriggerScheduler {

    public void schedule(Scheduler scheduler) throws SchedulerException {
        JobBuilder jobs = newJob(SweepJob.class);
        jobs.withIdentity("held", "orders");
        JobDetail job = jobs.build();

        TriggerBuilder<Trigger> triggers = newTrigger();
        triggers.withIdentity("x");
        CronScheduleBuilder cron = CronScheduleBuilder.cronSchedule("0 0 * * * ?");
        cron.withMisfireHandlingInstructionDoNothing();
        triggers.withSchedule(cron);
        scheduler.scheduleJob(job, triggers.build());
    }
}
