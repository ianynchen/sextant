package com.acme.orders.quartz;

import static org.quartz.CronScheduleBuilder.cronSchedule;
import static org.quartz.DailyTimeIntervalScheduleBuilder.dailyTimeIntervalSchedule;
import static org.quartz.JobBuilder.newJob;
import static org.quartz.SimpleScheduleBuilder.simpleSchedule;
import static org.quartz.TriggerBuilder.newTrigger;

import java.util.Calendar;
import org.quartz.JobDetail;
import org.quartz.Trigger;
import org.quartz.TimeOfDay;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QuartzConfig {

    @Bean
    JobDetail sweepDetail() {
        return newJob(SweepJob.class).withIdentity("sweep", "orders").storeDurably().build();
    }

    @Bean
    JobDetail auditDetail() {
        return newJob(AuditJob.class).withIdentity("audit", "orders").storeDurably().build();
    }

    @Bean
    Trigger sweepEvery30s() {
        return newTrigger()
                .forJob("sweep", "orders")
                .withIdentity("every30s", "orders")
                .withSchedule(simpleSchedule().withIntervalInSeconds(30).repeatForever())
                .build();
    }

    @Bean
    Trigger sweepNightly() {
        return newTrigger()
                .forJob("sweep", "orders")
                .withIdentity("nightly", "orders")
                .withSchedule(cronSchedule("0 0 2 * * ?"))
                .build();
    }

    @Bean
    Trigger auditTrigger(JobDetail auditDetail, @Value("${orders.sweep.cron}") String sweepCron) {
        return newTrigger().forJob(auditDetail).withSchedule(cronSchedule(sweepCron)).build();
    }

    @Bean
    Trigger officeHours() {
        return newTrigger()
                .forJob("sweep", "orders")
                .withSchedule(
                        dailyTimeIntervalSchedule()
                                .onDaysOfTheWeek(Calendar.TUESDAY, Calendar.THURSDAY)
                                .startingDailyAt(TimeOfDay.hourAndMinuteOfDay(9, 0))
                                .withIntervalInHours(1))
                .build();
    }
}
