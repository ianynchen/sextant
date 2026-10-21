"""ARCHITECTURE §10's rules about what a file *says*.

The import contracts in `pyproject.toml` cover the rules about what a file
*imports*. These four cannot be expressed that way: a protocol name in a query
and a Kotlin flag in the resolver are both perfectly legal imports.

Every exception below is written down with its reason. A rule quietly loosened
until it passes is worse than no rule, because it still reads as enforcement.
"""

import ast
from collections.abc import Iterator

import yaml
from rules import SRC, offenders, python_files, sql_files, yaml_files

FRAMEWORKS = {
    "spring",
    "micronaut",
    "quarkus",
    "feign",
    "retrofit",
    "jackson",
    "hibernate",
    "dropwizard",
    "vertx",
    "ktor",
    "jersey",
    "resteasy",
    "django",
    "fastapi",
    "flask",
}
# Every member of `domain.closed_sets.Protocol`, spelled out rather than read off the
# enum: the rule below is about NAMES appearing in `storage/`, and a rule that imported
# the set it polices could never catch a member the enum gained and the rule forgot. What
# catches that instead is `test_the_protocol_set_policed_here_is_the_whole_set`, which
# compares the two — `pulsar` and `rsocket` had been missing since they were added, and
# were the only protocol names `storage/` was free to mention.
PROTOCOLS = {
    "http",
    "kafka",
    "jms",
    "grpc",
    "soap",
    "graphql",
    "amqp",
    "sqs",
    "pubsub",
    "websocket",
    "sse",
    "pulsar",
    "rsocket",
    "temporal",
    "eventbus",
}
LANGUAGES = {"java", "kotlin", "golang", "rust", "typescript", "javascript", "swift", "scala"}
JVM_NAMES = {"jvm", "java", "kotlin", "bytecode", "asm", "classfile", "classpath"}


def test_no_framework_is_named_anywhere_in_code():
    """The claim the whole design rests on: framework knowledge is catalog
    data, never code (D02). Catalogs are excluded because naming frameworks is
    exactly what they are for — the rule is about the engines that read them."""
    assert offenders(python_files() + sql_files(), FRAMEWORKS) == {}


def test_catalogs_use_one_fqn_notation():
    """2E-prep design §1c: every annotation fqn in every catalog is dotted
    (`org.springframework.web.bind.annotation.RequestBody`), never the SCIP
    symbol form the fact stream uses (`org/springframework/.../RequestBody#`).
    `_catalog_symbol` (`shapes/rooting.py`) is the one seam that converts
    between the two notations; a `#` surviving into a catalog value is that
    seam skipped, not applied. Values are read through `yaml.safe_load`,
    never a raw-text scan, because a YAML comment legitimately starts with
    `#` and must not trip this rule."""
    offending = []
    for path in yaml_files("catalogs"):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        for value in _string_values(document):
            if "#" in value:
                offending.append(f"{path.relative_to(SRC)}: {value}")

    assert offending == []


def test_storage_names_no_framework_language_or_protocol():
    """§10 storage ignorance. `storage/` knows SQL and D01. A protocol name
    reaching a query means a catalog's value has been baked into the engine,
    and the next protocol needs a code change instead of a YAML file."""
    files = python_files("storage") + sql_files("storage")
    assert offenders(files, FRAMEWORKS | PROTOCOLS | LANGUAGES) == {}


def test_the_protocol_set_policed_here_is_the_whole_set():
    """The rule above is only as wide as its list, and the list is hand-written — so a
    protocol added to `Protocol` and not added here is a name `storage/` may mention with
    nothing objecting. That is not hypothetical: `pulsar`, `rsocket`, `temporal` and
    `eventbus` were each added to the enum in their own wave, and the first two were still
    missing here two waves later. This compares the two sets, so the next member fails a
    test instead of quietly widening what `storage/` may say."""
    from sextant.domain.closed_sets import Protocol

    assert PROTOCOLS == {member.value for member in Protocol}


# The one statement whose rows carry a value nothing downstream will ever mask.
_METADATA_INSERT = "endpoint_metadata_insert"


def test_every_origin_writing_endpoint_metadata_holds_a_redactor():
    """`schema.sql`'s `value` column, `insert_endpoint_metadata.sql`'s header and
    `workspace.py`'s export map all state one invariant: a metadata value is masked AT THE
    ORIGIN, because nothing downstream masks one and the table is exported whole. Three
    passes write that table, and nothing tied the invariant to any of them — two of the
    three were writing values in the clear into a bundle, for waves, with every document
    saying they could not be.

    So the rule is stated where it can be checked: a module that reaches
    `endpoint_metadata_insert` builds a `Redactor`. It does not check that the redactor is
    USED on the right column, but it does mean a fourth origin cannot be written without
    meeting this, which is how the first two got in.

    **A STRONGER rule exists and this is not it**, which is worth stating plainly because
    an earlier draft of this docstring claimed no source rule could go further. One can:
    pin the `value` entry of the row dict itself — every dict literal in these modules
    carrying the row's key set must have its `value` expression mention `redact_value` or
    `REDACTED`. Measured 2026-09-22, that rule passes on all three origins as they stand
    and flags the pre-fix `request_requirements.py`, so it would have caught this bug by
    the column rather than by the import. It is not adopted here because it is keyed to
    an incidental code SHAPE — the three origins happen to build a dict literal in one
    place, and a row assembled incrementally or spread with `**` would satisfy it
    vacuously. That defeat is itself detectable (the module would match no row dict at
    all), so the stronger rule is a real option, deliberately declined rather than
    unavailable. The limitation is recorded here so the next reader weighs it instead of
    rediscovering it.

    Structural rather than textual: the docstrings of these modules name the statement
    while explaining the invariant, and a rule that fired on its own rationale would be
    deleted (`rules.py`'s own note)."""
    missing = []
    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        writes = any(
            isinstance(node, ast.Call)
            and any(
                isinstance(argument, ast.Constant) and argument.value == _METADATA_INSERT
                for argument in node.args
            )
            for node in ast.walk(tree)
        )
        if not writes:
            continue
        holds = any(
            isinstance(node, ast.Attribute) and node.attr == "from_rules" for node in ast.walk(tree)
        )
        if not holds:
            missing.append(str(path.relative_to(SRC)))

    assert missing == [], f"origins writing {_METADATA_INSERT} with no redactor: {missing}"


def test_jvm_names_stay_in_the_jvm_extractor():
    """§10 language confinement.

    Three exceptions, all deliberate. The composition root names concrete
    adapters — that is what a composition root is for, and hiding it would only
    move the coupling. `domain/facts.py` calls a field `classpath`, which is
    a JVM name for a language-neutral idea: the ordered set of places symbols
    were read from, with a tier each. Renaming it is a D00 schema change, so it
    is recorded here rather than waved through. And `ingress/detect/gradle.py`
    reads the SAME word off Gradle's own init-script JSON (2M design §1's
    pinned schema: `"classpath": [{"path","group?","name?","version?"}]`) —
    the wire key is Gradle's own name for the identical language-neutral idea,
    not a JVM implementation detail leaking out of the extractor, so it is
    recorded here for the same reason rather than smuggled past the check.

    `ingress/detect/maven.py` joins them on the same standard (W3b): it reads
    the property key `java.version` because that is what MAVEN calls the
    setting, and Spring Boot's parent pom sets that one and nothing else. It is
    a wire key, not a language branch — the detector's behaviour does not vary
    by language, and the file goes out of its way to say so ("this detector is
    keyed by build system, so it has no business naming one"). Dropping the key
    instead was measured and rejected: the commonest Boot module in the estate
    would then report no declared release at all, and multi-release selection
    would fall back to the class-file major — a worse answer than the pom
    actually states. Since 2026-10-21 it also carries `classpath`, for the
    reason Gradle's entry does: `dependency:build-classpath` is the name of
    MAVEN's goal, and the file it writes is the same language-neutral idea —
    the places symbols were read from — under the build tool's own word.

    `api.py` was the composition-root exception (2N Task 5, §5b): the
    reactor-walk/scan composition that used to live inline in `cli/app.py`'s
    own command bodies — the one place allowed to name
    `AsmScanner`/`JvmGeneratedNaming` directly — moved into `sextant.api`,
    which is now the ONLY place that does; `cli` itself dropped out of this
    exception (2N Task 6) once `cli/resources.py` — the last file under it
    that named JVM things — was retired in favor of `sextant.resources`
    (below). The exact filename, not a bare `"api"` prefix (fix round 1,
    MINOR-8): a prefix would silently exempt any future `api_*` module too,
    which is not this exception's claim. `resources.py` (top-level) is
    `sextant.resources`, the one real implementation now (2N Task 6 retired
    `cli/resources.py`'s delegating copy entirely); it carries the same
    `extractor-jvm` path segment/prose that made the file need an exception
    before, and after.
    """
    allowed = {"ingress/extract/jvm", "api.py", "resources.py"}
    files = [
        path
        for path in python_files() + sql_files()
        if not any(str(path.relative_to(SRC)).startswith(prefix) for prefix in allowed)
    ]

    # A MAPPING, not a file set plus a blanket name check: each recorded file
    # is pinned to the exact name it may carry, so a file allowed `classpath`
    # cannot start carrying `java` without this failing.
    known_leak = {
        "domain/facts.py": {"classpath"},
        "ingress/detect/gradle.py": {"classpath"},
        "ingress/detect/maven.py": {"java", "classpath"},
    }

    found = offenders(files, JVM_NAMES)
    assert {str(path): hits for path, hits in found.items()} == known_leak, found


def test_a_language_extension_namespace_is_read_only_by_its_own_adapter():
    """§10 extension namespace. `ext.<lang>` is the pressure valve that keeps
    D00's closed sets closed, and it only works while one adapter owns each
    namespace — a resolver reading `ext.kotlin` puts language knowledge back in
    the language-blind half. Nothing reads one yet; this guards the first."""
    namespaces = {f"ext_{language}" for language in LANGUAGES | {"jvm"}}
    files = [
        path
        for path in python_files()
        if not str(path.relative_to(SRC)).startswith("ingress/extract")
    ]

    assert offenders(files, namespaces) == {}


def test_ports_hold_only_contracts():
    """A port that grows behaviour stops being a seam. Protocols, frozen
    dataclasses and errors are contracts; so is a do-nothing implementation
    such as `NullProgress`, which exists precisely so a caller needs no
    special case. Anything with a real method body belongs in an adapter."""
    offending = []
    for path in python_files("application/ports"):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.ClassDef) and not _is_contract(node):
                offending.append(f"{path.relative_to(SRC)}::{node.name}")

    assert offending == []


def test_closed_sets_are_defined_only_where_the_schema_defines_them():
    """NFR-5. Widening a closed set is a schema change requiring
    re-extraction, so a second definition elsewhere is a set widened by
    accident — and the accident is invisible until two runs disagree."""
    defined = []
    for path in python_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef) and any(
                isinstance(base, ast.Name) and base.id in {"Enum", "StrEnum", "IntEnum"}
                for base in node.bases
            ):
                defined.append(str(path.relative_to(SRC)))

    assert set(defined) == {"domain/closed_sets.py"}


def test_application_reads_no_files():
    """Item 2's rule, encoded so it cannot come back. `application` orchestrates
    and derives; every I/O concern reaches it through a port. The catalog loader
    was the one exception, and it hid the fact that D02 §6's second catalog
    source could not be expressed at all."""
    io_calls = {
        "open",
        "read_text",
        "write_text",
        "read_bytes",
        "write_bytes",
        "glob",
        "rglob",
        "iterdir",
        "mkdir",
        "unlink",
    }
    io_modules = {"yaml", "subprocess", "shutil", "os"}

    found: dict[str, set[str]] = {}
    for path in python_files("application"):
        hits = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in io_calls:
                hits.add(node.attr)
            elif isinstance(node, ast.Name) and node.id in io_calls:
                hits.add(node.id)
            elif isinstance(node, ast.alias) and node.name.split(".")[0] in io_modules:
                hits.add(node.name)
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.split(".")[0] in io_modules
            ):
                hits.add(node.module)
        if hits:
            found[str(path.relative_to(SRC))] = hits

    assert found == {}


def _string_values(node: object) -> Iterator[str]:
    """Every string leaf in a parsed YAML document, walked recursively —
    the values a catalog author writes, as opposed to the comments beside
    them, which `yaml.safe_load` already discards."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _string_values(value)
    elif isinstance(node, list):
        for item in node:
            yield from _string_values(item)


def _is_contract(node: ast.ClassDef) -> bool:
    protocol = any(isinstance(base, ast.Name) and base.id == "Protocol" for base in node.bases)
    error = any(
        isinstance(base, ast.Name) and base.id.endswith(("Error", "Exception"))
        for base in node.bases
    )
    dataclass = any(
        isinstance(decorator, ast.Call) and getattr(decorator.func, "id", "") == "dataclass"
        for decorator in node.decorator_list
    )
    return protocol or error or dataclass or _does_nothing(node)


def _does_nothing(node: ast.ClassDef) -> bool:
    """Every method body is `...` or `pass` — a null object, not behaviour."""
    methods = [child for child in node.body if isinstance(child, ast.FunctionDef)]
    return bool(methods) and all(
        all(
            isinstance(statement, ast.Pass)
            or (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant))
            for statement in method.body
        )
        for method in methods
    )
