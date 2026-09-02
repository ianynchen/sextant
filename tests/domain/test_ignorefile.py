"""`.sextantignore` (2K design §2). What these tests protect: git's own
wildmatch semantics reach Sextant unchanged (negation, dir-only patterns,
anchoring, `**`), and the built-in security layer beneath a repo's own file
cannot be switched off by anything a repository writes."""

from pathlib import Path

from sextant.domain.ignorefile import BUILTIN_PATTERNS, IgnoreRules


def _write_ignorefile(repo_root: Path, *lines: str) -> None:
    (repo_root / ".sextantignore").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_missing_ignorefile_still_applies_the_builtins_only(tmp_path: Path):
    """No `.sextantignore` at all is the ordinary case for a repo that never
    opted in — it must not mean "ignore nothing"; the built-in credential
    patterns still apply."""
    rules = IgnoreRules.load(tmp_path)
    assert rules.matches(tmp_path / ".env") is True
    assert rules.matches(tmp_path / "src" / "main" / "resources" / "application.yml") is False


def test_every_builtin_pattern_matches_with_no_repo_file_present(tmp_path: Path):
    """One live check per built-in shape, so the tuple in `ignorefile.py` and
    the credential file names it is meant to catch never drift apart."""
    rules = IgnoreRules.load(tmp_path)
    samples = {
        ".env": ".env",
        ".env.*": ".env.local",
        "*.pem": "server.pem",
        "*.p12": "keystore.p12",
        "*.jks": "truststore.jks",
        "id_rsa*": "id_rsa",
        "id_ed25519*": "id_ed25519.pub",
        "secrets/**": "secrets/db/password.txt",
        "*.keystore": "app.keystore",
    }
    assert set(samples) == set(BUILTIN_PATTERNS)
    for name, relative in samples.items():
        assert rules.matches(tmp_path / relative) is True, name


def test_a_repo_negation_cannot_re_admit_a_builtin_match(tmp_path: Path):
    """The two-layer safety rule, stated as behaviour: `!.env` is a valid
    gitignore negation, and it works for a repo's OWN patterns (the next
    test proves that) — but the built-in layer never sees it, so a `.env`
    stays ignored regardless of what a `.sextantignore` says about it."""
    _write_ignorefile(tmp_path, "!.env")
    rules = IgnoreRules.load(tmp_path)
    assert rules.matches(tmp_path / ".env") is True


def test_negation_among_the_repos_own_patterns_re_admits_a_file(tmp_path: Path):
    """The positive half: within the repo's OWN patterns (nothing built-in
    involved), full gitignore semantics apply, negation included."""
    _write_ignorefile(tmp_path, "*.tmp", "!keep.tmp")
    rules = IgnoreRules.load(tmp_path)
    assert rules.matches(tmp_path / "scratch.tmp") is True
    assert rules.matches(tmp_path / "keep.tmp") is False


def test_a_dir_only_pattern_ignores_everything_under_it(tmp_path: Path):
    """`build/` (trailing slash) is git's directory-only form — it must
    ignore every file under that directory, at any depth."""
    _write_ignorefile(tmp_path, "build/")
    rules = IgnoreRules.load(tmp_path)
    assert rules.matches(tmp_path / "build" / "output.txt") is True
    assert rules.matches(tmp_path / "build" / "nested" / "deep.txt") is True
    assert rules.matches(tmp_path / "not-build" / "output.txt") is False


def test_a_leading_slash_anchors_to_the_repo_root(tmp_path: Path):
    """`/only-here.yml` matches at the root only; the same name one
    directory down is untouched — anchoring is what makes the two different
    patterns rather than the same one written two ways."""
    _write_ignorefile(tmp_path, "/only-here.yml")
    rules = IgnoreRules.load(tmp_path)
    assert rules.matches(tmp_path / "only-here.yml") is True
    assert rules.matches(tmp_path / "nested" / "only-here.yml") is False


def test_an_unanchored_pattern_matches_at_any_depth(tmp_path: Path):
    """No leading slash and no interior slash: git matches the name at any
    depth, the opposite of the anchored case above."""
    _write_ignorefile(tmp_path, "everywhere.yml")
    rules = IgnoreRules.load(tmp_path)
    assert rules.matches(tmp_path / "everywhere.yml") is True
    assert rules.matches(tmp_path / "a" / "b" / "everywhere.yml") is True


def test_double_star_matches_across_any_number_of_directories(tmp_path: Path):
    _write_ignorefile(tmp_path, "config/**/local.yml")
    rules = IgnoreRules.load(tmp_path)
    assert rules.matches(tmp_path / "config" / "local.yml") is True
    assert rules.matches(tmp_path / "config" / "a" / "b" / "local.yml") is True
    assert rules.matches(tmp_path / "other" / "local.yml") is False


def test_matching_is_relative_to_the_repo_root_not_the_walked_root(tmp_path: Path):
    """A file three levels under the repo root — the shape a Maven module's
    `resource_roots` actually enumerates — is matched against its FULL path
    from the repo root, the way whoever wrote the `.sextantignore` saw it,
    never against a shorter path relative to the directory a walk happened
    to start from."""
    _write_ignorefile(tmp_path, "src/main/resources/ignored-secrets.yml")
    rules = IgnoreRules.load(tmp_path)
    nested = tmp_path / "src" / "main" / "resources" / "ignored-secrets.yml"
    assert rules.matches(nested) is True
    # A same-named file elsewhere is not swept in by the same pattern — the
    # pattern names a path, not a bare filename.
    assert (
        rules.matches(tmp_path / "src" / "main" / "resources" / "other" / "ignored-secrets.yml")
        is False
    )


def test_malformed_lines_are_read_the_way_git_reads_them(tmp_path: Path):
    """Comments and blank lines are not patterns; `pathspec`'s own
    `gitwildmatch` parsing decides this, and nothing here adds a stricter
    refusal on top of it (unlike `.sextant.yml`, which IS Sextant's own
    instruction format — a `.sextantignore` is gitignore's format, and this
    module's whole point is not inventing a second dialect of it)."""
    _write_ignorefile(tmp_path, "# a comment", "", "  ", "*.log")
    rules = IgnoreRules.load(tmp_path)
    assert rules.matches(tmp_path / "run.log") is True
    assert rules.matches(tmp_path / "# a comment") is False


def test_a_path_already_relative_to_the_repo_root_is_accepted_directly(tmp_path: Path):
    """`matches` is usable from either shape: an absolute path (what a
    filesystem walk hands back) or one already made relative — 2K Task 5's
    jail may already hold a relative candidate."""
    _write_ignorefile(tmp_path, "*.tmp")
    rules = IgnoreRules.load(tmp_path)
    assert rules.matches(Path("scratch.tmp")) is True
