"""The enrichment tools and the jail (2K design §4, Task 5 brief + fix
rounds 1 to 4).

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
contain "target" blanking real content) and, since fix round 4, the
DISPLAY contract every tool shares: one anchor, one spelling per file,
distinct citations for distinct files, no absolute host path ever, and the
four tools agreeing about a tree that changed mid-run. The second half is ordinary
behaviour: line-ranged reads, glob find, grep with a match cap, and the
redaction-on-read pass that a config file's planted credential proves end
to end.
"""

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from sextant.application.enrich.tools import (
    CONFIG_BEARING_EXTENSIONS,
    MAX_GREP_MATCHES,
    MAX_RESULT_BYTES,
    ToolExecutor,
)
from sextant.cli.app import cli
from sextant.domain.enrichment import ENRICHMENT_FILE
from sextant.domain.ignorefile import IgnoreRules
from sextant.domain.redaction import REDACTED, Redactor
from sextant.ingress.detect.sextant_config import read_redaction_rules

REPO = Path(__file__).parents[2]
FIXTURE = REPO / "fixtures" / "orders-service"


def _fixture_workspace_is_current(metadata_path: Path) -> bool:
    """Mirrors `tests/fixture_stub.is_current`: a build is current when it
    exists and postdates every source file it could have come from — the
    same mtime-comparison shape, over `orders-service`'s own sources rather
    than the stub library's."""
    if not metadata_path.is_file():
        return False
    built = metadata_path.stat().st_mtime
    sources = [
        *(FIXTURE / "src").rglob("*"),
        FIXTURE / "pom.xml",
        FIXTURE / ".sextant.yml",
        FIXTURE / ".sextantignore",
    ]
    return all(source.stat().st_mtime <= built for source in sources if source.is_file())


def _build_fixture_workspace() -> None:
    """A real, full `sextant module analyze` against `FIXTURE`'s own default
    `.sextant` workspace (2K Task 7 fix round 1, CRITICAL C1a) — the
    precondition every `_fixture_executor()` test in this module needs: a
    real fact tree at the location the enrichment jail is wired to read by
    default. Nothing else in this suite or in CI (`.github/workflows/
    pr.yml`'s priming step only runs `mvn compile`) builds it — `.sextant/`
    is gitignored, and every OTHER test in this repo analyzes into an
    isolated `tmp_path` instead, which is exactly why this one was silently
    depending on a developer's own uncommitted leftover before this fixture
    existed."""
    subprocess.run(["mvn", "-q", "-o", "compile"], cwd=FIXTURE, check=True)
    result = CliRunner().invoke(cli, ["module", "analyze", str(FIXTURE)])
    if result.exit_code != 0:
        raise RuntimeError(
            f"could not build the fixture workspace via `sextant module analyze {FIXTURE}`: "
            f"{result.output}"
        )


@pytest.fixture(scope="session", autouse=True)
def _fixture_workspace_ready(stub_library_in_the_local_repository: Path) -> None:
    """Ensures `FIXTURE/.sextant` exists and is current before any test in
    THIS module runs — file-local autouse, so no other test file pays for
    it (`tests/application/conftest.py`'s own `resolved_fixture` fixture is
    the analogous, explicitly-requested precedent for `mvn compile` alone;
    this is one level further, a full `analyze`). Current-state check
    mirrors `tests/fixture_stub.is_current`/`is_current`'s own precedent:
    the warm path (a developer who already ran `analyze` here, or a second
    test file collected in the same session) costs one stat per source
    file and nothing else; a fresh clone rebuilds it deterministically,
    once, for the whole session. `stub_library_in_the_local_repository` is
    requested — unused beyond ordering — because `orders-service` declares
    a dependency on it, and `mvn compile` fails to resolve without it."""
    metadata_path = FIXTURE / ".sextant" / "metadata.json"
    if not _fixture_workspace_is_current(metadata_path):
        _build_fixture_workspace()


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
    exactly once — spelled, since fix round 4, relative to the ONE display
    anchor (`.sextant/facts/a.jsonl`, the accepted cosmetic regression from
    rounds 2/3's bare `a.jsonl`), and reading back through that citation as
    well as through the fact root's own spelling."""
    module_root = tmp_path / "module"
    module_root.mkdir()
    (module_root / "Source.txt").write_text("module source\n")
    fact_root = module_root / ".sextant" / "facts"
    fact_root.mkdir(parents=True)
    (fact_root / "a.jsonl").write_text("fact-a\n")
    (fact_root / "b.jsonl").write_text("fact-b\n")
    executor = _executor((module_root, fact_root))
    assert executor.execute("find", {"pattern": "*.jsonl"}).splitlines() == [
        ".sextant/facts/a.jsonl",
        ".sextant/facts/b.jsonl",
    ]
    assert executor.execute("grep", {"pattern": "fact-"}).splitlines() == [
        ".sextant/facts/a.jsonl:1:fact-a",
        ".sextant/facts/b.jsonl:1:fact-b",
    ]
    # Round-trip: both citations read back the file they named...
    assert executor.execute("read_file", {"path": ".sextant/facts/a.jsonl"}) == "fact-a"
    assert executor.execute("read_file", {"path": ".sextant/facts/b.jsonl"}) == "fact-b"
    # ...and resolution stays permissive, so the fact root's own spelling
    # — what fix rounds 2 and 3 PRINTED — still reads too.
    assert executor.execute("read_file", {"path": "a.jsonl"}) == "fact-a"


def test_a_display_name_collision_between_nested_roots_is_disambiguated(tmp_path: Path):
    """2K Task 5 fix round 3, N1b (round-2 regression): the §5/§6b render
    layout is the realistic trigger — `architecture.md` rendered at the
    module root's `.sextant/render` AND a same-named file living directly
    at the module root both named as bare `architecture.md` under
    most-specific-root spelling alone, so `find` printed the identical
    line twice and `read_file architecture.md` could only ever reach the
    module-root copy — the render copy was unreachable by any name. Both
    must now get DISTINCT citations, and each citation must round-trip
    through BOTH `read_file` and `grep` to the exact file it named. Fix
    round 4 keeps the identical expectations for a different reason: the
    single anchor (here the module root) separates the two by
    construction, with no collision pass to get right."""
    module_root = tmp_path / "module"
    module_root.mkdir()
    (module_root / "architecture.md").write_text("module-level doc\n")
    render_root = module_root / ".sextant" / "render"
    render_root.mkdir(parents=True)
    (render_root / "architecture.md").write_text("rendered doc\n")
    executor = _executor((module_root, render_root))

    found = executor.execute("find", {"pattern": "architecture.md"}).splitlines()
    assert len(found) == 2
    assert len(set(found)) == 2, "the two files must not print the identical citation"
    assert set(found) == {"architecture.md", ".sextant/render/architecture.md"}

    # Every citation `find` printed reads back, via `read_file`, the exact
    # file it came from — not merely SOME file.
    by_citation = {
        citation: executor.execute("read_file", {"path": citation}) for citation in found
    }
    assert by_citation["architecture.md"] == "module-level doc"
    assert by_citation[".sextant/render/architecture.md"] == "rendered doc"

    # `grep` labels each match with the SAME two citations, and each
    # match's own line is the right file's own content.
    grepped: dict[str, str] = {}
    for line in executor.execute("grep", {"pattern": "doc"}).splitlines():
        path, _line_number, text = line.split(":", 2)
        grepped[path] = text
    assert grepped == {
        "architecture.md": "module-level doc",
        ".sextant/render/architecture.md": "rendered doc",
    }


def test_same_named_files_under_sibling_roots_get_distinct_round_tripping_citations(
    tmp_path: Path,
):
    """2K Task 5 fix round 4, S1 — the shape rounds 2 and 3 could not name:
    SIBLING roots (`repo/mod` and `repo/ws/render`, neither containing the
    other) each holding an `Order.java`. Per-file naming, most-specific or
    outermost, gave BOTH the bare name — the same collision, one file
    unreachable. Under the one anchor both are distinct by construction,
    and each citation must read back its own file through `read_file` and
    through a scoped `grep`."""
    repo = tmp_path / "repo"
    module_root = repo / "mod"
    module_root.mkdir(parents=True)
    (module_root / "Order.java").write_text("class Order {} // module\n")
    render_root = repo / "ws" / "render"
    render_root.mkdir(parents=True)
    (render_root / "Order.java").write_text("class Order {} // rendered\n")
    executor = _executor((module_root, render_root), ignore=IgnoreRules.load(repo))

    found = executor.execute("find", {"pattern": "Order.java"}).splitlines()
    assert found == ["mod/Order.java", "ws/render/Order.java"]

    reads = {citation: executor.execute("read_file", {"path": citation}) for citation in found}
    assert reads == {
        "mod/Order.java": "class Order {} // module",
        "ws/render/Order.java": "class Order {} // rendered",
    }
    for citation, content in reads.items():
        scoped = executor.execute("grep", {"pattern": "class Order", "path": citation})
        assert scoped == f"{citation}:1:{content}"


def test_a_nested_secrets_directory_is_excluded_like_one_at_the_anchor_top_level(
    tmp_path: Path,
):
    """2K Task 5 fix round 5, A1 — a Task-2 gap the anchor wiring exposed:
    `matches` judges a path relative to the REPOSITORY root, and the
    built-in `secrets/**` contained a slash, which gitignore anchors to
    that root. A module one directory down (`repo/mod`, the ordinary shape
    once the anchor is the repository rather than the module) therefore
    kept its whole `secrets/` tree readable — `read_file
    "mod/secrets/s.txt"` returned the content. `**/secrets/**` matches at
    every depth INCLUDING the top level, so both trees must now be
    invisible to all four tools."""
    repo = tmp_path / "repo"
    top_secrets = repo / "secrets"
    top_secrets.mkdir(parents=True)
    (top_secrets / "top.txt").write_text("top-secret-marker\n")
    module_root = repo / "mod"
    nested_secrets = module_root / "secrets"
    nested_secrets.mkdir(parents=True)
    (nested_secrets / "nested.txt").write_text("nested-secret-marker\n")
    (module_root / "Source.txt").write_text("real source\n")
    executor = _executor((repo, module_root), ignore=IgnoreRules.load(repo))

    assert executor.execute("find", {"pattern": "*.txt"}).splitlines() == ["mod/Source.txt"]
    assert executor.execute("grep", {"pattern": "secret-marker"}) == ""
    # The DIRECTORY entry itself still lists — `**/secrets/**` names what is
    # UNDER it, exactly as `secrets/**` always did at the top level — but it
    # lists as empty and nothing inside it can be read, at BOTH depths. The
    # point of A1 is that the two depths now behave identically.
    assert executor.execute("list_dir", {"path": "mod"}).splitlines() == [
        "Source.txt",
        "secrets/",
    ]
    assert executor.execute("list_dir", {"path": "."}).splitlines() == ["mod/", "secrets/"]
    assert executor.execute("list_dir", {"path": "mod/secrets"}) == ""
    assert executor.execute("list_dir", {"path": "secrets"}) == ""
    assert executor.execute("read_file", {"path": "mod/secrets/nested.txt"}) == (
        "refused: mod/secrets/nested.txt is not available"
    )
    assert executor.execute("read_file", {"path": "secrets/top.txt"}) == (
        "refused: secrets/top.txt is not available"
    )
    # The convenience spelling (relative to the nested root) is refused too
    # — one policy, every route.
    assert executor.execute("read_file", {"path": "secrets/nested.txt"}) == (
        "refused: secrets/nested.txt is not available"
    )


def test_a_decoy_under_a_root_cannot_shadow_an_anchor_relative_citation(tmp_path: Path):
    """2K Task 5 fix round 5, A2: citations are minted anchor-relative, so
    the ANCHOR's reading of a path has to be the canonical one. With an
    anchor of `repo` and a root of `repo/mod`, trying the ROOT walk first
    made the citation `mod/notes.md` — minted for `repo/mod/notes.md` —
    resolve to `repo/mod/mod/notes.md` instead: a citation silently
    returning a file it did not name, with the named file unreachable.
    Each file must answer to its OWN citation, both round-tripping."""
    repo = tmp_path / "repo"
    module_root = repo / "mod"
    module_root.mkdir(parents=True)
    (module_root / "notes.md").write_text("the real notes\n")
    decoy = module_root / "mod"
    decoy.mkdir()
    (decoy / "notes.md").write_text("the decoy notes\n")
    executor = _executor((module_root,), ignore=IgnoreRules.load(repo))

    found = executor.execute("find", {"pattern": "notes.md"}).splitlines()
    assert found == ["mod/mod/notes.md", "mod/notes.md"]
    assert executor.execute("read_file", {"path": "mod/notes.md"}) == "the real notes"
    assert executor.execute("read_file", {"path": "mod/mod/notes.md"}) == "the decoy notes"
    # `grep` scoped to each citation searches the file that citation names.
    assert executor.execute("grep", {"pattern": "notes", "path": "mod/notes.md"}) == (
        "mod/notes.md:1:the real notes"
    )
    assert executor.execute("grep", {"pattern": "notes", "path": "mod/mod/notes.md"}) == (
        "mod/mod/notes.md:1:the decoy notes"
    )


def test_a_file_created_after_construction_never_leaks_an_absolute_host_path(tmp_path: Path):
    """2K Task 5 fix round 4, S2: the naming cache was built on first use,
    so a file the live tree gained afterward was unknown to it, and the
    fallback for an unknown file was `path.as_posix()` — an ABSOLUTE HOST
    PATH in a model-visible scoped-`grep` result, the one thing this jail
    never emits. With naming derived from the anchor alone there is no
    fallback branch left; this asserts on the ABSENCE, over every tool,
    whatever each one decides to report."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "existing.txt").write_text("needle existing\n")
    executor = _executor((root,))
    # Warm every path that used to populate the cache.
    executor.execute("find", {"pattern": "*.txt"})
    executor.execute("grep", {"pattern": "needle"})

    (root / "created.txt").write_text("needle created\n")
    results = [
        executor.execute("list_dir", {"path": "."}),
        executor.execute("find", {"pattern": "*.txt"}),
        executor.execute("grep", {"pattern": "needle"}),
        executor.execute("grep", {"pattern": "needle", "path": "created.txt"}),
        executor.execute("read_file", {"path": "created.txt"}),
    ]
    for result in results:
        assert str(tmp_path) not in result
        assert not any(line.startswith("/") for line in result.splitlines())


def test_the_four_tools_agree_about_a_file_created_after_construction(tmp_path: Path):
    """2K Task 5 fix round 4, S3: `find`/`grep` answered from a cached
    snapshot while `read_file`/`list_dir` walked the live tree, so a file
    created mid-run was readable and listable while the search tools swore
    it did not exist — a model told, by its own tools, two different
    truths. Nothing is cached now, so all four see the same tree; this
    pins that they agree."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "existing.txt").write_text("needle existing\n")
    executor = _executor((root,))
    assert executor.execute("find", {"pattern": "*.txt"}).splitlines() == ["existing.txt"]

    (root / "created.txt").write_text("needle created\n")
    assert executor.execute("find", {"pattern": "*.txt"}).splitlines() == [
        "created.txt",
        "existing.txt",
    ]
    assert executor.execute("grep", {"pattern": "needle created"}).splitlines() == [
        "created.txt:1:needle created"
    ]
    assert "created.txt" in executor.execute("list_dir", {"path": "."}).splitlines()
    assert executor.execute("read_file", {"path": "created.txt"}) == "needle created"


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
    # The citation is anchor-relative (fix round 4), so it SHOWS the
    # `target` segment the fact root happens to live under — and still
    # reads, because the exclusion is judged against the fact root itself.
    assert executor.execute("find", {"pattern": "canary.jsonl"}).splitlines() == [
        "target/ws/facts/canary.jsonl"
    ]
    assert executor.execute("grep", {"pattern": "fact-canary"}).splitlines() == [
        "target/ws/facts/canary.jsonl:1:fact-canary"
    ]
    assert executor.execute("read_file", {"path": "target/ws/facts/canary.jsonl"}) == "fact-canary"
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


def test_construction_refuses_a_jailed_root_that_does_not_exist_yet(tmp_path: Path):
    """2K Task 7 fix round 1, CRITICAL C1b: before this, a missing root (an
    analysed-but-unrendered workspace's absent `.sextant/render`, say)
    degraded silently — every call still returned a string, but every
    `find`/`grep` came back the opaque `"refused: ... could not be
    completed"` `_walk_visible` produces when `list_directory` raises on a
    directory that is not there. A caller needs that at construction,
    loudly, not discovered one degraded tool call at a time — this is the
    exact live failure mode 2K Task 7's own golden-overlay regeneration hit."""
    root = tmp_path / "root"
    root.mkdir()
    missing = tmp_path / "root" / "does-not-exist"
    with pytest.raises(ValueError, match="does not exist"):
        ToolExecutor(
            roots=(root, missing), redactor=Redactor.from_rules(), ignore=IgnoreRules.load(root)
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
    """Two SIBLING roots: every citation is relative to the one anchor
    their `ignore` was loaded for (fix round 4), so each carries its own
    root's segment — `a/one.txt`, not the bare `one.txt` rounds 1-3
    printed."""
    root_a = tmp_path / "a"
    root_a.mkdir()
    root_b = tmp_path / "b"
    root_b.mkdir()
    (root_a / "one.txt").write_text("alpha\nneedle here\n")
    (root_b / "two.txt").write_text("needle again\nbeta\n")
    executor = _executor((root_a, root_b), ignore=IgnoreRules.load(tmp_path))
    result = executor.execute("grep", {"pattern": "needle"})
    assert result.splitlines() == ["a/one.txt:2:needle here", "b/two.txt:1:needle again"]


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
    instead — the credential the read_file test proves is masked from
    `application.yml` must also be absent from every grep match SCOPED to
    that same file.

    Scoped, not jail-wide (2K Task 7 fix round 1, CRITICAL C1a): the raw
    fact tree stores values VERBATIM by design (`domain/redaction.py`'s
    "the workspace stays verbatim") and a `.jsonl` fact file is not itself
    a config-bearing file by extension, so `.sextant/facts/config/
    application.yml.jsonl` genuinely carries this value unmasked once the
    fixture workspace is a real, full `analyze` — an unscoped grep WOULD
    find it there. That is a stated boundary of the raw fact root being one
    of the three jailed roots by design (2K design §4), not a masking
    failure this test exists to catch; what redaction-on-read actually
    promises — proven here, on the file it is proven for by `read_file` two
    tests above — is scoped to where the promise is made."""
    executor = _fixture_executor()
    assert (
        executor.execute(
            "grep", {"pattern": "hunter2-fixture", "path": "src/main/resources/application.yml"}
        )
        == ""
    )


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
