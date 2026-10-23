"""CP-44: which registration points does Spring consult a condition at, which annotations count
at each, and what do `@ConditionalOnMissingBean` / `@ConditionalOnBean` check? Every cell is read
off the jars with `javap`; the version in each column is the jar's own manifest. Prints the
observation table `cp44_bean_registration_conditions.md` carries."""

import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _spring_jar import JAVAP, javap, manifest_version, newest_jar

CONDITION = "org.springframework.boot.autoconfigure.condition.OnBeanCondition"
SPEC = CONDITION + "$Spec"
MATCH = CONDITION + "$MatchResult"
EVALUATOR = "org.springframework.context.annotation.ConditionEvaluator"
PACKAGE = "org/springframework/context/annotation/"
PARSER = "org.springframework.context.annotation.ConfigurationClassParser"
READER = "org.springframework.context.annotation.ConfigurationClassBeanDefinitionReader"
SCANNER = "org.springframework.context.annotation.ClassPathScanningCandidateComponentProvider"
FACTORY = "org.springframework.beans.factory.support.DefaultListableBeanFactory"
LISTABLE = "org.springframework.beans.factory.ListableBeanFactory"
NAMER = "org.springframework.context.annotation.AnnotationBeanNameGenerator"
CLASS_UTILS = "org.springframework.util.ClassUtils"
STRING_UTILS = "org.springframework.util.StringUtils"
STEREOTYPES = {
    "context": [
        "org.springframework.stereotype.Component",
        "org.springframework.stereotype.Service",
        "org.springframework.stereotype.Repository",
        "org.springframework.stereotype.Controller",
        "org.springframework.context.annotation.Configuration",
    ],
    "web": [
        "org.springframework.web.bind.annotation.RestController",
        "org.springframework.web.bind.annotation.ControllerAdvice",
        "org.springframework.web.bind.annotation.RestControllerAdvice",
    ],
}


class Instruction(NamedTuple):
    offset: int
    op: str
    rest: str


_INSTRUCTION = re.compile(r"^\s+(\d+): (\w+)\s*(.*)$")
_METHOD_HEADER = re.compile(r"^  (?!static)(\S.*\))(?: throws [\w.,\s$]+)?;$")


def methods(listing: str) -> dict[str, list[Instruction]]:
    """`javap -c -p` output as header -> instructions."""
    found: dict[str, list[Instruction]] = {}
    current: list[Instruction] | None = None
    for line in listing.splitlines():
        header = _METHOD_HEADER.match(line)
        if header:
            current = found.setdefault(header.group(1), [])
            continue
        parsed = _INSTRUCTION.match(line)
        if parsed and current is not None:
            current.append(Instruction(int(parsed.group(1)), parsed.group(2), parsed.group(3)))
    return found


def method(table: dict[str, list[Instruction]], name: str) -> list[Instruction]:
    """The first method whose header names `name(`; empty when the jar has none."""
    pattern = re.compile(rf"(?:^|\s){re.escape(name)}\(")
    return next((body for header, body in table.items() if pattern.search(header)), [])


def calls(body: list[Instruction]) -> list[str]:
    """The simple names of the methods a body invokes, in order."""
    return [
        m.group(1)
        for ins in body
        if (m := re.search(r'Method (?:[\w/$]+\.)?"?([\w<>$]+)"?:', ins.rest))
    ]


def chain(body: list[Instruction], wanted: list[str]) -> str:
    """`wanted` in the order the body invokes them; a missing one is printed as MISSING so a
    stale reading is visible in the table rather than silently shorter."""
    seen = calls(body)
    return " -> ".join(w if w in seen else f"MISSING {w}" for w in wanted)


def fields_read(body: list[Instruction]) -> list[str]:
    return [m.group(1) for ins in body if (m := re.search(r"Field (\w+):", ins.rest))]


def annotations_of(jar: Path, name: str) -> list[str]:
    """The annotations a type carries ITSELF (the class-level `RuntimeVisibleAnnotations`)."""
    tail = javap(jar, name, "-v").split("SourceFile:", 1)[-1]
    return re.findall(r"^    ([\w.$]+)", tail, flags=re.MULTILINE)


def row_1(auto: Path, v_auto: str) -> str:
    spec = methods(javap(auto, SPEC, "-c", "-p"))
    constructor = method(spec, f"{SPEC}")
    deduce_at = next(i for i, ins in enumerate(constructor) if "Method deducedBeanType" in ins.rest)
    extract_at = next(i for i, ins in enumerate(constructor) if "Method extractTypes" in ins.rest)
    between = constructor[extract_at:deduce_at]
    tests = sum("Set.isEmpty" in ins.rest for ins in between)
    guarded = fields_read(between)
    deduced = method(spec, "deducedBeanType")
    method_only = any("instanceof" == ins.op and "MethodMetadata" in ins.rest for ins in deduced)
    bean_only = any("isAnnotated" in ins.rest for ins in deduced) and any(
        re.search(r"class [\w/]+/Bean$", ins.rest) for ins in deduced
    )
    otherwise = "Collections.emptySet" if "emptySet" in calls(deduced) else "MISSING emptySet"
    returns = chain(
        method(spec, "getReturnType"),
        ["getMethodReturnType", "resolve", "isParameterizedContainer", "getGeneric"],
    )
    validate = method(spec, "validate")
    refused = chain(validate, ["hasAtLeastOneElement"]) + (
        " -> new IllegalStateException"
        if any("IllegalStateException" in ins.rest for ins in validate)
        else " -> MISSING IllegalStateException"
    )
    return (
        f"| 1 | the type an unannotated `@ConditionalOnMissingBean` / `@ConditionalOnBean` checks "
        f"| `spring-boot-autoconfigure` | {v_auto} | `Spec.<init>` reaches `deducedBeanType` only "
        f"after {tests} `Set.isEmpty` tests, with fields `{'`, `'.join(guarded)}` read between "
        f"`extractTypes` and `deducedBeanType`; `deducedBeanType` tests "
        f"`instanceof MethodMetadata`"
        f"{', calls `isAnnotated` with `Bean`' if bean_only else ''}"
        f"{'' if method_only else ' (MISSING instanceof)'} and calls `{otherwise}`; "
        f"`getReturnType` runs `{returns}`; `validate` runs `{refused}` |"
    )


def row_2(auto: Path, v_auto: str) -> str:
    spec = methods(javap(auto, SPEC, "-c", "-p"))
    constructor = method(spec, f"{SPEC}")
    assigned: dict[str, list[str]] = {}
    pending: list[str] = []
    for ins in constructor:
        literal = re.search(r"// String (\w+)$", ins.rest)
        if literal:
            pending.append(literal.group(1))
        stored = re.search(r"putfield\b.*Field (\w+):", f"{ins.op} {ins.rest}")
        if stored:
            assigned[stored.group(1)] = pending
            pending = []
    types = [
        m.group(1)
        for ins in method(spec, "extractTypes")
        if (m := re.search(r"// String (\w+)$", ins.rest))
    ]
    condition = methods(javap(auto, CONDITION, "-c", "-p"))
    searched = {
        "getBeanDefinitionsForType": "types",
        "getBeanDefinitionsForAnnotation": "annotations",
        "containsBean": "names",
    }
    matching = calls(method(condition, "getMatchingBeans"))
    lookups = ", ".join(
        f"`{call}` for {role}" for call, role in searched.items() if call in matching
    )
    listing = methods(javap(auto, MATCH, "-c", "-p"))
    read = {
        verdict: ", ".join(f"`{f}`" for f in dict.fromkeys(fields_read(method(listing, verdict))))
        for verdict in ("isAllMatched", "isAnyMatched")
    }
    on_bean = chain(method(condition, "evaluateConditionalOnBean"), ["isAllMatched"])
    on_missing = chain(method(condition, "evaluateConditionalOnMissingBean"), ["isAnyMatched"])
    stores = "; ".join(
        f"`{'`, `'.join(assigned.get(field, ['MISSING']))}` -> field `{field}`"
        for field in ("names", "annotations", "ignoredTypes")
    )
    return (
        f"| 2 | how `value` / `type` / `name` select what is checked | `spring-boot-autoconfigure` "
        f"| {v_auto} | `extractTypes` reads the literals `{'`, `'.join(types)}`; "
        f"`Spec.<init>` stores {stores}; `getMatchingBeans` looks up {lookups}; "
        f"`@ConditionalOnBean` is decided by `{on_bean}` (reads {read['isAllMatched']}), "
        f"`@ConditionalOnMissingBean` by `{on_missing}` (reads {read['isAnyMatched']}) |"
    )


def row_3(auto: Path, context: Path, beans: Path, versions: dict[str, str]) -> str:
    condition = methods(javap(auto, CONDITION, "-c", "-p"))
    phase = next(
        (
            m.group(1)
            for ins in method(condition, "getConfigurationPhase")
            if (m := re.search(r"ConfigurationPhase\.(\w+):", ins.rest))
        ),
        "MISSING",
    )
    collect = method(condition, "collectBeanDefinitionsForType")
    lookup = next(i for i, ins in enumerate(collect) if "getBeanNamesForType" in ins.rest)
    literals = [collect[lookup - 2].op, collect[lookup - 1].op]
    flags = {"iconst_1": "true", "iconst_0": "false"}
    listable = javap(beans, LISTABLE, "-v")
    declared = re.search(
        r"getBeanNamesForType\(org\.springframework\.core\.ResolvableType, boolean, boolean\);.*?"
        r"MethodParameters:\s+Name\s+Flags\s+(\w+)\s+(\w+)\s+(\w+)",
        listable,
        flags=re.DOTALL,
    )
    names = declared.groups()[1:] if declared else ("MISSING", "MISSING")
    factory = methods(javap(beans, FACTORY, "-c", "-p"))
    collecting = method(factory, "doGetBeanNamesForType")
    iterates = sorted({f for f in fields_read(collecting) if f != "logger"})
    matches = "`isTypeMatch`" if "isTypeMatch" in calls(collecting) else "MISSING `isTypeMatch`"
    evaluator = methods(javap(context, EVALUATOR, "-c", "-p"))
    shoulds = [
        body for header, body in evaluator.items() if "shouldSkip(" in header and "Phase)" in header
    ]
    compared = (
        bool(shoulds)
        and chain(shoulds[0], ["getConfigurationPhase", "matches"])
        == "getConfigurationPhase -> matches"
    )
    reader = methods(javap(context, READER, "-c", "-p"))
    bean_method = method(reader, "loadBeanDefinitionsForBeanMethod")
    skip_at = next(ins.offset for ins in bean_method if "ConditionEvaluator.shouldSkip" in ins.rest)
    register_at = next(
        ins.offset
        for ins in bean_method
        if "BeanDefinitionRegistry.registerBeanDefinition" in ins.rest
    )
    parser_phase = _phases(javap(context, PARSER, "-c", "-p"), "processConfigurationClass")
    reader_phase = sorted(
        {
            p
            for h in ("loadBeanDefinitionsForBeanMethod",)
            for p in _phases(javap(context, READER, "-c", "-p"), h)
        }
        | set(
            _phases(javap(context, READER + "$TrackedConditionEvaluator", "-c", "-p"), "shouldSkip")
        )
    )
    return (
        f"| 3 | which definitions the search sees, and when | `spring-boot-autoconfigure`, "
        f"`spring-context`, `spring-beans` | {versions['auto']}, {versions['context']}, "
        f"{versions['beans']} | `OnBeanCondition.getConfigurationPhase` is `{phase}`; "
        f"`ConditionEvaluator.shouldSkip(metadata, phase)` "
        f"{'compares' if compared else 'MISSING comparison of'} the condition's own phase "
        f"with the phase it was handed before `Condition.matches`; the parser hands "
        f"`{'/'.join(parser_phase)}`, the bean-definition reader `{'/'.join(reader_phase)}`; "
        f"in `loadBeanDefinitionsForBeanMethod` `shouldSkip` (offset {skip_at}) comes BEFORE "
        f"`registerBeanDefinition` (offset {register_at}); the search is "
        f"`getBeanNamesForType(ResolvableType, {names[0]}={flags.get(literals[0], '?')}, "
        f"{names[1]}={flags.get(literals[1], '?')})`, which reads "
        f"fields `{'`, `'.join(iterates)}` and tests each name with {matches} |"
    )


def _phases(listing: str, name: str) -> list[str]:
    body = method(methods(listing), name)
    return sorted(
        {m.group(1) for ins in body if (m := re.search(r"ConfigurationPhase\.(\w+):", ins.rest))}
    )


def row_4(context: Path, v_context: str) -> str:
    with zipfile.ZipFile(context) as archive:
        names = sorted(
            n[: -len(".class")].replace("/", ".")
            for n in archive.namelist()
            if n.startswith(PACKAGE) and n.endswith(".class")
        )
    visibility = "public" if javap(context, EVALUATOR).startswith("public") else "package-private"
    listing = subprocess.run(
        [str(JAVAP), "-c", "-p", "-cp", str(context), *names],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    sites: list[str] = []
    wrapped: list[str] = []
    for block in listing.split("Compiled from")[1:]:
        found = re.search(r"(?:class|interface|enum) ([\w.$]+)", block)
        owner = found.group(1).rsplit(".", 1)[-1] if found else "?"
        for header, body in methods(block).items():
            where = f"{owner}#{header.split('(')[0].split()[-1]}"
            for at, ins in enumerate(body):
                target = re.search(r"Method ([\w/$]+)\.shouldSkip:(\([^)]*\))", ins.rest)
                if not target or owner == "ConditionEvaluator":
                    continue
                if target.group(1).endswith("TrackedConditionEvaluator"):
                    wrapped.append(where)
                    continue
                window = body[max(0, at - 12) : at]
                getter = next(
                    (
                        m.group(1)
                        for w in reversed(window)
                        if (m := re.search(r"Method (?:[\w/$]+/)?(\w+\.get\w*Metadata):", w.rest))
                    ),
                    "?",
                )
                phase = next(
                    (
                        m.group(1)
                        for w in reversed(window)
                        if (m := re.search(r"ConfigurationPhase\.(\w+):", w.rest))
                    ),
                    None,
                )
                sites.append(
                    f"`{where}` hands `{getter}` with "
                    f"{phase or 'no phase, so the evaluator picks one'}"
                )
    reader = methods(javap(context, READER, "-c", "-p"))
    per_class = method(reader, "loadBeanDefinitionsForConfigurationClass")
    asked = next(
        (
            i
            for i, ins in enumerate(per_class)
            if "TrackedConditionEvaluator.shouldSkip" in ins.rest
        ),
        0,
    )
    left = next((ins.offset for ins in per_class[asked:] if ins.op == "return"), -1)
    listed = next((ins.offset for ins in per_class if "getBeanMethods" in ins.rest), -1)
    tracked = methods(javap(context, READER + "$TrackedConditionEvaluator", "-c", "-p"))
    importers = chain(
        method(tracked, "shouldSkip"), ["isImported", "getImportedBy", "shouldSkip", "getMetadata"]
    )
    parser = methods(javap(context, PARSER, "-c", "-p"))
    reach = sorted(
        {
            header.split("(")[0].split()[-1]
            for header, body in parser.items()
            if "processConfigurationClass" in calls(body)
            and " processConfigurationClass(" not in header
        }
    )
    scanner = methods(javap(context, SCANNER, "-c", "-p"))
    scans = chain(method(scanner, "isCandidateComponent"), ["isConditionMatch"])
    return (
        f"| 4 | every `ConditionEvaluator.shouldSkip` call site, and what it is handed "
        f"| `spring-context` | {v_context} | `ConditionEvaluator` is {visibility} "
        f"(`javap` header), so only the {len(names)} classes of its own package can call it; "
        f"{len(sites)} call it directly: {'; '.join(sorted(sites))}; "
        f"`ConfigurationClassBeanDefinitionReader$TrackedConditionEvaluator` is called from "
        f"`{'`, `'.join(sorted(set(wrapped)))}`, which returns (offset {left}) after a skip "
        f"BEFORE it reads `getBeanMethods` (offset {listed}); the wrapper's own `shouldSkip` "
        f"runs `{importers}`; "
        f"`ConfigurationClassParser.processConfigurationClass` is reached from "
        f"`{'`, `'.join(reach)}`; the scanner's `isCandidateComponent` runs `{scans}` |"
    )


def row_5(context: Path, web: Path, versions: dict[str, str]) -> str:
    own = {
        name: annotations_of(context if name in STEREOTYPES["context"] else web, name)
        for name in [*STEREOTYPES["context"], *STEREOTYPES["web"]]
    }
    component = STEREOTYPES["context"][0]

    def reaches(name: str, seen: frozenset[str] = frozenset()) -> bool:
        if name == component:
            return True
        return any(
            reaches(parent, seen | {name})
            for parent in own.get(name, ())
            if parent not in seen and parent in own
        )

    defaults = method(methods(javap(context, SCANNER, "-c", "-p")), "registerDefaultFilters")
    component_filter = any("AnnotationTypeFilter" in i.rest for i in defaults) and any(
        i.rest.endswith("stereotype/Component") for i in defaults
    )
    verdicts = ", ".join(
        f"`@{name.rsplit('.', 1)[-1]}` {'yes' if reaches(name) else 'NO'}" for name in own
    )
    return (
        f"| 5 | which annotations make a class a scanned bean | `spring-context`, `spring-web` "
        f"| {versions['context']}, {versions['web']} | the scanner's `registerDefaultFilters` "
        f"builds an `AnnotationTypeFilter` for `Component`"
        f"{'' if component_filter else ' (MISSING)'}; reaches `@Component` directly or through "
        f"meta-annotations: {verdicts} |"
    )


def aliases(jar: Path, name: str) -> dict[str, tuple[str, str]]:
    """Each attribute of annotation `name` that carries `@AliasFor` naming ANOTHER annotation:
    attribute -> (that annotation, its attribute — the same name when `attribute` is unset)."""
    found: dict[str, tuple[str, str]] = {}
    blocks = re.split(
        r"^  public abstract \S+ (\w+)\(\);$", javap(jar, name, "-v"), flags=re.MULTILINE
    )
    for attribute, block in zip(blocks[1::2], blocks[2::2], strict=True):
        body = block.split("\n\n", 1)[0]
        target = re.search(r"AliasFor\(\s*annotation=class L([\w/$]+);", body)
        if target:
            named = re.search(r'attribute="(\w+)"', body)
            found[attribute] = (
                target.group(1).replace("/", "."),
                named.group(1) if named else attribute,
            )
    return found


def row_6(context: Path, web: Path, core: Path, versions: dict[str, str]) -> str:
    namer = methods(javap(context, NAMER, "-c", "-p"))
    generate = chain(
        method(namer, "generateBeanName"),
        ["determineBeanNameFromAnnotation", "hasText", "buildDefaultBeanName"],
    )
    default = next(
        (
            body
            for header, body in namer.items()
            if re.search(r"buildDefaultBeanName\([\w.]+BeanDefinition\)", header)
        ),
        [],
    )
    built = chain(default, ["getBeanClassName", "getShortName", "uncapitalizeAsProperty"])
    short = method(methods(javap(core, CLASS_UTILS, "-c", "-p")), "getShortName")
    pushed = [ins.rest for ins in short if ins.op == "bipush"]
    cut = "`$$`" if any("String $$" in ins.rest for ins in short) else "MISSING `$$`"
    replaced = (
        "replaces `$` with `.`"
        if pushed[-2:] == ["36", "46"] and "replace" in calls(short)
        else "MISSING replace"
    )
    last = "after the last `.`" if pushed[:1] == ["46"] else "MISSING lastIndexOf"
    uncap = methods(javap(core, STRING_UTILS, "-c", "-p"))
    uncapitalize = method(uncap, "uncapitalizeAsProperty")
    tested = [ins.rest for ins in uncapitalize if "charAt" in ins.rest or "isUpperCase" in ins.rest]
    both = sum("isUpperCase" in t for t in tested) == 2 and sum("charAt" in t for t in tested) == 2
    lowers = chain(uncapitalize, ["changeFirstCharacterCase"])
    component = STEREOTYPES["context"][0]

    def jar_of(name: str) -> Path:
        return context if name in STEREOTYPES["context"] else web

    def names_bean(name: str, attribute: str, seen: frozenset[tuple[str, str]]) -> bool:
        if (name, attribute) == (component, "value"):
            return True
        if (name, attribute) in seen or name not in (*STEREOTYPES["context"], *STEREOTYPES["web"]):
            return False
        target = aliases(jar_of(name), name).get(attribute)
        return target is not None and names_bean(*target, seen | {(name, attribute)})

    def naming(name: str) -> str:
        if name == component:
            return "value"
        found = [a for a in aliases(jar_of(name), name) if names_bean(name, a, frozenset())]
        return ", ".join(found) or "NONE"

    named = ", ".join(
        f"`@{n.rsplit('.', 1)[-1]}` {naming(n)}"
        for n in [*STEREOTYPES["context"], *STEREOTYPES["web"]]
    )
    return (
        f"| 6 | how a scanned class is named | `spring-context`, `spring-web`, `spring-core` "
        f"| {versions['context']}, {versions['web']}, {versions['core']} "
        f"| `AnnotationBeanNameGenerator.generateBeanName` runs `{generate}`; "
        f"`buildDefaultBeanName` runs `{built}`; `ClassUtils.getShortName` keeps the text "
        f"{last}, cut at {cut}, and {replaced}; `StringUtils.uncapitalizeAsProperty` returns "
        f"the name unchanged when "
        f"{'`charAt(0)` and `charAt(1)` are both `isUpperCase`' if both else 'MISSING test'}, "
        f"else runs `{lowers}`; the attribute aliased (`@AliasFor`, followed) to `@Component`'s "
        f"`value`: {named} |"
    )


def main() -> int:
    artifacts = {
        "context": newest_jar("org.springframework", "spring-context"),
        "beans": newest_jar("org.springframework", "spring-beans"),
        "web": newest_jar("org.springframework", "spring-web"),
        "core": newest_jar("org.springframework", "spring-core"),
        "auto": newest_jar("org.springframework.boot", "spring-boot-autoconfigure"),
    }
    if any(jar is None for jar in artifacts.values()):
        print(f"NOT IN THE LOCAL REPOSITORY: {[k for k, j in artifacts.items() if j is None]}")
        return 1
    jars: dict[str, Path] = {k: j for k, j in artifacts.items() if j is not None}
    versions = {key: manifest_version(jar) for key, jar in jars.items()}
    label = {
        "context": "spring-context",
        "beans": "spring-beans",
        "web": "spring-web",
        "core": "spring-core",
        "auto": "spring-boot-autoconfigure",
    }
    columns = list(dict.fromkeys(versions.values()))
    print(f"| what the run read | {' | '.join(columns)} |")
    print(f"|---|{'---|' * len(columns)}")
    print(
        "| artifact reporting this version | "
        + " | ".join(
            ", ".join(label[k] for k, v in versions.items() if v == col) for col in columns
        )
        + " |"
    )
    print(
        "| where the jar states that version | " + " | ".join("MANIFEST.MF" for _ in columns) + " |"
    )
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")
    print(row_1(jars["auto"], versions["auto"]))
    print(row_2(jars["auto"], versions["auto"]))
    print(row_3(jars["auto"], jars["context"], jars["beans"], versions))
    print(row_4(jars["context"], versions["context"]))
    print(row_5(jars["context"], jars["web"], versions))
    print(row_6(jars["context"], jars["web"], jars["core"], versions))
    return 0


if __name__ == "__main__":
    sys.exit(main())
