package com.acme.orders.quartz;

import static org.quartz.JobBuilder.newJob;
import static org.quartz.TriggerBuilder.newTrigger;

import org.quartz.CronScheduleBuilder;
import org.quartz.CronTrigger;
import org.quartz.Job;
import org.quartz.JobDetail;
import org.quartz.Scheduler;
import org.quartz.SchedulerException;
import org.quartz.Trigger;
import org.quartz.TriggerKey;

/** The RuoYi shape: a jobs-table row becomes a job and a cron trigger at runtime. */
public class RowScheduler {

    public void createJob(Scheduler scheduler, OrderJobRow row) throws SchedulerException {
        JobDetail detail = newJob(jobClass(row)).withIdentity(row.getName(), row.getGroup()).build();
        CronScheduleBuilder builder = misfire(row, CronScheduleBuilder.cronSchedule(row.getCron()));
        Trigger trigger =
                newTrigger().withIdentity(row.getName(), row.getGroup()).withSchedule(builder).build();
        detail.getJobDataMap().put("row", row);
        scheduler.scheduleJob(detail, trigger);
    }

    public void updateJob(Scheduler scheduler, OrderJobRow row) throws SchedulerException {
        TriggerKey key = TriggerKey.triggerKey(row.getName(), row.getGroup());
        CronTrigger trigger = (CronTrigger) scheduler.getTrigger(key);
        Trigger updated =
                trigger.getTriggerBuilder()
                        .withSchedule(misfire(row, CronScheduleBuilder.cronSchedule(row.getCron())))
                        .build();
        scheduler.rescheduleJob(key, updated);
    }

    private Class<? extends Job> jobClass(OrderJobRow row) {
        return row.isConcurrent() ? ConcurrentRowJob.class : SerialRowJob.class;
    }

    private CronScheduleBuilder misfire(OrderJobRow row, CronScheduleBuilder builder) {
        return row.isConcurrent()
                ? builder.withMisfireHandlingInstructionDoNothing()
                : builder.withMisfireHandlingInstructionFireAndProceed();
    }
}
