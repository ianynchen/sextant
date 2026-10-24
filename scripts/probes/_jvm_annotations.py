"""Shared by CP-49..CP-52: a jar at an exact coordinate out of the local Maven repository, the
version the jar ITSELF states (never the directory name this harness found it under — CP-5's
failure), and `javap -v`'s annotation data (`RuntimeVisibleAnnotations`, `AnnotationDefault`)
and instruction listings parsed into values a probe can print."""

from __future__ import annotations

import re
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from _spring_jar import JAVAP, REPOSITORY


class ProbeError(RuntimeError):
    """A run that cannot label its own output. Fatal, never advisory."""


def jar_at(group: str, artifact: str, version: str) -> Path | None:
    path = REPOSITORY.joinpath(*group.split("."), artifact, version, f"{artifact}-{version}.jar")
    return path if path.is_file() else None


def pom_at(group: str, artifact: str, version: str) -> Path | None:
    path = REPOSITORY.joinpath(*group.split("."), artifact, version, f"{artifact}-{version}.pom")
    return path if path.is_file() else None


def identity(jar: Path, requested: str) -> tuple[str, str]:
    """(version, manifest key) the jar states: `Implementation-Version`, else the OSGi
    `Bundle-Version`. A jar that states a version other than the one it was resolved as aborts
    the run rather than filling a mislabelled column."""
    with zipfile.ZipFile(jar) as archive:
        text = archive.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    stated = {
        key.strip(): value.strip()
        for key, _, value in (line.partition(":") for line in text.splitlines())
        if value
    }
    for key in ("Implementation-Version", "Bundle-Version"):
        if key in stated:
            if stated[key] != requested:
                raise ProbeError(
                    f"{jar.name} states {key} {stated[key]!r} but was resolved as {requested!r}"
                )
            return stated[key], key
    raise ProbeError(f"{jar.name}'s manifest states no version")


def class_names(jar: Path) -> list[str]:
    with zipfile.ZipFile(jar) as archive:
        return sorted(
            name[: -len(".class")].replace("/", ".")
            for name in archive.namelist()
            if name.endswith(".class") and "module-info" not in name and "META-INF" not in name
        )


def javap(classpath: Path, *arguments: str) -> str:
    result = subprocess.run(
        [str(JAVAP), "-cp", str(classpath), *arguments], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise ProbeError(f"javap {' '.join(arguments[:3])}… failed: {result.stderr.strip()}")
    return result.stdout


# --- annotation values ------------------------------------------------------------------------


@dataclass(frozen=True)
class Enum:
    type: str
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class ClassValue:
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass
class Annotation:
    type: str
    elements: dict[str, object] = field(default_factory=dict)

    def __str__(self) -> str:
        if not self.elements:
            return f"@{self.type}"
        body = ", ".join(f"{key}={render(value)}" for key, value in self.elements.items())
        return f"@{self.type}({body})"


def render(value: object) -> str:
    if isinstance(value, str):
        return '"' + value + '"'
    if isinstance(value, list):
        return "{" + ", ".join(render(item) for item in value) + "}"
    return str(value)


def _descriptor(text: str) -> str:
    return text[1:-1].replace("/", ".") if text.startswith("L") and text.endswith(";") else text


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "'": "'", '"': '"', "\\": "\\"}


def _string(text: str, i: int) -> tuple[str, int]:
    out: list[str] = []
    i += 1
    while text[i] != '"':
        if text[i] == "\\":
            if text[i + 1] == "u":
                out.append(chr(int(text[i + 2 : i + 6], 16)))
                i += 6
                continue
            out.append(_ESCAPES.get(text[i + 1], text[i + 1]))
            i += 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out), i + 1


def _skip(text: str, i: int) -> int:
    while i < len(text) and text[i].isspace():
        i += 1
    return i


def _value(text: str, i: int) -> tuple[object, int]:
    i = _skip(text, i)
    if text[i] == '"':
        return _string(text, i)
    if text[i] == "[":
        items: list[object] = []
        i = _skip(text, i + 1)
        while text[i] != "]":
            item, i = _value(text, i)
            items.append(item)
            i = _skip(text, i)
            if text[i] == ",":
                i = _skip(text, i + 1)
        return items, i + 1
    if text[i] == "@":
        return _annotation(text, i + 1)
    if text.startswith("class ", i):
        token = re.compile(r"class (\S+?)(?=[,\])\s]|$)").match(text, i)
        assert token is not None
        return ClassValue(_descriptor(token.group(1))), token.end()
    token = re.compile(r"[^,\])\s]+").match(text, i)
    assert token is not None
    raw = token.group()
    enum = re.fullmatch(r"(L[\w/$]+;)\.(\w+)", raw)
    if enum:
        return Enum(_descriptor(enum.group(1)), enum.group(2)), token.end()
    return raw, token.end()


def _annotation(text: str, i: int) -> tuple[Annotation, int]:
    name = re.compile(r"[\w.$]+").match(text, i)
    assert name is not None
    annotation = Annotation(name.group())
    i = name.end()
    if i < len(text) and text[i] == "(":
        i += 1
        while True:
            i = _skip(text, i)
            if text[i] == ")":
                return annotation, i + 1
            key = re.compile(r"(\w+)=").match(text, i)
            assert key is not None
            value, i = _value(text, key.end())
            annotation.elements[key.group(1)] = value
    return annotation, i


def _entries(lines: list[str], indent: int) -> list[Annotation]:
    """The annotations of one `RuntimeVisibleAnnotations:` block whose entries (`N: #…`) sit
    at `indent` spaces; each entry's readable form is the text indented below it."""
    found: list[Annotation] = []
    block: list[str] = []
    for line in [*lines, ""]:
        if line.startswith(" " * (indent + 2)):
            block.append(line)
            continue
        if block:
            found.append(_annotation("\n".join(block).strip(), 0)[0])
        block = []
        if not re.match(rf"^ {{{indent}}}\d+: #", line):
            break
    return found


@dataclass
class Member:
    header: str
    name: str
    annotations: list[Annotation] = field(default_factory=list)
    default: object | None = None

    @property
    def returns(self) -> str:
        """The declared type of a method's result (or a field's type)."""
        match = re.search(rf"(\S+)\s+{re.escape(self.name)}\s*(?:\(|;|=)", self.header)
        return match.group(1) if match else ""


@dataclass
class ClassFile:
    name: str
    declaration: str
    annotations: list[Annotation]
    members: list[Member]
    bootstrap: dict[int, list[str]]
    text: str

    def annotation(self, type_name: str) -> Annotation | None:
        return next((a for a in self.annotations if a.type == type_name), None)

    def member(self, name: str) -> Member | None:
        return next((m for m in self.members if m.name == name), None)


def parse(listing: str) -> ClassFile:
    """A `javap -v` listing's annotation data, members and bootstrap-method arguments."""
    lines = listing.splitlines()
    # `javap -v` prints the declaration on the line before `minor version:`, and the class's
    # own name on its `this_class:` line.
    minor = next((i for i, line in enumerate(lines) if line.startswith("  minor version:")), 0)
    declaration = lines[minor - 1] if minor else ""
    this = next((line for line in lines if line.startswith("  this_class:")), "")
    name = this.split("// ", 1)[1].strip().replace("/", ".") if "// " in this else ""
    members: list[Member] = []
    annotations: list[Annotation] = []
    bootstrap: dict[int, list[str]] = {}
    in_body = False
    current: Member | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if line == "{":
            in_body = True
        elif line == "}":
            in_body = False
            current = None
        elif in_body and re.match(r"^  \S.*;$", line) and "descriptor" not in line:
            header = line.strip()
            member_name = re.search(r"([\w$<>\"]+)\s*(?:\(|;$| =)", header)
            current = Member(header, member_name.group(1) if member_name else header)
            members.append(current)
        elif in_body and current is not None and line == "    RuntimeVisibleAnnotations:":
            current.annotations = _entries(lines[i + 1 :], 6)
        elif in_body and current is not None and line == "    AnnotationDefault:":
            text: list[str] = []
            for rest in lines[i + 2 :]:
                if not rest.startswith("        "):
                    break
                text.append(rest)
            current.default = _value("\n".join(text), 0)[0]
        elif not in_body and line == "RuntimeVisibleAnnotations:":
            annotations = _entries(lines[i + 1 :], 2)
        elif not in_body and line == "BootstrapMethods:":
            j = i + 1
            index = -1
            while j < len(lines) and lines[j].startswith("  "):
                head = re.match(r"^  (\d+): ", lines[j])
                if head:
                    index = int(head.group(1))
                    bootstrap[index] = [lines[j].split(None, 2)[2]]
                elif lines[j].startswith("      ") and index >= 0:
                    bootstrap[index].append(lines[j].strip())
                j += 1
        i += 1
    return ClassFile(name, declaration, annotations, members, bootstrap, listing)


def classes(jar: Path, names: list[str] | None = None) -> dict[str, ClassFile]:
    """Every (or the named) class of a jar, parsed from one `javap -v -p -c -constants` run."""
    wanted = names if names is not None else class_names(jar)
    output = javap(jar, "-v", "-p", "-c", "-constants", *wanted)
    parts = re.split(r"(?m)^(?=Classfile )", output)
    parsed = [parse(part) for part in parts if part.startswith("Classfile ")]
    return {cls.name: cls for cls in parsed}


# --- instruction listings ---------------------------------------------------------------------


@dataclass(frozen=True)
class Instruction:
    offset: int
    opcode: str
    operand: str
    comment: str


def body(cls: ClassFile, member: str) -> list[Instruction]:
    """The instructions of the first method named `member` (`<clinit>` for `static {}`)."""
    lines = cls.text.splitlines()
    pattern = (
        re.compile(r"^  static \{\};$")
        if member == "<clinit>"
        else re.compile(rf"^  \S.*[\s.]{re.escape(member)}\(.*\)(?: throws [\w.,\s$]+)?;$")
    )
    start = next((i for i, line in enumerate(lines) if pattern.match(line)), None)
    if start is None:
        return []
    found: list[Instruction] = []
    for line in lines[start + 1 :]:
        if re.match(r"^  \S", line) or line == "}":
            break
        step = re.match(r"^\s+(\d+): (\w+)\s*([^/]*?)\s*(?://\s*(.*))?$", line)
        if step:
            found.append(
                Instruction(int(step.group(1)), step.group(2), step.group(3), step.group(4) or "")
            )
        elif found and re.match(r"^\s+(?:LineNumberTable|LocalVariableTable|StackMapTable)", line):
            break
    return found


_INVOKED = re.compile(r"(?:Interface)?Method (?:([\w/$]+)\.)?(\"?[<\w$>]+\"?):")


def targets(steps: list[Instruction]) -> list[tuple[str, str]]:
    """(owner FQN, or "" for the class's own method; method name) of every invocation."""
    found: list[tuple[str, str]] = []
    for step in steps:
        match = _INVOKED.match(step.comment)
        if step.opcode.startswith("invoke") and match:
            found.append(((match.group(1) or "").replace("/", "."), match.group(2)))
    return found


def called(steps: list[Instruction]) -> list[str]:
    """`Owner.name` of every method a body invokes, in order (simple owner name)."""
    return [
        f"{owner.rsplit('.', 1)[-1]}.{name}" if owner else name for owner, name in targets(steps)
    ]


def fields(steps: list[Instruction], opcode: str = "getstatic") -> list[str]:
    found: list[str] = []
    for step in steps:
        match = re.match(r"Field (?:[\w/$]+/)?([\w$]+\.)?(\w+):", step.comment)
        if step.opcode == opcode and match:
            found.append(f"{match.group(1) or ''}{match.group(2)}")
    return found


def strings(steps: list[Instruction]) -> list[str]:
    """The string constants a body loads, in order."""
    return [
        step.comment.split("String ", 1)[1]
        for step in steps
        if step.opcode.startswith("ldc") and step.comment.startswith("String ")
    ]


def recipes(cls: ClassFile, steps: list[Instruction]) -> list[str]:
    """The `makeConcatWithConstants` recipe of each string concatenation a body performs, in
    order, with each argument slot (`\\u0001`) shown as `<>`."""
    found: list[str] = []
    for step in steps:
        match = re.match(r"InvokeDynamic #(\d+):makeConcatWithConstants", step.comment)
        if step.opcode == "invokedynamic" and match:
            arguments = cls.bootstrap.get(int(match.group(1)), [])
            recipe = next(
                (a.split(" ", 1)[1] for a in arguments if re.match(r"#\d+ ", a)), "NOT FOUND"
            )
            found.append(recipe.replace("\\u0001", "<>").replace("\\'", "'"))
    return found


def lambda_targets(cls: ClassFile, steps: list[Instruction]) -> list[str]:
    """The implementation method handle of each `invokedynamic` lambda/method reference a body
    creates (`LambdaMetafactory`), as `Owner.name`."""
    found: list[str] = []
    for step in steps:
        match = re.match(r"InvokeDynamic #(\d+):(\w+)", step.comment)
        if (
            step.opcode != "invokedynamic"
            or not match
            or match.group(2) == "makeConcatWithConstants"
        ):
            continue
        for argument in cls.bootstrap.get(int(match.group(1)), []):
            handle = re.search(r"REF_\w+ ([\w/$]+)\.([\w$<>\"]+):", argument)
            if handle:
                found.append(f"{handle.group(1).rsplit('/', 1)[-1]}.{handle.group(2)}")
    return found


def dotnames(cls: ClassFile) -> dict[str, str]:
    """A `DotName` constants class's static initialiser: field -> the class or string each
    `putstatic` is built from (the `ldc` immediately before it)."""
    found: dict[str, str] = {}
    pending: str | None = None
    for step in body(cls, "<clinit>"):
        if step.opcode.startswith("ldc"):
            kind, _, value = step.comment.partition(" ")
            pending = value.replace("/", ".") if kind == "class" else value
        elif step.opcode == "putstatic" and pending is not None:
            name = re.match(r"Field (\w+):", step.comment)
            if name:
                found[name.group(1)] = pending
            pending = None
    return found


def pom_dependencies(pom: Path) -> list[str]:
    text = pom.read_text(encoding="utf-8")
    block = text.split("<dependencies>", 1)[1] if "<dependencies>" in text else ""
    return [
        f"{group}:{artifact}"
        for group, artifact in re.findall(
            r"<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>", block
        )
    ]
