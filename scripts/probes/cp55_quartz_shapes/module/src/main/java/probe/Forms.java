package probe;

import java.util.Calendar;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.quartz.CalendarIntervalScheduleBuilder;
import org.quartz.CronScheduleBuilder;
import org.quartz.DailyTimeIntervalScheduleBuilder;
import org.quartz.DateBuilder.IntervalUnit;
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.JobExecutionContext;
import org.quartz.JobKey;
import org.quartz.Scheduler;
import org.quartz.SchedulerException;
import org.quartz.SimpleScheduleBuilder;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;
import org.quartz.TriggerKey;
import org.springframework.scheduling.quartz.QuartzJobBean;

/** Quartz call forms, compiled and read with javap; never run. */
public class Forms {

	/** A job class, so a `QuartzJobBean` subclass is in the module. */
	public static class SampleJob extends QuartzJobBean {
		@Override
		protected void executeInternal(JobExecutionContext context) {
		}
	}

	// (e) varargs of Integer, given int constants
	public DailyTimeIntervalScheduleBuilder dailyOnDays() {
		return DailyTimeIntervalScheduleBuilder.dailyTimeIntervalSchedule()
			.onDaysOfTheWeek(Calendar.TUESDAY, Calendar.THURSDAY);
	}

	public CronScheduleBuilder cronOnGivenDays() {
		return CronScheduleBuilder.atHourAndMinuteOnGivenDaysOfWeek(3, 0, 1, 2);
	}

	// (f) the eight boxing conversions
	public Object[] boxed(boolean z, byte b, char c, short s, int i, long j, float f, double d) {
		Boolean bz = z;
		Byte bb = b;
		Character bc = c;
		Short bs = s;
		Integer bi = i;
		Long bj = j;
		Float bf = f;
		Double bd = d;
		return new Object[] {bz, bb, bc, bs, bi, bj, bf, bd};
	}

	// the builders, one chain per schedule builder
	public JobDetail job() {
		return JobBuilder.newJob(SampleJob.class).withIdentity("job", "grp").build();
	}

	public Trigger cron() {
		return TriggerBuilder.newTrigger().withIdentity("cron", "grp")
			.withSchedule(CronScheduleBuilder.cronSchedule("0 0 * * * ?")).build();
	}

	public Trigger simple() {
		return TriggerBuilder.newTrigger().withIdentity("simple")
			.withSchedule(SimpleScheduleBuilder.repeatSecondlyForever(5)).build();
	}

	public Trigger calendarInterval() {
		return TriggerBuilder.newTrigger()
			.withSchedule(CalendarIntervalScheduleBuilder.calendarIntervalSchedule().withInterval(2, IntervalUnit.DAY))
			.build();
	}

	// every Scheduler.scheduleJob / scheduleJobs / rescheduleJob overload
	public void schedule(Scheduler scheduler, JobDetail job, Trigger trigger, Set<? extends Trigger> triggers,
			Map<JobDetail, Set<? extends Trigger>> map) throws SchedulerException {
		scheduler.scheduleJob(job, trigger);
		scheduler.scheduleJob(trigger);
		scheduler.scheduleJob(job, triggers, true);
		scheduler.scheduleJobs(map, true);
		scheduler.rescheduleJob(TriggerKey.triggerKey("t"), trigger);
		scheduler.unscheduleJob(TriggerKey.triggerKey("t", "g"));
		scheduler.unscheduleJobs(List.of(TriggerKey.triggerKey("t")));
		scheduler.triggerJob(JobKey.jobKey("j"));
		scheduler.addJob(job, true);
	}

	// the default group, as javac reads it off the key classes
	public String jobDefaultGroup() {
		return JobKey.DEFAULT_GROUP;
	}

	public String triggerDefaultGroup() {
		return TriggerKey.DEFAULT_GROUP;
	}
}
