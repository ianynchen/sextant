package com.acme.orders.quartz;

import static org.quartz.CronScheduleBuilder.cronSchedule;
import static org.quartz.JobBuilder.newJob;
import static org.quartz.TriggerBuilder.newTrigger;

import org.quartz.Scheduler;
import org.quartz.SchedulerException;
import org.quartz.Trigger;

/** The ruoyi-vue-pro shape: the trigger is built by a private method and returned. */
public class TriggerFactory {

    public void register(Scheduler scheduler, OrderJobRow row) throws SchedulerException {
        scheduler.scheduleJob(newJob(AuditJob.class).build(), buildTrigger(row.getCron()));
    }

    private Trigger buildTrigger(String cron) {
        return newTrigger().withSchedule(cronSchedule(cron)).build();
    }
}
