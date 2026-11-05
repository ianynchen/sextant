"""CP-57: javap readings of the Akka 2.6.21 and Pekko 1.1.3 actor API. See run.sh."""

import re
import subprocess
import sys
import zipfile
from pathlib import Path

ARGS = dict(a.split("=", 1) for a in sys.argv[1:])
FIX, JAVA_HOME, TWO = Path(ARGS["FIX"]), ARGS["JAVA_HOME"], ARGS["TWO"]

# (short class name, {family: package prefix}, method names; "<init>" for constructors)
T = "actor.typed"
ROWS = [
    (
        "typed javadsl.BehaviorBuilder",
        T + ".javadsl.BehaviorBuilder",
        ["onMessage", "onMessageEquals", "build"],
    ),
    (
        "typed javadsl.ReceiveBuilder",
        T + ".javadsl.ReceiveBuilder",
        ["onMessage", "onMessageEquals", "build"],
    ),
    (
        "typed javadsl.Behaviors",
        T + ".javadsl.Behaviors",
        ["receive", "receiveMessage", "setup", "withTimers"],
    ),
    ("typed javadsl.AbstractBehavior", T + ".javadsl.AbstractBehavior", ["newReceiveBuilder"]),
    (
        "persistence CommandHandlerBuilderByState",
        "persistence.typed.javadsl.CommandHandlerBuilderByState",
        ["onCommand", "onAnyCommand", "onCommandEquals"],
    ),
    (
        "persistence CommandHandlerBuilder",
        "persistence.typed.javadsl.CommandHandlerBuilder",
        ["forAnyState", "forState", "forStateType", "build"],
    ),
    (
        "classic japi.pf.ReceiveBuilder",
        "japi.pf.ReceiveBuilder",
        ["create", "match", "matchEquals", "matchAny", "build"],
    ),
    ("classic AbstractActor", "actor.AbstractActor", ["receiveBuilder", "getSender", "getSelf"]),
    ("typed ActorRef", T + ".ActorRef", ["tell"]),
    ("classic ActorRef", "actor.ActorRef", ["tell", "forward"]),
    ("typed RecipientRef", T + ".RecipientRef", ["tell", "ask"]),
    ("typed javadsl.AskPattern", T + ".javadsl.AskPattern", ["ask"]),
    ("sharding EntityRef", "cluster.sharding.typed.javadsl.EntityRef", ["tell", "ask"]),
    (
        "typed javadsl.ActorContext",
        T + ".javadsl.ActorContext",
        ["ask", "messageAdapter", "pipeToSelf", "scheduleOnce"],
    ),
    (
        "typed javadsl.TimerScheduler",
        T + ".javadsl.TimerScheduler",
        [
            "startTimerWithFixedDelay",
            "startTimerAtFixedRate",
            "startSingleTimer",
            "startPeriodicTimer",
        ],
    ),
    ("typed Scheduler", T + ".Scheduler", ["scheduleOnce", "scheduleWithFixedDelay"]),
    ("classic Scheduler", "actor.Scheduler", ["scheduleOnce"]),
    ("typed receptionist.ServiceKey", T + ".receptionist.ServiceKey", ["create"]),
    ("sharding EntityTypeKey", "cluster.sharding.typed.javadsl.EntityTypeKey", ["create"]),
    ("sharding Entity", "cluster.sharding.typed.javadsl.Entity", ["of"]),
    (
        "sharding ClusterSharding",
        "cluster.sharding.typed.javadsl.ClusterSharding",
        ["init", "entityRefFor"],
    ),
    (
        "typed receptionist.Receptionist",
        T + ".receptionist.Receptionist",
        ["register", "subscribe", "find"],
    ),
    ("pubsub Mediator$Publish", "cluster.pubsub.DistributedPubSubMediator$Publish", ["<init>"]),
    ("pubsub Mediator$Subscribe", "cluster.pubsub.DistributedPubSubMediator$Subscribe", ["<init>"]),
    ("pubsub Mediator$Send", "cluster.pubsub.DistributedPubSubMediator$Send", ["<init>"]),
    ("pubsub Mediator$Put", "cluster.pubsub.DistributedPubSubMediator$Put", ["<init>"]),
    ("classic pattern.Patterns", "pattern.Patterns", ["ask", "pipe"]),
]
FAM = {"pekko": "org.apache.pekko.", "akka": "akka."}


def javap(fam, cls):
    cp = (FIX / f"orders-actors-{fam}/target/probe.cp").read_text().strip()
    classes = str(FIX / f"orders-actors-{fam}/target/classes")
    out = subprocess.run(
        [f"{JAVA_HOME}/bin/javap", "-c", "-p", "-s", "-cp", f"{classes}:{cp}", cls],
        capture_output=True,
        check=False,
        text=True,
    )
    return out.stdout if out.returncode == 0 else None


def methods(text):
    """name, descriptor, returns_this (True / False / None for no code) per method."""
    result, cur = [], None
    for line in text.splitlines():
        if re.match(r"^  \S.*\);$|^  \S.*\) throws .*;$|^  static \{\};$", line):
            m = re.search(r"(\S+)\(", line)
            cur = {
                "line": line.strip(),
                "name": m.group(1).split(".")[-1] if m else "",
                "desc": "",
                "code": [],
                "has_code": False,
            }
            result.append(cur)
        elif cur is not None and line.startswith("    descriptor:"):
            cur["desc"] = line.split(":", 1)[1].strip()
        elif cur is not None and line.startswith("    Code:"):
            cur["has_code"] = True
        elif cur is not None and re.match(r"^\s+\d+: ", line):
            cur["code"].append(line.split(":", 1)[1].split("//")[0].split()[0])
            cur.setdefault("full", []).append(line.split(":", 1)[1].strip())
    return result


def returns(m, ms=(), depth=0):
    if not m["has_code"]:
        return "abstract"
    ops, kinds = m["code"], set()
    for i, op in enumerate(ops):
        if op in ("areturn", "ireturn", "return", "lreturn", "dreturn", "freturn"):
            if op != "areturn":
                kinds.add("void/prim")
                continue
            j = i - 1
            if j >= 0 and ops[j] == "checkcast":
                j -= 1
            if j >= 0 and ops[j] == "aload_0":
                kinds.add("this")
                continue
            # `areturn` of a call on `this` to a method of the same class: that method decides
            full = m.get("full", [])[j] if j >= 0 else ""
            mm = re.search(r"invoke(?:special|virtual)\s+#\d+\s*// Method ([^:]+):(\(.*)", full)
            if mm and depth < 4 and j >= 1 and "/" not in mm.group(1):
                callee = [c for c in ms if c["name"] == mm.group(1) and c["desc"] == mm.group(2)]
                if callee and callee[0] is not m:
                    inner = returns(callee[0], ms, depth + 1)
                    kinds.add(
                        ("via same-class call: " + inner)
                        if inner != "this"
                        else "this (via same-class call)"
                    )
                    continue
            kinds.add("new/other")
    return "/".join(sorted(kinds)) or "none"


def simple(desc):
    return desc.replace("Lorg/apache/pekko/", "L~pekko/").replace("Lakka/", "L~akka/")


ARTIFACTS = (
    "actor",
    "actor-typed",
    "cluster-typed",
    "cluster-sharding-typed",
    "cluster-tools",
    "persistence-typed",
)


def reported_version(fam):
    """The `Implementation-Version` the family's own jars state in their MANIFEST.MF (GUIDELINES
    5.4). Read from every artifact the probe reads; aborts unless they all agree and none is
    missing. Never taken from the pom or from the jar's file name."""
    classpath = (FIX / f"orders-actors-{fam}/target/probe.cp").read_text().strip().split(":")
    seen = {}
    for artifact in ARTIFACTS:
        stem = f"{fam}-{artifact}_2.13-"
        jars = [c for c in classpath if Path(c).name.startswith(stem)]
        if len(jars) != 1:
            sys.exit(f"{fam}: expected one {stem}*.jar on the classpath, found {jars}")
        with zipfile.ZipFile(jars[0]) as jar:
            manifest = jar.read("META-INF/MANIFEST.MF").decode()
        found = re.search(r"^Implementation-Version: (\S+)", manifest, flags=re.MULTILINE)
        if not found:
            sys.exit(f"{jars[0]}: no Implementation-Version in its manifest")
        seen[artifact] = found.group(1)
    if len(set(seen.values())) != 1:
        sys.exit(f"{fam}: the jars report different versions: {seen}")
    return next(iter(seen.values()))


def measure(fam):
    """{(class, method, descriptor): verdict} for one family, descriptors package-normalised."""
    cells = {}
    for _label, rel, names in ROWS:
        cls = FAM[fam] + rel
        text = javap(fam, cls)
        short = rel
        if text is None:
            cells[(short, "*", "-")] = "NOT FOUND"
            continue
        ms = methods(text)
        for name in names:
            if name == "<init>":
                hits = [m for m in ms if m["name"].endswith(cls.split(".")[-1]) or m["name"] == cls]
            else:
                hits = [m for m in ms if m["name"] == name]
            if not hits:
                cells[(short, name, "-")] = "NOT FOUND"
            for m in hits:
                desc = re.sub(r"L~(pekko|akka)/", "L~/", simple(m["desc"]))
                cells[(short, name, desc)] = returns(m, ms)
    return cells


def main():
    versions = {fam: reported_version(fam) for fam in ("pekko", "akka")}
    cells = {fam: measure(fam) for fam in ("pekko", "akka")}
    keys = list(cells["pekko"])
    if keys != list(cells["akka"]):
        sys.exit(
            "the two families do not declare the same methods: "
            + str(set(keys) ^ set(cells["akka"]))
        )
    print(f"| owner.method descriptor | {versions['pekko']} | {versions['akka']} |")
    print("|---|---|---|")
    for key in keys:
        cls, name, desc = key
        print(f"| `{cls}.{name}` `{desc}` | {cells['pekko'][key]} | {cells['akka'][key]} |")


def lambdas():
    """What javac writes for the fixture's lambdas and sends (Pekko build; Akka's is identical but for names)."""
    for cls in ("Stock", "OrderRoutes", "Frontend", "Relay", "ClassicBroker", "OrderEntity"):
        text = javap("pekko", "com.acme.actors." + cls)
        print(f"\n### {cls}\n")
        for m in methods(text):
            if m["name"].startswith("lambda$") or m["name"] in (
                "summary",
                "onStart",
                "announce",
                "forward",
                "<init>",
                "create",
                "preStart",
                "behavior",
                "createReceive",
                "onPrice",
            ):
                body = [
                    i
                    for i in m.get("full", [])
                    if re.match(r"(invoke|new|getstatic|areturn|ldc|checkcast)", i)
                ]
                print(f"- `{m['name']}` `{m['desc']}`")
                for i in body:
                    print(f"    {i}")


main()
print("\n# fixture lambdas")
lambdas()
print("\n### TwoReturns (scratch, compiled by run.sh)\n")
cp = (FIX / "orders-actors-pekko/target/probe.cp").read_text().strip()
two = subprocess.run(
    [f"{JAVA_HOME}/bin/javap", "-c", "-p", "-s", "-cp", f"{TWO}:{cp}", "probe.TwoReturns"],
    capture_output=True,
    check=False,
    text=True,
).stdout
for m in methods(two):
    if m["name"].startswith("lambda$"):
        print(f"- `{m['name']}` `{m['desc']}`")
        for i in m.get("full", []):
            if re.match(r"(invoke|new|areturn|ifnull|ifnonnull|ifeq|ifne|goto)", i):
                print(f"    {i}")
