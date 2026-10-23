"""CP-48: how does Spring's placeholder parser find where a `${…}` ends when another sits
inside it, and is a default that itself holds a placeholder resolved? Every cell is read off
the jar with `javap`; the version in each column is the jar's own manifest. Prints the
observation table `cp48_placeholder_nesting.md` carries."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _spring_jar import javap, manifest_version, newest_jar

UTIL = "org.springframework.util."
HELPER = UTIL + "PropertyPlaceholderHelper"
PARSER = UTIL + "PlaceholderParser"
SIMPLE = PARSER + "$SimplePlaceholderPart"
NESTED = PARSER + "$NestedPlaceholderPart"
ABSTRACT = PARSER + "$AbstractPart"
CONTEXT = PARSER + "$PartResolutionContext"

_HEADER = re.compile(r"^  \S.*(?:\)|\{\})(?: throws [\w.,\s$]+)?;$")


def bodies(listing: str) -> dict[str, str]:
    """`javap -c -p` output as method header -> its instruction listing."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in listing.splitlines():
        if _HEADER.match(line):
            current = found.setdefault(line.strip(), [])
        elif current is not None:
            current.append(line)
    return {header: "\n".join(lines) for header, lines in found.items()}


def body(listing: str, name: str) -> str:
    """The first method whose header names `name` (`static {}` for the initialiser); a
    `name` spelling an opening parenthesis is matched as written, to tell overloads apart."""
    if "(" in name:
        return next((text for header, text in bodies(listing).items() if name in header), "")
    pattern = re.compile(rf"(?:^|\s|\.){re.escape(name)}(?:\(|$|;)")
    return next((text for header, text in bodies(listing).items() if pattern.search(header)), "")


def strings(text: str) -> list[str]:
    """The string constants a listing loads, in order."""
    return re.findall(r"// String (\S+)\s*$", text, re.MULTILINE)


def invoked(text: str) -> list[str]:
    """The simple names of the methods a listing invokes, in order, once each."""
    names = re.findall(r"// (?:Interface)?Method (?:[\w/$]+\.)?(\"?<?[\w$]+>?\"?):", text)
    return list(dict.fromkeys(names))


def sequence(text: str) -> list[str]:
    """Every field read and method invoked, in instruction order, repeats kept — where WHICH
    field a call follows is the observation."""
    return re.findall(r"// (?:Field|(?:Interface)?Method) (?:[\w/$]+\.)?(\"?<?[\w$]+>?\"?):", text)


def fields(text: str) -> list[str]:
    """The fields a listing reads or writes, in order, once each."""
    return list(dict.fromkeys(re.findall(r"// Field (?:[\w/$]+\.)?(\w+):", text)))


def branch(text: str, after: str, until: str) -> str:
    """The instructions from the first line containing `after` up to the next containing
    `until`, exclusive."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if after in line)
    end = next(i for i in range(start + 1, len(lines)) if until in lines[i])
    return "\n".join(lines[start + 1 : end])


def main() -> int:
    core = newest_jar("org.springframework", "spring-core")
    if core is None:
        print("spring-core NOT IN THE LOCAL REPOSITORY")
        return 1
    version = manifest_version(core)
    print(f"| what the run read | {version} |")
    print("|---|---|")
    print("| artifact reporting this version | spring-core |")
    print("| where the jar states that version | MANIFEST.MF |")
    print()
    print("| # | question | artifact | version | observed |")
    print("|---|---|---|---|---|")

    def row(number: str, question: str, observed: str) -> None:
        print(f"| {number} | {question} | `spring-core` | {version} | {observed} |")

    helper = javap(core, HELPER, "-c", "-p")
    replace = body(helper, "replacePlaceholders(java.lang.String, org")
    delegated = re.findall(r"// Method ([\w/$]+)\.replacePlaceholders:", replace)
    row(
        "1",
        "which parser `PropertyPlaceholderHelper` resolves through",
        f"`replacePlaceholders` reads field `{'`, `'.join(fields(replace))}` and invokes "
        f"`{'`, `'.join(o.rsplit('/', 1)[-1] + '.replacePlaceholders' for o in delegated)}`",
    )

    parser = javap(core, PARSER, "-c", "-p", "-constants")
    pairs = strings(body(parser, "static {}"))
    constructor = body(parser, "PlaceholderParser")
    row(
        "2",
        "the opener a nested placeholder is counted by",
        f"the initialiser loads `{'`, `'.join(pairs)}` into `wellKnownSimplePrefixes`; the "
        f"constructor reads `{'`, `'.join(f for f in fields(constructor) if f in ('suffix', 'wellKnownSimplePrefixes', 'prefix', 'simplePrefix'))}` "
        f"and invokes `{'`, `'.join(n for n in invoked(constructor) if n in ('get', 'endsWith'))}`: "
        "`simplePrefix` is the closer's partner where the opener ends with it, else the opener",
    )

    end = body(parser, "nextValidEndPrefix")
    raised = re.search(r"iinc\s+4, 1\b", end) is not None
    lowered = re.search(r"iinc\s+4, -1\b", end) is not None
    tested = [f for f in fields(end) if f in ("suffix", "simplePrefix")]
    row(
        "3",
        "how a placeholder's end is found",
        f"`nextValidEndPrefix`, starting after `prefix`, tests `{'`, `'.join(tested)}` at each index by "
        f"`{'`, `'.join(n for n in invoked(end) if n == 'substringMatch')}`; a `simplePrefix` "
        f"raises a depth counter: {'yes' if raised else 'NO'}; a `suffix` at depth above zero "
        f"lowers it and is skipped: {'yes' if lowered else 'NO'}; a `suffix` at depth zero "
        f"is the end: {'yes' if re.search(r'ifle', end) else 'NO'}; none found returns "
        f"{'-1' if 'iconst_m1' in end else 'NOT -1'}",
    )

    parse = body(parser, "parse(java.lang.String, boolean")
    unclosed = branch(parse, "Method nextValidEndPrefix", "goto")
    row(
        "4",
        "what an opener with no end is",
        f"where `nextValidEndPrefix` answers -1, `parse` runs `{' -> '.join(invoked(unclosed))}`: "
        "the opener is text and the scan resumes after it",
    )

    row(
        "5",
        "how a placeholder's inside is read",
        f"`parse` runs `{' -> '.join(n for n in invoked(parse) if n in ('substring', 'parse', 'createSimplePlaceholderPart', 'addAll', 'createNestedPlaceholderPart'))}`: "
        "the inside is parsed again; one holding no placeholder is a simple part, one holding "
        "one is a nested part",
    )

    section = body(parser, "parseSection")
    nested_part = body(parser, "createNestedPlaceholderPart")
    row(
        "6",
        "where the default separator splits a placeholder",
        f"`parseSection` finds the `{'`, `'.join(f for f in fields(section) if f == 'separator')}` "
        f"by `{'`, `'.join(n for n in invoked(section) if n in ('contains', 'indexOf', 'substring'))}` "
        "(the key before the first, the default the rest); `createNestedPlaceholderPart` "
        f"splits only a text part (`instanceof TextPart`: "
        f"{'yes' if 'PlaceholderParser$TextPart' in branch(nested_part, 'checkcast', 'ifne') else 'NO'}), "
        f"the parts after it joining the default (`{'`, `'.join(n for n in invoked(nested_part) if n == 'subList')}`)",
    )

    nested = javap(core, NESTED, "-c", "-p")
    resolve = body(nested, "resolve")
    simple = javap(core, SIMPLE, "-c", "-p")
    simple_resolve = body(simple, "resolve")
    row(
        "7",
        "whether a default holding a placeholder is resolved",
        f"`NestedPlaceholderPart.resolve` runs `{' -> '.join(sequence(resolve))}`: the key's "
        "parts are resolved, the key looked up, and where it answers nothing the default's "
        "parts are resolved; "
        f"`SimplePlaceholderPart.resolve` runs `{' -> '.join(sequence(simple_resolve))}`, its "
        "`fallback` returned as written — it holds no placeholder by construction (row 5)",
    )

    abstract = body(javap(core, ABSTRACT, "-c", "-p"), "resolveRecursively")
    context = javap(core, CONTEXT, "-c", "-p", "-constants")
    flagged = body(context, "flagPlaceholderAsVisited")
    row(
        "8",
        "how a cycle is stopped",
        f"`AbstractPart.resolveRecursively` runs `{' -> '.join(invoked(abstract))}`; "
        f"`flagPlaceholderAsVisited` adds the key to `{'`, `'.join(fields(flagged))}` and, "
        f"where it is already there, throws "
        f"`{'`, `'.join(re.findall(r'// String (.+?)\s*$', flagged, re.MULTILINE))}`",
    )

    recursively = body(simple, "resolveRecursively(org")
    row(
        "9",
        "what a simple part looks up first",
        f"`SimplePlaceholderPart.resolveRecursively` reads `{'`, `'.join(fields(recursively))}` "
        f"and invokes `{' -> '.join(invoked(recursively))}`: the whole inside, separator and "
        "default included, is looked up as a key before the key alone",
    )

    escaped = body(parser, "isEscaped")
    row(
        "10",
        "where an escape character is honoured",
        f"`isEscaped` reads `{'`, `'.join(fields(escaped))}` and tests `{'`, `'.join(invoked(escaped))}` "
        f"of the preceding character; `parse` calls it before a placeholder: "
        f"{'yes' if 'isEscaped' in invoked(parse) else 'NO'}; `parseSection` before a "
        f"separator: {'yes' if 'isEscaped' in invoked(section) else 'NO'}",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
