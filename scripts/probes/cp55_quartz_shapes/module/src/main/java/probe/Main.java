package probe;

import java.util.Map;
import java.util.Properties;
import java.util.Set;

import org.quartz.CronScheduleBuilder;
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.JobKey;
import org.quartz.Scheduler;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;
import org.quartz.TriggerKey;
import org.quartz.impl.StdSchedulerFactory;
import org.springframework.scheduling.quartz.QuartzJobBean;

/**
 * Prints the versions the running JVM reports for the two libraries, the group Quartz gives a key
 * built without one, and (g) what Quartz does when one trigger is scheduled twice: on a scheduler
 * over Quartz's own in-memory job store, CREATED BUT NEVER STARTED (no job fires), shut down at the
 * end.
 */
public class Main {
	public static void main(String[] args) throws Exception {
		System.out.println("IDENTITY\tquartz\t" + JobKey.class.getPackage().getImplementationVersion());
		System.out.println("IDENTITY\tspring-context-support\t" + QuartzJobBean.class.getPackage().getImplementationVersion());
		System.out.println("GROUP\tJobKey.jobKey(\"x\").getGroup()\t" + JobKey.jobKey("x").getGroup());
		System.out.println("GROUP\tnew TriggerKey(\"x\").getGroup()\t" + new TriggerKey("x").getGroup());
		System.out.println("GROUP\tTriggerKey.triggerKey(\"x\", null).getGroup()\t" + TriggerKey.triggerKey("x", null).getGroup());

		Properties props = new Properties();
		props.setProperty("org.quartz.scheduler.instanceName", "cp55");
		props.setProperty("org.quartz.threadPool.threadCount", "1");
		props.setProperty("org.quartz.jobStore.class", "org.quartz.simpl.RAMJobStore");
		Scheduler scheduler = new StdSchedulerFactory(props).getScheduler();
		try {
			System.out.println("STORE\t" + scheduler.getMetaData().getJobStoreClass().getName());
			System.out.println("KEYS\t" + (newJob("k1").getKey().equals(newJob("k2").getKey())
				? "two `newJob(X.class).build()` share one key" : "two `newJob(X.class).build()` have different keys"));

			// One trigger, two different jobs (the P4 shape).
			Trigger t = cron("t");
			report("`scheduleJob(newJob(B).build(), t)`, `t` built with no `forJob`",
				() -> scheduler.scheduleJob(newJob("b"), t), t);
			report("then `scheduleJob(newJob(C).build(), t)`, the same `t`",
				() -> scheduler.scheduleJob(newJob("c"), t), t);

			// One trigger, the same job twice.
			// Named, so the store's message names a stable key rather than a generated one.
			JobDetail same = JobBuilder.newJob(SampleJob.class).withIdentity("s").build();
			NAMES.put(same.getKey(), "s");
			Trigger u = cron("u");
			report("`scheduleJob(j, u)`", () -> scheduler.scheduleJob(same, u), u);
			report("then `scheduleJob(j, u)` again, the same job and trigger", () -> scheduler.scheduleJob(same, u), u);

			// A trigger that already names another job (`forJob`).
			Trigger v = TriggerBuilder.newTrigger().withIdentity("v").forJob("other")
				.withSchedule(CronScheduleBuilder.cronSchedule("0 0 * * * ?")).build();
			report("`scheduleJob(newJob(D).build(), v)`, `v` built `forJob(\"other\")`",
				() -> scheduler.scheduleJob(newJob("d"), v), v);

			// The collection forms: a trigger naming another job, then a trigger already stored.
			Trigger w = TriggerBuilder.newTrigger().withIdentity("w").forJob("other")
				.withSchedule(CronScheduleBuilder.cronSchedule("0 0 * * * ?")).build();
			JobDetail e = newJob("e");
			report("`scheduleJob(newJob(E).build(), Set.of(w), false)`, `w` built `forJob(\"other\")`",
				() -> scheduler.scheduleJob(e, Set.of(w), false), w);
			Trigger x = cron("x");
			report("`scheduleJobs(Map.of(newJob(F).build(), Set.of(x)), false)`",
				() -> scheduler.scheduleJobs(Map.of(newJob("f"), Set.of(x)), false), x);
			report("then `scheduleJobs(Map.of(newJob(G).build(), Set.of(x)), false)`, the same `x`",
				() -> scheduler.scheduleJobs(Map.of(newJob("g"), Set.of(x)), false), x);
			report("then `scheduleJobs(Map.of(newJob(H).build(), Set.of(x)), true)`, the same `x`, replace",
				() -> scheduler.scheduleJobs(Map.of(newJob("h"), Set.of(x)), true), x);
		} finally {
			scheduler.shutdown(false);
		}
	}

	interface Call {
		void run() throws Exception;
	}

	static JobDetail newJob(String name) {
		JobDetail job = JobBuilder.newJob(SampleJob.class).build();
		NAMES.put(job.getKey(), name);
		return job;
	}

	static Trigger cron(String name) {
		return TriggerBuilder.newTrigger().withIdentity(name)
			.withSchedule(CronScheduleBuilder.cronSchedule("0 0 * * * ?")).build();
	}

	/** One line: the call, then `returned` or the exception class and message, then the job the trigger names afterwards. */
	static void report(String call, Call c, Trigger trigger) {
		String outcome;
		try {
			c.run();
			outcome = "returned";
		} catch (Exception e) {
			outcome = "threw `" + e.getClass().getName() + "`: " + e.getMessage();
		}
		JobKey bound = trigger.getJobKey();
		System.out.println("SCHEDULED\t" + call + "\t" + outcome + "\t"
			+ (bound == null ? "names no job" : "names job `" + jobName(bound) + "`"));
	}

	static final Map<JobKey, String> NAMES = new java.util.HashMap<>();

	static String jobName(JobKey key) {
		return NAMES.getOrDefault(key, bound(key));
	}

	static String bound(JobKey key) {
		return key.getName().equals("other") ? "other" : "an unknown key";
	}

	public static class SampleJob implements org.quartz.Job {
		public void execute(org.quartz.JobExecutionContext context) {
		}
	}
}
