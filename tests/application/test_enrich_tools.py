"""The enrichment tools and the jail (2K design §4, Task 5 brief).

Security-sensitive: a bug here is a bug in the wall the rest of the
enrichment loop is built behind, not a wrong document. Every test in the
first half is about something the jail must NEVER show — outside its
roots, `.sextantignore`'d, or Task 3's ruling that the overlay itself is
invisible — coming back as a plain refusal STRING, never an exception. The
second half is ordinary behaviour: line-ranged reads, glob find, grep with
a match cap, and the redaction-on-read pass that a config file's planted
credential (`fixtures/orders-service/src/main/resources/application.yml`)
proves end to end.
"""

from pathlib import Path

from sextant.application.enrich.tools import (
    CONFIG_BEARING_EXTENSIONS,
    MAX_GREP_MATCHES,
    MAX_RESULT_BYTES,
    ToolExecutor,
)
from sextant.domain.enrichment import ENRICHMENT_FILE
from sextant.domain.ignorefile import IgnoreRules
from sextant.domain.redaction import REDACTED, Redactor
from sextant.ingress.detect.sextant_config import read_redaction_rules

REPO = Path(__file__).parents[2]
FIXTURE = REPO / "fixtures" / "orders-service"


def _executor(
    roots: tuple[Path, ...], redactor: Redactor | None = None, ignore: IgnoreRules | None = None
) -> ToolExecutor:
    """A jail over `roots`. `ignore` defaults to rules loaded for
    `roots[0]` (the tmp_path-based security/behaviour tests never write a
    `.sextantignore` of their own, so this is the built-ins-only case) —
    correct whenever `roots[0]` is an ancestor of every other root, the
    class's own stated wiring assumption; a test exercising SIBLING roots
    passes an `ignore` loaded for their common parent explicitly."""
    return ToolExecutor(
        roots=roots,
        redactor=redactor or Redactor.from_rules(),
        ignore=ignore or IgnoreRules.load(roots[0]),
    )


def _fixture_executor() -> ToolExecutor:
    """The jail wired the way Task 6's loop is expected to wire it: the
    redactor built through the SAME path `cli/app.py`'s `_redactor_for`
    uses (built-ins widened by the fixture's own `.sextant.yml`), and
    `ignore` loaded for the fixture's own module root."""
    redactor = Redactor.from_rules(read_redaction_rules(FIXTURE))
    ignore = IgnoreRules.load(FIXTURE)
    return ToolExecutor(
        roots=(FIXTURE, FIXTURE / ".sextant" / "facts"),
        redactor=redactor,
        ignore=ignore,
    )


# --- The jail: containment, checked after resolution -----------------------


def test_traversal_outside_the_root_is_refused(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "safe.txt").write_text("hi\n")
    executor = _executor((root,))
    result = executor.execute("read_file", {"path": "../../etc/passwd"})
    assert result == "refused: outside the allowed roots"


def test_an_absolute_path_outside_every_root_is_refused(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("not yours\n")
    executor = _executor((root,))
    result = executor.execute("read_file", {"path": str(outside / "secret.txt")})
    assert result == "refused: outside the allowed roots"


def test_a_symlink_inside_a_root_pointing_outside_is_refused_after_resolution(tmp_path: Path):
    """Containment is checked POST-resolution (2K Task 5 brief): a symlink
    that LOOKS like it stays inside the root, until you follow it, must
    still be refused — checking containment before following the link
    would let this one through."""
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("not yours\n")
    (root / "escape").symlink_to(outside)
    executor = _executor((root,))
    result = executor.execute("read_file", {"path": "escape/secret.txt"})
    assert result == "refused: outside the allowed roots"


def test_a_path_genuinely_inside_the_root_is_accepted(tmp_path: Path):
    """The positive control for the three refusals above: the jail is not
    just a wall, it lets a real, contained path through."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "safe.txt").write_text("hi\n")
    executor = _executor((root,))
    assert executor.execute("read_file", {"path": "safe.txt"}) == "hi"


def test_a_path_that_does_not_exist_in_any_root_is_a_plain_miss_not_a_security_refusal(
    tmp_path: Path,
):
    root = tmp_path / "root"
    root.mkdir()
    executor = _executor((root,))
    result = executor.execute("read_file", {"path": "nope.txt"})
    assert result == "refused: nope.txt does not exist"


# --- Invisibility: .sextantignore (built-in AND repo), and the overlay -----


def test_a_builtin_ignored_file_is_invisible_everywhere_and_unreadable():
    """`.env` at the fixture root — `IgnoreRules`' built-in layer, no
    `.sextantignore` line needed (the fixture's own docstring pins the
    same fact for `IgnoreRules` directly; this proves the jail wires it
    through)."""
    executor = _fixture_executor()
    listing = executor.execute("list_dir", {"path": "."}).splitlines()
    assert ".env" not in listing
    assert executor.execute("find", {"pattern": ".env"}) == ""
    assert executor.execute("grep", {"pattern": "FAKE_SECRET"}) == ""
    assert (
        executor.execute("read_file", {"path": ".env"})
        == "refused: .env is excluded from the enrichment jail"
    )


def test_a_repo_ignore_pattern_file_is_invisible_everywhere_and_unreadable():
    """`application-secret.yml` — excluded by the fixture's OWN
    `.sextantignore` line, the repo layer rather than a built-in."""
    executor = _fixture_executor()
    listing = executor.execute("list_dir", {"path": "src/main/resources"}).splitlines()
    assert "application-secret.yml" not in listing
    # `find` is basename-only and searches every jailed root: it is not
    # asserted empty here because a COMPILED copy of the fixture may sit
    # under `target/classes` with the same base name (a `.sextantignore`
    # pattern is a PATH, not a basename — it only ever excluded the
    # source path below). What must never appear is that source path, and
    # `grep` scoped to the source directory it lives in — never asserted
    # over EVERY root, for the identical reason — must not see its content.
    found = executor.execute("find", {"pattern": "application-secret.yml"}).splitlines()
    assert "src/main/resources/application-secret.yml" not in found
    scoped = executor.execute(
        "grep", {"pattern": "should-never-resolve", "path": "src/main/resources"}
    )
    assert scoped == ""
    result = executor.execute("read_file", {"path": "src/main/resources/application-secret.yml"})
    assert result == (
        "refused: src/main/resources/application-secret.yml is excluded from the enrichment jail"
    )


def test_the_enrichment_overlay_is_excluded_as_a_jail_specific_rule_not_a_sextantignore_builtin():
    """2K Task 3's controller ruling, carried to Task 5 at dispatch: the
    overlay is excluded from the jail SEPARATELY from `.sextantignore` —
    the model must never read its own prior run's claims, or a later run
    grounds its answers in what it already said rather than in the
    module. Nothing in `fixtures/orders-service/.sextantignore` names
    `.sextant-enrichment.json`; this test is the live proof the exclusion
    holds anyway."""
    assert ENRICHMENT_FILE not in (FIXTURE / ".sextantignore").read_text(encoding="utf-8")
    executor = _fixture_executor()
    listing = executor.execute("list_dir", {"path": "."}).splitlines()
    assert ENRICHMENT_FILE not in listing
    assert executor.execute("find", {"pattern": ENRICHMENT_FILE}) == ""
    # A distinctive string from the overlay's own claim text (planted 2K
    # Task 3 fixture) — proves grep cannot see the FILE'S CONTENT either.
    assert executor.execute("grep", {"pattern": "Legacy billing edge"}) == ""
    result = executor.execute("read_file", {"path": ENRICHMENT_FILE})
    assert result == f"refused: {ENRICHMENT_FILE} is excluded from the enrichment jail"


# --- Refusals are tool-result strings, never exceptions ---------------------


def test_an_unknown_tool_name_is_a_refusal_string(tmp_path: Path):
    executor = _executor((tmp_path,))
    result = executor.execute("delete_file", {"path": "x"})
    assert result == "refused: unknown tool 'delete_file'"


def test_a_missing_required_argument_is_a_refusal_string(tmp_path: Path):
    executor = _executor((tmp_path,))
    result = executor.execute("read_file", {})
    assert result.startswith("refused:")
    assert "'path'" in result


def test_arguments_that_are_not_an_object_is_a_refusal_string(tmp_path: Path):
    executor = _executor((tmp_path,))
    result = executor.execute("read_file", ["not", "a", "dict"])  # type: ignore[arg-type]
    assert result == "refused: arguments must be a JSON object"


def test_an_invalid_grep_pattern_is_a_refusal_string(tmp_path: Path):
    executor = _executor((tmp_path,))
    result = executor.execute("grep", {"pattern": "["})
    assert result.startswith("refused:")


def test_read_file_end_before_start_is_a_refusal_string(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("one\ntwo\nthree\n")
    executor = _executor((root,))
    result = executor.execute("read_file", {"path": "a.txt", "start": 5, "end": 2})
    assert result.startswith("refused:")
    assert "'end'" in result


# --- Behaviour: read_file ranging + cap, find, grep -------------------------


def test_read_file_default_window_and_an_explicit_range(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    lines = [f"line-{i}" for i in range(1, 501)]
    (root / "big.txt").write_text("\n".join(lines) + "\n")
    executor = _executor((root,))
    default_window = executor.execute("read_file", {"path": "big.txt"})
    assert default_window.splitlines() == lines[:400]
    ranged = executor.execute("read_file", {"path": "big.txt", "start": 10, "end": 12})
    assert ranged.splitlines() == ["line-10", "line-11", "line-12"]


def test_read_file_result_is_capped_at_the_byte_limit(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    long_lines = ["x" * 200] * 1000
    (root / "huge.txt").write_text("\n".join(long_lines))
    executor = _executor((root,))
    result = executor.execute("read_file", {"path": "huge.txt", "start": 1, "end": 1000})
    assert len(result.encode("utf-8")) <= MAX_RESULT_BYTES
    assert result.endswith(f"[truncated: result exceeds the {MAX_RESULT_BYTES}-byte cap]")


def test_find_matches_by_glob_against_the_base_name_case_sensitively(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "Order.java").write_text("class Order {}\n")
    (root / "order.txt").write_text("notes\n")
    nested = root / "nested"
    nested.mkdir()
    (nested / "Receipt.java").write_text("class Receipt {}\n")
    executor = _executor((root,))
    result = executor.execute("find", {"pattern": "*.java"})
    assert result.splitlines() == ["Order.java", "nested/Receipt.java"]


def test_grep_searches_every_jailed_root_and_reports_path_line_and_text(tmp_path: Path):
    root_a = tmp_path / "a"
    root_a.mkdir()
    root_b = tmp_path / "b"
    root_b.mkdir()
    (root_a / "one.txt").write_text("alpha\nneedle here\n")
    (root_b / "two.txt").write_text("needle again\nbeta\n")
    executor = _executor((root_a, root_b), ignore=IgnoreRules.load(tmp_path))
    result = executor.execute("grep", {"pattern": "needle"})
    assert result.splitlines() == ["one.txt:2:needle here", "two.txt:1:needle again"]


def test_grep_scoped_to_a_path_only_searches_that_subtree(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "one.txt").write_text("needle\n")
    sub = root / "sub"
    sub.mkdir()
    (sub / "two.txt").write_text("needle\n")
    executor = _executor((root,))
    result = executor.execute("grep", {"pattern": "needle", "path": "sub"})
    assert result.splitlines() == ["sub/two.txt:1:needle"]


def test_grep_caps_the_number_of_matches(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    total = MAX_GREP_MATCHES + 50
    (root / "many.txt").write_text("\n".join(f"needle {i}" for i in range(total)))
    executor = _executor((root,))
    lines = executor.execute("grep", {"pattern": "needle"}).splitlines()
    assert len(lines) == MAX_GREP_MATCHES + 1
    assert lines[-1].startswith(f"... [truncated: {total} matches found")


# --- Redaction on read -------------------------------------------------------


def test_config_bearing_extensions_mirrors_the_non_schema_artifact_readers():
    """2K Task 5 brief: "config-bearing detection ... reuse that registry
    knowledge, state the rule." `tools.py` cannot IMPORT the registry
    (`application` sits below `ingress` in `.importlinter`'s layering), so
    this pins the mirror against the real readers instead — if
    `YamlConfigReader`/`PropertiesReader` ever stop being the
    `reads_schema_sources = False` readers, or a schema reader starts
    claiming one of these extensions, this test catches the drift."""
    from sextant.ingress.read.avsc import AvscReader
    from sextant.ingress.read.graphql_sdl import GraphqlSdlReader
    from sextant.ingress.read.properties import PropertiesReader
    from sextant.ingress.read.proto_source import ProtoSourceReader
    from sextant.ingress.read.wsdl_xsd import WsdlXsdReader
    from sextant.ingress.read.yaml_config import YamlConfigReader

    config_readers = [PropertiesReader(), YamlConfigReader()]
    schema_readers = [AvscReader(), GraphqlSdlReader(), ProtoSourceReader(), WsdlXsdReader()]
    assert all(reader.reads_schema_sources is False for reader in config_readers)
    assert all(reader.reads_schema_sources is True for reader in schema_readers)
    assert CONFIG_BEARING_EXTENSIONS == frozenset({"yml", "yaml", "properties"})
    for kind in CONFIG_BEARING_EXTENSIONS:
        assert any(reader.accepts(kind) for reader in config_readers)
        assert not any(reader.accepts(kind) for reader in schema_readers)


def test_reading_the_fixtures_config_file_masks_the_planted_credentials():
    """The live pin (2K Task 5 brief): `application.yml` plants a
    built-in-pattern secret (`db.password`) and a repo-added-pattern
    secret (`internal.dsn`, via the fixture's `.sextant.yml` `redact:`
    section) side by side. Both must come back `«redacted»` through
    `read_file` — the built-in alone is not enough to prove the repo
    addition is actually wired into the tool's redactor."""
    executor = _fixture_executor()
    content = executor.execute("read_file", {"path": "src/main/resources/application.yml"})
    assert "hunter2-fixture" not in content
    assert f"password: {REDACTED}" in content
    assert f"dsn: {REDACTED}" in content


def test_a_value_no_redaction_rule_names_stays_verbatim_when_read():
    """The negative half of the same pin: `soap.billing.uri` names no
    key any rule matches, so a redactor that over-reaches would show up
    here as a masked address in a document that still claims to describe
    where the service points."""
    executor = _fixture_executor()
    content = executor.execute("read_file", {"path": "src/main/resources/application.yml"})
    assert "http://billing.internal.example.com/ws" in content


def test_grep_cannot_recover_a_value_read_file_would_have_masked():
    """Redaction-on-read has to hold for BOTH content-exposing tools, or a
    model that fails to guess `read_file`'s masking just calls `grep`
    instead — the credential the read_file test proves is masked must
    also be absent from every grep match."""
    executor = _fixture_executor()
    assert executor.execute("grep", {"pattern": "hunter2-fixture"}) == ""


def test_a_non_config_file_is_not_key_masked_but_still_gets_url_userinfo_stripped(
    tmp_path: Path,
):
    """The split 2K design §4 draws: KEY-based masking is only for
    config-bearing formats, but `redact_text`'s userinfo stripping is
    "applied to ALL tool results" (Task 5 brief) regardless of format —
    so a `.java` source file keeps its own comment mentioning `password`
    verbatim, while a credential riding a URL's userinfo still comes
    out."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "Client.java").write_text(
        '// password: not-a-config-key, left alone\nString uri = "https://user:s3cret@host/path";\n'
    )
    executor = _executor((root,))
    content = executor.execute("read_file", {"path": "Client.java"})
    assert "password: not-a-config-key, left alone" in content
    assert "https://host/path" in content
    assert "s3cret" not in content


# --- The transcript -----------------------------------------------------


def test_every_call_and_result_is_appended_to_the_transcript(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("hello\n")
    executor = _executor((root,))
    executor.execute("read_file", {"path": "a.txt"})
    executor.execute("list_dir", {"path": "."})
    assert [call["name"] for call in executor.transcript] == ["read_file", "list_dir"]
    assert executor.transcript[0]["args"] == {"path": "a.txt"}
    assert executor.transcript[0]["result"] == "hello"
    assert executor.transcript[1]["result"] == "a.txt"


def test_definitions_returns_the_four_tools_each_with_a_json_schema(tmp_path: Path):
    executor = _executor((tmp_path,))
    definitions = executor.definitions()
    assert [tool.name for tool in definitions] == ["list_dir", "find", "grep", "read_file"]
    for tool in definitions:
        assert tool.schema["type"] == "object"
        assert "properties" in tool.schema
        assert "required" in tool.schema
