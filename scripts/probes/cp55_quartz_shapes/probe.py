"""CP-55: the shapes Quartz 2.5.1 and Spring's `QuartzJobBean` (spring-context-support 7.0.1) take
in bytecode — every static factory of the six builder classes with its descriptor, every
`Scheduler.scheduleJob` / `scheduleJobs` / `rescheduleJob` overload, the default group of a job and
a trigger key, `QuartzJobBean.execute`'s call to `executeInternal`, what javac 21 emits for
`onDaysOfTheWeek(Calendar.TUESDAY, Calendar.THURSDAY)` and `atHourAndMinuteOnGivenDaysOfWeek(3, 0,
1, 2)`, the eight boxing methods, and the call each `Scheduler` overload compiles to. Every cell is
read off the jars and the probe module's class files with `javap`, except the default group of a
key built without one, which `Main.java` takes from Quartz itself by running `JobKey` and
`TriggerKey`. The version in each column is the jar's own manifest, and the JVM that loaded the
classes has to report the same one. Prints the observation table `cp55_quartz_shapes.md` carries."""

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _jvm_annotations import ProbeError, body, classes, identity, jar_at, javap

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
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
