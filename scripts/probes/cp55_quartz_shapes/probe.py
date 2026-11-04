"""CP-55: the shapes Quartz 2.5.1 and Spring's `QuartzJobBean` (spring-context-support 7.0.1) take
in bytecode — every static factory of the six builder classes with its descriptor, every
`Scheduler.scheduleJob` / `scheduleJobs` / `rescheduleJob` overload, the default group of a job and
a trigger key, `QuartzJobBean.execute`'s call to `executeInternal`, what javac 21 emits for
`onDaysOfTheWeek(Calendar.TUESDAY, Calendar.THURSDAY)` and `atHourAndMinuteOnGivenDaysOfWeek(3, 0,
1, 2)`, the eight boxing methods, the call each `Scheduler` overload compiles to, and (g) what each
pairing call the Quartz catalog declares does to its arguments and when it refuses. Every cell is
read off the jars and the probe module's class files with `javap`, except the default group of a
key built without one, which `Main.java` takes from Quartz itself by running `JobKey` and
`TriggerKey`, and (g)'s outcomes, which it takes from a scheduler over Quartz's in-memory store,
created and never started. The version in each column is the jar's own manifest, and the JVM that loaded the
classes has to report the same one. Prints the observation table `cp55_quartz_shapes.md` carries."""

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _jvm_annotations import ProbeError, body, class_names, classes, identity, jar_at, javap

QUARTZ = ("org.quartz-scheduler", "quartz")
SPRING = ("org.springframework", "spring-context-support")
VERSIONS = {"quartz": "2.5.1", "spring": "7.0.1"}
ARTIFACTS = {"quartz": QUARTZ, "spring": SPRING}

BUILDERS = [
    "org.quartz.JobBuilder",
    "org.quartz.TriggerBuilder",
    "org.quartz.CronScheduleBuilder",
    "org.quartz.SimpleScheduleBuilder",
    "org.quartz.CalendarIntervalScheduleBuilder",
    "org.quartz.DailyTimeIntervalScheduleBuilder",
]
SCHEDULER = "org.quartz.Scheduler"
SCHEDULER_METHODS = ["scheduleJob", "scheduleJobs", "rescheduleJob"]
KEY = "org.quartz.utils.Key"
JOB_BEAN = "org.springframework.scheduling.quartz.QuartzJobBean"
FORMS = "probe.Forms"
CORE = "org.quartz.core.QuartzScheduler"
STD = "org.quartz.impl.StdScheduler"
BUILDER_OF_JOBS = "org.quartz.JobBuilder"
RAM_STORE = "org.quartz.simpl.RAMJobStore"
JDBC_STORE = "org.quartz.impl.jdbcjobstore.JobStoreSupport"
JDBC_DELEGATE = "org.quartz.impl.jdbcjobstore.StdJDBCDelegate"
LISTENER = "org.quartz.SchedulerListener"
# Read with `javap` only, never run: the version the user named when ruling on the job
# argument (2026-11-02). Its manifest must state it, as every jar here must.
OLD_QUARTZ = "2.3.2"
# (owner, method, parameters as javap prints them, question): what reaches the JOB argument
# of `scheduleJob(JobDetail, Trigger)` (h).
JOB_BODIES = [
    (
        CORE,
        "scheduleJob",
        "org.quartz.JobDetail, org.quartz.Trigger",
        (
            "`QuartzScheduler.scheduleJob(JobDetail, Trigger)`: its calls, strings, exceptions "
            "and throws (h)"
        ),
    ),
    (
        CORE,
        "notifySchedulerListenersJobAdded",
        "org.quartz.JobDetail",
        (
            "`QuartzScheduler.notifySchedulerListenersJobAdded(JobDetail)`, which "
            "`scheduleJob` hands the job to (h)"
        ),
    ),
    (RAM_STORE, "storeJob", None, "`RAMJobStore.storeJob(JobDetail, boolean)` (h)"),
    (
        JDBC_STORE,
        "storeJob",
        "java.sql.Connection, org.quartz.JobDetail, boolean",
        "`JobStoreSupport.storeJob(Connection, JobDetail, boolean)` (h)",
    ),
    (
        JDBC_DELEGATE,
        "insertJobDetail",
        "java.sql.Connection, org.quartz.JobDetail",
        (
            "`StdJDBCDelegate.insertJobDetail(Connection, JobDetail)`, what the JDBC store "
            "reads off the job (h)"
        ),
    ),
]
# (owner, method, parameters as javap prints them, question): the three pairing calls the
# catalog declares, as `StdScheduler` hands them on and `QuartzScheduler` runs them, and the
# store calls they end in.
PAIRING_BODIES = [
    (
        STD,
        "scheduleJob",
        "org.quartz.JobDetail, org.quartz.Trigger",
        "`StdScheduler.scheduleJob(JobDetail, Trigger)`, the `Scheduler` a `StdSchedulerFactory` builds, as compiled (g)",
    ),
    (
        STD,
        "scheduleJob",
        "org.quartz.JobDetail, java.util.Set<? extends org.quartz.Trigger>, boolean",
        "`StdScheduler.scheduleJob(JobDetail, Set, boolean)` as compiled (g)",
    ),
    (
        STD,
        "scheduleJobs",
        "java.util.Map<org.quartz.JobDetail, java.util.Set<? extends org.quartz.Trigger>>, boolean",
        "`StdScheduler.scheduleJobs(Map, boolean)` as compiled (g)",
    ),
    (
        CORE,
        "scheduleJob",
        "org.quartz.JobDetail, org.quartz.Trigger",
        "`QuartzScheduler.scheduleJob(JobDetail, Trigger)`: its calls, strings, exceptions and throws (g)",
    ),
    (
        CORE,
        "scheduleJob",
        "org.quartz.JobDetail, java.util.Set<? extends org.quartz.Trigger>, boolean",
        "`QuartzScheduler.scheduleJob(JobDetail, Set, boolean)`: its calls, strings, exceptions and throws (g)",
    ),
    (
        CORE,
        "scheduleJobs",
        "java.util.Map<org.quartz.JobDetail, java.util.Set<? extends org.quartz.Trigger>>, boolean",
        "`QuartzScheduler.scheduleJobs(Map, boolean)`: its calls, strings, exceptions and throws (g)",
    ),
    (
        BUILDER_OF_JOBS,
        "build",
        None,
        "`JobBuilder.build()`: the key of a job built with no `withIdentity` (g)",
    ),
    (
        RAM_STORE,
        "storeJobAndTrigger",
        None,
        "`RAMJobStore.storeJobAndTrigger(JobDetail, OperableTrigger)` (g)",
    ),
    (RAM_STORE, "storeJob", None, "`RAMJobStore.storeJob(JobDetail, boolean)` (g)"),
    (RAM_STORE, "storeTrigger", None, "`RAMJobStore.storeTrigger(OperableTrigger, boolean)` (g)"),
    (
        JDBC_STORE,
        "storeJobAndTrigger",
        None,
        "`JobStoreSupport.storeJobAndTrigger(JobDetail, OperableTrigger)` (the JDBC stores) (g)",
    ),
    (
        JDBC_STORE,
        "storeJob",
        "java.sql.Connection, org.quartz.JobDetail, boolean",
        "`JobStoreSupport.storeJob(Connection, JobDetail, boolean)` (g)",
    ),
    (
        JDBC_STORE,
        "storeTrigger",
        "java.sql.Connection, org.quartz.spi.OperableTrigger, org.quartz.JobDetail, boolean, java.lang.String, boolean, boolean",
        "`JobStoreSupport.storeTrigger(Connection, OperableTrigger, JobDetail, boolean, String, boolean, boolean)` (g)",
    ),
]
BOXES = ["Boolean", "Byte", "Character", "Short", "Integer", "Long", "Float", "Double"]


def listing(jar: Path, class_name: str) -> list[tuple[str, str, str]]:
    """(flags-and-header line, name, descriptor) of every method `javap -s -p` lists."""
    lines = javap(jar, "-s", "-p", class_name).splitlines()
    found = []
    for i, line in enumerate(lines):
        header = re.match(
            r"^  ((?:\w+ )*)[\w.<>\[\]?$, ]+? (\w+|static \{\})\(.*\)(?: throws .*)?;$", line
        )
        if header and i + 1 < len(lines) and "descriptor:" in lines[i + 1]:
            found.append(
                (line.strip(), header.group(2), lines[i + 1].split("descriptor:")[1].strip())
            )
    return found


def static_factories(jar: Path, class_name: str) -> list[str]:
    return [
        f"`{name}:{descriptor}`"
        for header, name, descriptor in listing(jar, class_name)
        if header.startswith("public static ")
    ]


def overloads(jar: Path, class_name: str, wanted: str) -> list[str]:
    return [
        f"`{name}:{descriptor}`"
        for _, name, descriptor in listing(jar, class_name)
        if name == wanted
    ]


def render(steps) -> str:
    """Instructions as `opcode operand // constant-pool entry`, one per line of the cell."""
    return "<br>".join(
        "`"
        + " ".join(part for part in (s.opcode, s.operand) if part)
        + (f" // {s.comment}" if s.comment else "")
        + "`"
        for s in steps
    )


def run_main(java_home: str, classes_dir: str, classpath_file: str) -> list[list[str]]:
    classpath = Path(classpath_file).read_text(encoding="utf-8").strip()
    result = subprocess.run(
        [f"{java_home}/bin/java", "-cp", f"{classes_dir}:{classpath}", "probe.Main"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ProbeError(f"probe.Main failed: {result.stderr.strip()}")
    return [line.split("\t") for line in result.stdout.splitlines() if line.strip()]


def main(argv: list[str]) -> int:
    arguments = dict(arg.split("=", 1) for arg in argv)
    jars = {}
    for key, (group, artifact) in ARTIFACTS.items():
        jar = jar_at(group, artifact, VERSIONS[key])
        if jar is None:
            raise ProbeError(f"NOT IN THE LOCAL REPOSITORY: {group}:{artifact}:{VERSIONS[key]}")
        stated, source = identity(jar, VERSIONS[key])
        jars[key] = (jar, stated, source)

    ran = run_main(arguments["JAVA_HOME"], arguments["CLASSES"], arguments["CLASSPATH"])
    reported = {r[1]: r[2] for r in ran if r[0] == "IDENTITY"}
    for key, (_, artifact) in ARTIFACTS.items():
        if reported.get(artifact) != jars[key][1]:
            raise ProbeError(
                f"the process reports {artifact} {reported.get(artifact)!r}, "
                f"the jar's manifest states {jars[key][1]!r}"
            )

    module = classes(Path(arguments["CLASSES"]), [FORMS])
    forms = module[FORMS]
    major = re.search(r"^\s+major version: (\d+)", forms.text, flags=re.MULTILINE)
    stated_major = major.group(1) if major else "NOT FOUND"
    if stated_major != "65":  # class file major version 65 is Java 21
        raise ProbeError(f"the probe module's class files are major version {stated_major}, not 65")

    quartz, spring = jars["quartz"], jars["spring"]
    print("| what the run read | " + " | ".join(jars[k][1] for k in ARTIFACTS) + " |")
    print("|---|---|---|")
    print(
        "| artifacts reporting this version | org.quartz-scheduler:quartz | org.springframework:spring-context-support |"
    )
    print(
        "| where the jar states that version | "
        + " | ".join(f"MANIFEST.MF `{jars[k][2]}`" for k in ARTIFACTS)
        + " |"
    )
    print(
        "| what the process that ran the library's code reported | `Package.getImplementationVersion` of "
        + " | `Package.getImplementationVersion` of ".join(
            f"`{c}`: {reported[a]}"
            for c, a in (
                ("org.quartz.JobKey", "quartz"),
                ("QuartzJobBean", "spring-context-support"),
            )
        )
        + " |"
    )
    print(
        f"| the probe module's compiler | javac 21: class file major version {stated_major} | (same module) |"
    )
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")

    row = 0

    def emit(question: str, key: str, observed: str) -> None:
        nonlocal row
        row += 1
        group, artifact = ARTIFACTS[key]
        print(f"| {row} | {question} | `{group}:{artifact}` | {jars[key][1]} | {observed} |")

    # (a) the static factories of the six builders
    for name in BUILDERS:
        factories = static_factories(quartz[0], name)
        if not factories:
            raise ProbeError(f"{name} has no public static method")
        emit(
            f"every public static factory of `{name}`, with its descriptor (a)",
            "quartz",
            "<br>".join(factories),
        )

    # (b) the Scheduler overloads
    for method in SCHEDULER_METHODS:
        found = overloads(quartz[0], SCHEDULER, method)
        if not found:
            raise ProbeError(f"Scheduler has no {method}")
        emit(
            f"every `Scheduler.{method}` overload, with its descriptor (b)",
            "quartz",
            "<br>".join(found),
        )

    # (c) the default group
    key_cls = classes(quartz[0], [KEY, "org.quartz.JobKey", "org.quartz.TriggerKey"])
    constant = re.search(
        r'public static final java\.lang\.String DEFAULT_GROUP = "([^"]*)";', key_cls[KEY].text
    )
    if constant is None:
        raise ProbeError("Key declares no DEFAULT_GROUP constant")
    own = [
        n
        for n in ("org.quartz.JobKey", "org.quartz.TriggerKey")
        if "DEFAULT_GROUP" in key_cls[n].text.split("{", 1)[1]
    ]
    emit(
        "the constant `DEFAULT_GROUP`, declared on `org.quartz.utils.Key`, the superclass of `JobKey` and `TriggerKey` (c)",
        "quartz",
        f'`Key.DEFAULT_GROUP` = `"{constant.group(1)}"`; declared again by: {", ".join(own) or "neither `JobKey` nor `TriggerKey`"}',
    )
    for owner, member in (("org.quartz.JobKey", "jobKey"), ("org.quartz.TriggerKey", "triggerKey")):
        emit(
            f"`{owner.rsplit('.', 1)[1]}.{member}(String)` as compiled: the group it passes to the constructor (c)",
            "quartz",
            render(body(key_cls[owner], member, "java.lang.String")),
        )
    emit(
        "`Key.<init>(String, String)` as compiled: what it does with a null group (c)",
        "quartz",
        render(body(key_cls[KEY], "Key", "java.lang.String, java.lang.String")),
    )
    for name, getter in (
        ("jobDefaultGroup", "JobKey.DEFAULT_GROUP"),
        ("triggerDefaultGroup", "TriggerKey.DEFAULT_GROUP"),
    ):
        emit(f"`{getter}` as javac compiles a read of it (c)", "quartz", render(body(forms, name)))
    for entry in ran:
        if entry[0] == "GROUP":
            emit(f"the group Quartz reports for `{entry[1]}` (c)", "quartz", f"`{entry[2]}`")

    # (d) QuartzJobBean.execute
    job_bean = classes(spring[0], [JOB_BEAN])[JOB_BEAN]
    steps = body(job_bean, "execute")
    if not any("executeInternal" in s.comment for s in steps):
        raise ProbeError("QuartzJobBean.execute never calls executeInternal")
    emit("`QuartzJobBean.execute(JobExecutionContext)` as compiled (d)", "spring", render(steps))

    # (e) the varargs of Integer
    for name, call in (
        ("dailyOnDays", "onDaysOfTheWeek(Calendar.TUESDAY, Calendar.THURSDAY)"),
        ("cronOnGivenDays", "atHourAndMinuteOnGivenDaysOfWeek(3, 0, 1, 2)"),
    ):
        emit(f"what javac 21 emits for `{call}` (e)", "quartz", render(body(forms, name)))

    # (f) the eight boxing methods
    seen = [
        s.comment.removeprefix("Method ")
        for s in body(forms, "boxed")
        if s.opcode == "invokestatic" and ".valueOf:" in s.comment
    ]
    if len(seen) != len(BOXES):
        raise ProbeError(f"expected {len(BOXES)} boxing calls, found {len(seen)}")
    emit(
        "the boxing calls javac 21 emits for one value of each primitive, in the order boxed (f)",
        "quartz",
        "<br>".join(f"`{s}`" for s in seen),
    )

    # (b, continued) how a call to each overload compiles
    calls = [
        f"`{s.opcode} {s.comment.removeprefix('InterfaceMethod ')}`"
        for s in body(forms, "schedule")
        if s.opcode.startswith("invoke") and "org/quartz/Scheduler." in s.comment
    ]
    emit(
        "the call javac 21 emits for each `Scheduler` method called from `Forms.schedule` (b)",
        "quartz",
        "<br>".join(calls),
    )

    # (g) what each declared pairing call does to its arguments, and every refusal it throws
    core = classes(quartz[0], [CORE, STD, BUILDER_OF_JOBS, RAM_STORE, JDBC_STORE])
    for owner, name, parameters, question in PAIRING_BODIES:
        steps = body(core[owner], name, parameters)
        if not steps:
            raise ProbeError(f"{owner} has no {name}({parameters})")
        emit(question, "quartz", effects(steps))
    emit(
        "every class in the jar that implements `org.quartz.spi.JobStore` directly or through a superclass in the jar (g)",
        "quartz",
        "<br>".join(f"`{n}`" for n in job_stores(quartz[0])),
    )
    for entry in ran:
        if entry[0] == "STORE":
            emit(
                "the job store of the probe's scheduler, as Quartz reports it (g)",
                "quartz",
                f"`{entry[1]}`",
            )
        elif entry[0] == "KEYS":
            emit(
                "the keys of two jobs built with no `withIdentity`, as Quartz compares them (g)",
                "quartz",
                entry[1],
            )
        elif entry[0] == "SCHEDULED":
            emit(
                f"on the probe's scheduler (in-memory store, never started): {entry[1]} (g)",
                "quartz",
                f"{entry[2]}; afterwards the trigger {entry[3]}",
            )

    # (h) what `scheduleJob(JobDetail, Trigger)` does to its JOB argument, in 2.5.1 and in
    # 2.3.2 (the version the user named, 2026-11-02): the calls the job reaches, the store
    # calls it is handed to, and the listeners Quartz hands it to.
    old = jar_at(*QUARTZ, OLD_QUARTZ)
    if old is None:
        raise ProbeError(f"NOT IN THE LOCAL REPOSITORY: {QUARTZ[0]}:{QUARTZ[1]}:{OLD_QUARTZ}")
    old_stated, _ = identity(old, OLD_QUARTZ)

    def emit_at(question: str, version: str, observed: str) -> None:
        nonlocal row
        row += 1
        print(f"| {row} | {question} | `{QUARTZ[0]}:{QUARTZ[1]}` | {version} | {observed} |")

    for jar, version in ((quartz[0], quartz[1]), (old, old_stated)):
        read = classes(jar, [CORE, RAM_STORE, JDBC_STORE, JDBC_DELEGATE])
        for owner, name, parameters, question in JOB_BODIES:
            if (
                version == quartz[1]
                and owner in (RAM_STORE, JDBC_STORE)
                or (version == quartz[1] and name == "scheduleJob")
            ):
                continue  # 2.5.1's are rows 27, 32 and 35 above
            steps = body(read[owner], name, parameters)
            if not steps:
                raise ProbeError(f"{owner} has no {name}({parameters}) in {version}")
            emit_at(question, version, effects(steps))
        listeners = implementers(jar, LISTENER)
        emit_at(
            "every class in the jar that implements `org.quartz.SchedulerListener` (h)",
            version,
            "<br>".join(f"`{n}`" for n in listeners),
        )
        bodies = classes(jar, listeners)
        for name in listeners:
            steps = body(bodies[name], "jobAdded", "org.quartz.JobDetail")
            emit_at(
                f"`{name.rsplit('.', 1)[-1]}.jobAdded(JobDetail)` as compiled (h)",
                version,
                render(steps) if steps else "declares no `jobAdded` of its own",
            )
    return 0


def effects(steps) -> str:
    """The calls a body makes, the strings it loads, the exceptions it builds and every
    `athrow`, in order: what it does to its arguments and when it refuses."""
    kept = [
        s
        for s in steps
        if s.opcode.startswith("invoke") or s.opcode in ("ldc", "ldc_w", "new", "athrow")
    ]
    return render(kept)


def job_stores(jar: Path) -> list[str]:
    """Every class in `jar` whose `javap` declaration implements `JobStore`, or extends one
    that does, to a fixed point."""
    return implementers(jar, "org.quartz.spi.JobStore", "-public")


def implementers(jar: Path, interface: str, *flags: str) -> list[str]:
    """Every class in `jar` whose `javap` declaration implements `interface`, or extends one
    that does, to a fixed point. `flags` narrows the listing (`-public`)."""
    names = [n for n in class_names(jar) if n.startswith("org.quartz.")]
    declarations = {
        m.group(1): m.group(0)
        for m in re.finditer(
            r"(?m)^(?:public |protected |private )?(?:abstract )?(?:final )?class ([\w.$]+)"
            r"[^\n]*\{$",
            javap(jar, *flags, *names),
        )
    }
    found = {
        n
        for n, d in declarations.items()
        if re.search(rf"implements [^{{]*{re.escape(interface)}(?![\w$])", d)
    }
    while True:
        more = {
            n
            for n, d in declarations.items()
            if n not in found
            and any(re.search(rf"extends {re.escape(f)}(?![\w$])", d) for f in found)
        }
        if not more:
            return sorted(found)
        found |= more


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
