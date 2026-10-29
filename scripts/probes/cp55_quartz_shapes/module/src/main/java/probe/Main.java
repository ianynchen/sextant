package probe;

import org.quartz.JobKey;
import org.quartz.TriggerKey;
import org.springframework.scheduling.quartz.QuartzJobBean;

/** Prints the versions the running JVM reports for the two libraries, and the group Quartz gives a key built without one. */
public class Main {
	public static void main(String[] args) {
		System.out.println("IDENTITY\tquartz\t" + JobKey.class.getPackage().getImplementationVersion());
		System.out.println("IDENTITY\tspring-context-support\t" + QuartzJobBean.class.getPackage().getImplementationVersion());
		System.out.println("GROUP\tJobKey.jobKey(\"x\").getGroup()\t" + JobKey.jobKey("x").getGroup());
		System.out.println("GROUP\tnew TriggerKey(\"x\").getGroup()\t" + new TriggerKey("x").getGroup());
		System.out.println("GROUP\tTriggerKey.triggerKey(\"x\", null).getGroup()\t" + TriggerKey.triggerKey("x", null).getGroup());
	}
}
