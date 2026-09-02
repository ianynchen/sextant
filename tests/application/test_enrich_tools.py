"""The enrichment tools and the jail (2K design §4, Task 5 brief + fix
rounds 1 and 2).

Security-sensitive: a bug here is a bug in the wall the rest of the
enrichment loop is built behind, not a wrong document. The first half is
about something the jail must NEVER show — outside its roots, through a
symlink (direct or chained), under a spelling a case-insensitive filesystem
would accept but `.sextantignore` never matches, `.sextantignore`'d
outright, a derived-output directory (`target/`, ...) — including one
judged against the WRONG root when roots nest — or Task 3's ruling that the
overlay itself is invisible — coming back as a plain refusal STRING, never
an exception, and never one that echoes raw diagnostic text at the model.
It also covers the two correctness bugs fix round 2 found in the nested
layout itself (a file counted twice; a workspace path that happened to
contain "target" blanking real content). The second half is ordinary
behaviour: line-ranged reads, glob find, grep with a match cap, and the
redaction-on-read pass that a config file's planted credential proves end
to end.
"""

from pathlib import Path

import pytest

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
    class's own construction-time invariant; a test exercising SIBLING
    roots passes an `ignore` loaded for their common parent explicitly."""
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


class _ExplodingRedactor:
    """A redactor that always fails on `redact_text` — the one
    deliberately UNEXPECTED failure this suite triggers on purpose (2K
    Task 5 fix round 1, I4), to prove `execute` still never raises and
    never lets the raw failure text reach the model."""

    def redact_text(self, text: str) -> str:
        raise RuntimeError(f"boom: cannot redact {text!r} — /private/host/path/leaked")


# --- The jail: containment, never through a symlink -------------------------


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


def test_a_symlink_inside_a_root_pointing_outside_is_refused(tmp_path: Path):
    """The jail never follows a symlink at all (2K Task 5 fix round 1,
    C1) — not "follow it, then refuse once the target turns out to be
    outside": a symlink is refused the instant it is MET. The refusal is
    the SAME "is not available" string every other invisible path gets
    (2K Task 5 fix round 2, N4) — "outside the allowed roots" would be a
    false statement for a symlink pointing back INSIDE the jail, and would
    tell a model it specifically found a symlink, which "is not available"
    deliberately does not."""
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("not yours\n")
    (root / "escape").symlink_to(outside)
    executor = _executor((root,))
    result = executor.execute("read_file", {"path": "escape/secret.txt"})
    assert result == "refused: escape/secret.txt is not available"
    assert "not yours" not in result


def test_a_path_genuinely_inside_the_root_is_accepted(tmp_path: Path):
    """The positive control for the refusals around it: the jail is not
    just a wall, it lets a real, contained, non-symlinked path through."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "safe.txt").write_text("hi\n")
    executor = _executor((root,))
    assert executor.execute("read_file", {"path": "safe.txt"}) == "hi"


def test_a_path_that_does_not_exist_in_any_root_is_a_plain_miss(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    executor = _executor((root,))
    result = executor.execute("read_file", {"path": "nope.txt"})
    assert result == "refused: nope.txt is not available"


# --- C1: find/grep must not read (or reveal) through a symlink --------------


def test_grep_cannot_read_through_a_symlink_aliasing_an_ignored_file(tmp_path: Path):
    """The exact escape the reviewer reproduced live: `innocent.txt` is a
    symlink to `.env`, and `.env` itself is separately excluded — but
    that separate exclusion is not what closes this hole. Before the fix,
    the WALK route (`find`/`grep`) never re-checked a walked candidate
    for being a symlink at all, so `innocent.txt` sailed through as an
    ordinary file and `grep` read straight through it to `.env`'s
    content."""
    root = tmp_path / "root"
    root.mkdir()
    (root / ".env").write_text("FAKE_SECRET=must-not-leak\n")
    (root / "innocent.txt").symlink_to(root / ".env")
    executor = _executor((root,))
    assert executor.execute("find", {"pattern": "innocent.txt"}) == ""
    assert executor.execute("find", {"pattern": ".env"}) == ""
    assert executor.execute("grep", {"pattern": "FAKE_SECRET"}) == ""
    assert executor.execute("read_file", {"path": "innocent.txt"}) == (
        "refused: innocent.txt is not available"
    )


def test_a_symlink_chain_to_outside_the_jail_leaks_nothing_through_either_alias(tmp_path: Path):
    """`root/a -> root/b -> /outside/secret`: TWO aliases, chained, both
    living inside the jailed root. Before the fix, `find` listed both
    names and `grep` read the outside file's content through EITHER one
    (leaking it twice, once per alias) — `_walk_visible` now refuses to
    even descend past the first symlink it meets, so the chain is never
    walked at all."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside-secret-marker\n")
    root = tmp_path / "root"
    root.mkdir()
    (root / "b").symlink_to(outside / "secret.txt")
    (root / "a").symlink_to(root / "b")
    executor = _executor((root,))
    assert executor.execute("find", {"pattern": "a"}) == ""
    assert executor.execute("find", {"pattern": "b"}) == ""
    assert executor.execute("grep", {"pattern": "outside-secret-marker"}) == ""
    assert executor.execute("read_file", {"path": "a"}) == "refused: a is not available"
    assert executor.execute("read_file", {"path": "b"}) == "refused: b is not available"


# --- C2: a case-insensitive filesystem must not bypass an exclusion --------


def test_a_case_insensitive_filesystem_cannot_bypass_the_builtin_ignore_pattern():
    """`.ENV` against a real `.env`: on a case-preserving-but-insensitive
    filesystem (macOS's default), the OS opens the file regardless of the
    case the caller spelled — `_walk_segments` must not trust that lookup,
    only the REAL directory entry's own spelling."""
    executor = _fixture_executor()
    result = executor.execute("read_file", {"path": ".ENV"})
    assert result == "refused: .ENV is not available"
    assert "FAKE_SECRET" not in result


def test_a_case_insensitive_filesystem_cannot_bypass_a_repo_ignore_pattern(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    (root / ".sextantignore").write_text("secret.txt\n")
    (root / "secret.txt").write_text("do-not-leak\n")
    executor = _executor((root,))
    # Sanity: the correctly-cased path IS excluded.
    assert executor.execute("read_file", {"path": "secret.txt"}) == (
        "refused: secret.txt is not available"
    )
    result = executor.execute("read_file", {"path": "SECRET.TXT"})
    assert result == "refused: SECRET.TXT is not available"
    assert "do-not-leak" not in result


def test_a_case_insensitive_filesystem_cannot_bypass_the_overlay_exclusion():
    executor = _fixture_executor()
    result = executor.execute("read_file", {"path": ".SEXTANT-ENRICHMENT.JSON"})
    assert result == "refused: .SEXTANT-ENRICHMENT.JSON is not available"
    assert "Legacy billing edge" not in result


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
    assert executor.execute("read_file", {"path": ".env"}) == "refused: .env is not available"


def test_a_repo_ignore_pattern_file_is_invisible_everywhere_and_unreadable():
    """`application-secret.yml` — excluded by the fixture's OWN
    `.sextantignore` line, the repo layer rather than a built-in."""
    executor = _fixture_executor()
    listing = executor.execute("list_dir", {"path": "src/main/resources"}).splitlines()
    assert "application-secret.yml" not in listing
    found = executor.execute("find", {"pattern": "application-secret.yml"}).splitlines()
    assert "src/main/resources/application-secret.yml" not in found
    scoped = executor.execute(
        "grep", {"pattern": "should-never-resolve", "path": "src/main/resources"}
    )
    assert scoped == ""
    result = executor.execute("read_file", {"path": "src/main/resources/application-secret.yml"})
    assert result == ("refused: src/main/resources/application-secret.yml is not available")


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
    assert result == f"refused: {ENRICHMENT_FILE} is not available"


def test_i3_excluded_and_missing_are_the_same_message_no_existence_oracle():
    """2K Task 5 fix round 1, I3: a model refused on `.env` (which
    exists, excluded) and a model refused on a name that plainly does not
    exist must see the IDENTICAL string — the previous two-message split
    was an existence oracle for exactly the file names an attacker would
    probe for."""
    executor = _fixture_executor()
    excluded = executor.execute("read_file", {"path": ".env"})
    missing = executor.execute("read_file", {"path": "there-is-truly-no-such-file.txt"})
    assert excluded == "refused: .env is not available"
    assert missing == "refused: there-is-truly-no-such-file.txt is not available"


# --- Derived-output directories (2K Task 5 fix round 1 ruling) -------------


def test_a_derived_output_directory_is_invisible_and_unreadable(tmp_path: Path):
    """`target/` (also `build/`, `out/`, `node_modules/`, `.git/`):
    invisible and unreadable everywhere in the jail, ancestry included —
    a JAIL-specific exclusion joining `ENRICHMENT_FILE`'s own precedent,
    NOT added to `.sextantignore`'s built-in patterns."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "src.txt").write_text("real source\n")
    built = root / "target" / "classes"
    built.mkdir(parents=True)
    (built / "application-secret.yml").write_text("decoy: should-never-resolve\n")
    executor = _executor((root,))
    listing = executor.execute("list_dir", {"path": "."}).splitlines()
    assert "target/" not in listing
    assert "src.txt" in listing
    assert executor.execute("find", {"pattern": "application-secret.yml"}) == ""
    assert executor.execute("grep", {"pattern": "should-never-resolve"}) == ""
    result = executor.execute("read_file", {"path": "target/classes/application-secret.yml"})
    assert result == "refused: target/classes/application-secret.yml is not available"


def test_the_fixtures_own_compiled_decoy_under_target_is_also_invisible_and_unreadable(
    resolved_fixture: object,
):
    """The exact scenario reviewed live: `target/classes/
    application-secret.yml` is Maven's own copy of the fixture's planted
    decoy (`process-resources`, part of `mvn compile`'s lifecycle) — a
    path `.sextantignore`'s pattern never named, since that pattern only
    ever excluded the SOURCE path. `target/` is gitignored, so nothing
    guarantees it exists in a fresh checkout; `resolved_fixture` (unused
    beyond its side effect) is `tests/application/conftest.py`'s own
    SESSION-cached `mvn compile`, reused here rather than this test
    running a second, ad-hoc compile of its own — an extra compile call
    site on the same shared fixture directory is exactly the kind of
    thing that turned out to make an unrelated test flake once during
    this fix round."""
    compiled = FIXTURE / "target" / "classes" / "application-secret.yml"
    assert compiled.is_file(), "resolved_fixture did not compile the fixture as expected"
    executor = _fixture_executor()
    listing = executor.execute("list_dir", {"path": "."}).splitlines()
    assert "target/" not in listing
    assert executor.execute("find", {"pattern": "application-secret.yml"}) == ""
    result = executor.execute("read_file", {"path": "target/classes/application-secret.yml"})
    assert result == "refused: target/classes/application-secret.yml is not available"


# --- N1 + N2: nested roots (2K Task 5 fix round 2) --------------------------


def test_find_and_grep_do_not_double_count_a_file_under_a_nested_root(tmp_path: Path):
    """2K Task 5 fix round 2, N1: the ordinary wiring nests the fact/render
    roots INSIDE the module root — a real fixture walked 279 entries for
    180 unique files without the fix, `find *.jsonl` printed each name
    twice, and `MAX_GREP_MATCHES` counted double. Each file must appear
    exactly once, displayed relative to its OWN most specific root
    (`a.jsonl`, never `.sextant/facts/a.jsonl`)."""
    module_root = tmp_path / "module"
    module_root.mkdir()
    (module_root / "Source.txt").write_text("module source\n")
    fact_root = module_root / ".sextant" / "facts"
    fact_root.mkdir(parents=True)
    (fact_root / "a.jsonl").write_text("fact-a\n")
    (fact_root / "b.jsonl").write_text("fact-b\n")
    executor = _executor((module_root, fact_root))
    assert executor.execute("find", {"pattern": "*.jsonl"}).splitlines() == [
        "a.jsonl",
        "b.jsonl",
    ]
    assert executor.execute("grep", {"pattern": "fact-"}).splitlines() == [
        "a.jsonl:1:fact-a",
        "b.jsonl:1:fact-b",
    ]


def test_derived_output_exclusion_is_judged_against_the_most_specific_root(tmp_path: Path):
    """2K Task 5 fix round 2, N2 — the reviewer's exact reproduction:
    `--workspace target/ws` puts the fact root under a directory literally
    named `target`, and judging ancestry against the OUTER module root
    (which genuinely has `target` in it) rather than the fact root itself
    (which does not) silently blanked every fact/render file. A GENUINE
    `target/` directory living directly inside the module root — not the
    fact root's own ancestry — must still exclude, unchanged."""
    module_root = tmp_path / "module"
    module_root.mkdir()
    (module_root / "Source.txt").write_text("module source\n")
    # The fact root's OWN path happens to contain "target" — not Maven's
    # build output, just wherever `--workspace` was pointed.
    fact_root = module_root / "target" / "ws" / "facts"
    fact_root.mkdir(parents=True)
    (fact_root / "canary.jsonl").write_text("fact-canary\n")
    executor = _executor((module_root, fact_root))
    assert executor.execute("read_file", {"path": "canary.jsonl"}) == "fact-canary"
    assert executor.execute("find", {"pattern": "canary.jsonl"}).splitlines() == ["canary.jsonl"]
    assert executor.execute("grep", {"pattern": "fact-canary"}).splitlines() == [
        "canary.jsonl:1:fact-canary"
    ]
    # A real build directory inside the MODULE root (not the fact root's
    # own ancestry) still excludes exactly as before.
    built = module_root / "target" / "classes"
    built.mkdir(parents=True)
    (built / "Decoy.txt").write_text("built artifact\n")
    result = executor.execute("read_file", {"path": "target/classes/Decoy.txt"})
    assert result == "refused: target/classes/Decoy.txt is not available"


# --- N5: the tool descriptions state the symlink policy --------------------


def test_tool_descriptions_tell_the_model_symlinks_are_never_followed(tmp_path: Path):
    """2K Task 5 fix round 2, N5: a repository with a symlinked source
    directory goes quietly invisible under the never-follow-symlinks
    policy — the tool descriptions the model actually reads have to say
    so, not only the spec, or the model has no way to explain what it is
    seeing."""
    executor = _executor((tmp_path,))
    for tool in executor.definitions():
        assert "symlink" in tool.description.lower(), tool.name


# --- I4: a mis-wired ignore root fails construction, loudly, generically ---


def test_construction_refuses_a_mis_wired_ignore_root(tmp_path: Path):
    """`ignore` must be loaded for a repository root that CONTAINS every
    jailed root. Before this check, a mismatch here made EVERY tool call
    refuse with the raw `ValueError` text — an absolute host path —
    echoed into the model-visible refusal, looking exactly like an
    ordinary-but-broken jail rather than a wiring bug."""
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ValueError):
        ToolExecutor(
            roots=(root,), redactor=Redactor.from_rules(), ignore=IgnoreRules.load(unrelated)
        )


def test_an_unexpected_failure_never_escapes_and_never_leaks_its_text_to_the_model(
    tmp_path: Path,
):
    """A deliberately-broken `redactor` (any OTHER unforeseen failure
    would behave identically) proves `execute`'s outer guarantee: the
    MODEL-visible result is a generic message, never the raw exception —
    which could carry an absolute host path — while the raw text is kept
    ONLY in the transcript, under `error`, for a human to read later."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("hello\n")
    executor = ToolExecutor(
        roots=(root,), redactor=_ExplodingRedactor(), ignore=IgnoreRules.load(root)
    )
    result = executor.execute("read_file", {"path": "a.txt"})
    assert result == "refused: read_file could not be completed"
    assert "boom" not in result
    assert "/private/host/path" not in result
    entry = executor.transcript[-1]
    assert entry["result"] == result
    assert "boom" in str(entry["error"])


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


def test_config_bearing_extensions_pins_both_directions_against_the_real_registry():
    """2K Task 5 brief: "config-bearing detection ... reuse that registry
    knowledge, state the rule." `tools.py` cannot IMPORT
    `sextant.ingress.read.registry.READERS` (`application` sits below
    `ingress` in `.importlinter`'s layering), so this test is where the
    mirror is checked — against the SAME registry `cli/app.py` builds
    `analyze()`'s readers from, not a second, independently-hardcoded
    reader list (2K Task 5 fix round 1, minor) — in BOTH directions."""
    from sextant.ingress.read.registry import READERS

    config_readers = [reader for reader in READERS if reader.reads_schema_sources is False]
    schema_readers = [reader for reader in READERS if reader.reads_schema_sources is True]
    assert {reader.__class__.__name__ for reader in config_readers} == {
        "PropertiesReader",
        "YamlConfigReader",
    }
    # Direction 1: every extension THIS MODULE claims is config-bearing is
    # accepted by a config reader and by no schema reader.
    for extension in CONFIG_BEARING_EXTENSIONS:
        assert any(reader.accepts(extension) for reader in config_readers)
        assert not any(reader.accepts(extension) for reader in schema_readers)
    # Direction 2: every extension a SCHEMA reader claims is not also
    # claimed by a config reader and is not in this module's set — the
    # reverse drift (a schema reader gaining an extension this constant
    # would then wrongly key-mask) `tools.py`'s own comment warns about.
    known_schema_extensions = {"avsc", "graphqls", "graphql", "proto", "wsdl", "xsd"}
    for extension in known_schema_extensions:
        assert any(reader.accepts(extension) for reader in schema_readers)
        assert not any(reader.accepts(extension) for reader in config_readers)
        assert extension not in CONFIG_BEARING_EXTENSIONS


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
    so a source file keeps its own comment mentioning `password`
    verbatim, while a credential riding a URL's userinfo still comes
    out."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "Client.txt").write_text(
        '// password: not-a-config-key, left alone\nString uri = "https://user:s3cret@host/path";\n'
    )
    executor = _executor((root,))
    content = executor.execute("read_file", {"path": "Client.txt"})
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


def test_transcript_args_are_stored_as_a_copy_not_a_reference(tmp_path: Path):
    """2K Task 5 fix round 1, minor: a caller (Task 6's loop) that reuses
    or mutates its own `args` dict after the call must not silently
    rewrite the transcript's record of what was actually asked for."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("hello\n")
    executor = _executor((root,))
    args = {"path": "a.txt"}
    executor.execute("read_file", args)
    args["path"] = "mutated-after-the-call"
    assert executor.transcript[0]["args"] == {"path": "a.txt"}


def test_definitions_returns_the_four_tools_each_with_a_json_schema(tmp_path: Path):
    executor = _executor((tmp_path,))
    definitions = executor.definitions()
    assert [tool.name for tool in definitions] == ["list_dir", "find", "grep", "read_file"]
    for tool in definitions:
        assert tool.schema["type"] == "object"
        assert "properties" in tool.schema
        assert "required" in tool.schema
