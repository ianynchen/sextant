package com.acme.orders.quartz;

import static org.quartz.CronScheduleBuilder.cronSchedule;
import static org.quartz.TriggerBuilder.newTrigger;

import org.quartz.Trigger;

/** The dolphinscheduler shape, half two: the trigger is built here, its cron a parameter. */
public class TriggerMaker {

    public Trigger make(String cron) {
        return newTrigger().withSchedule(cronSchedule(cron)).build();
    }
}
