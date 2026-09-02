"""`.sextant.yml` — Sextant's OWN input, and the one place a malformed file is
refused rather than read as an honest absence (DR-6's exemption)."""

from pathlib import Path

import pytest

from sextant.domain.redaction import RedactionRules
from sextant.ingress.detect.sextant_config import (
    SextantConfigError,
    read_extract_libraries,
    read_redaction_rules,
)


def _config(root: Path, text: str) -> Path:
    (root / ".sextant.yml").write_text(text, encoding="utf-8")
    return root


def test_a_module_with_no_config_file_opts_into_nothing(tmp_path: Path):
    """The default, and the shape of the isolation guarantee: a module that
    never asked for library extraction must reach the scan loop with nothing to
    scan, so its facts are what they were before any of this existed."""
    assert read_extract_libraries(tmp_path) == ()


def test_a_config_file_declaring_nothing_opts_into_nothing(tmp_path: Path):
    """An empty file — and one that declares the key with an empty list — are
    legitimate things to write while a coordinate is being added or removed.
    Structure is what is refused below, not silence."""
    assert read_extract_libraries(_config(tmp_path, "")) == ()
    assert read_extract_libraries(_config(tmp_path, "extract_libraries: []\n")) == ()


def test_the_declared_coordinates_are_returned_in_the_order_the_file_states_them(
    tmp_path: Path,
):
    """File order, not sorted order: the file is a written instruction, and
    re-ordering it would make the fact-tree write order depend on something
    other than what the author wrote (NFR-1)."""
    root = _config(
        tmp_path,
        "extract_libraries:\n  - com.example:orders-soap-client\n  - com.acme:shared-domain\n",
    )
    assert read_extract_libraries(root) == (
        "com.example:orders-soap-client",
        "com.acme:shared-domain",
    )


def test_a_coordinate_may_pin_its_own_version(tmp_path: Path):
    """The three-segment form is the author's OWN assertion of which release to
    read, and it is the escape hatch for the case the two-segment form cannot
    reach at all: a version managed by a parent POM or a BOM, which the detector
    does not resolve. It is returned verbatim — splitting it is resolution's
    job, not this reader's."""
    root = _config(tmp_path, "extract_libraries: ['com.example:orders-soap-client:1.0.0']\n")
    assert read_extract_libraries(root) == ("com.example:orders-soap-client:1.0.0",)


@pytest.mark.parametrize(
    ("text", "because"),
    [
        ("extract_libraries: [\n", "unparseable YAML is not an empty configuration"),
        ("- com.example:thing\n", "a list at the root declares no key at all"),
        (
            "extract_libaries: [com.example:thing]\n",
            "a misspelled key would otherwise read as extracting nothing",
        ),
        (
            "extract_libraries: com.example:thing\n",
            "one coordinate is still a list of one",
        ),
        ("extract_libraries: [42]\n", "a coordinate is a string"),
        ("extract_libraries: [orders-soap-client]\n", "a coordinate names a group"),
        (
            "extract_libraries: ['com.example:orders:1.0.0:jdk17']\n",
            "a fourth segment is a classifier, which the archive name would have to carry",
        ),
        (
            "extract_libraries: ['com.example:']\n",
            "an empty segment names no artifact and no directory",
        ),
        (
            "extract_libraries: ['..:orders']\n",
            "a coordinate becomes a directory, so it may not name a path segment",
        ),
    ],
)
def test_a_config_file_that_cannot_be_honoured_as_written_is_refused(
    tmp_path: Path, text: str, because: str
):
    """Every one of these would otherwise resolve to "extract nothing" —
    indistinguishable from an unconfigured module, and silently wrong for
    exactly as long as nobody checks. This file is an instruction TO Sextant,
    so a mistake in it is reported rather than skipped."""
    try:
        read_extract_libraries(_config(tmp_path, text))
    except SextantConfigError:
        return
    pytest.fail(f"honoured a config it cannot honour as written — {because}")


def test_a_module_declaring_no_redact_section_adds_no_rules(tmp_path: Path):
    """Which is not the same as redacting nothing: these are ADDITIONS, and the
    built-in set applies to every module whether or not it wrote a file (2K
    design §1). The empty answer here is what a module gets for free."""
    assert read_redaction_rules(tmp_path) == RedactionRules()
    assert read_redaction_rules(_config(tmp_path, "extract_libraries: []\n")) == RedactionRules()


def test_the_declared_redaction_patterns_are_returned_as_written(tmp_path: Path):
    """Both lists, verbatim: the redactor normalizes and sorts the EFFECTIVE
    set itself, so this reader's job is to say what the file asked for and
    refuse what it cannot."""
    root = _config(
        tmp_path,
        "redact:\n"
        "  key_patterns:\n    - dsn\n    - internal-token\n"
        "  value_patterns:\n    - 'ACME_[A-Z0-9]{24}'\n",
    )
    assert read_redaction_rules(root) == RedactionRules(
        key_patterns=("dsn", "internal-token"),
        value_patterns=("ACME_[A-Z0-9]{24}",),
    )


@pytest.mark.parametrize(
    ("text", "because"),
    [
        ("redact: [dsn]\n", "`redact` is a mapping of named pattern lists"),
        (
            "redact:\n  key_pattern: [dsn]\n",
            "a misspelled section would otherwise read as adding no patterns",
        ),
        ("redact:\n  key_patterns: dsn\n", "one pattern is still a list of one"),
        ("redact:\n  value_patterns: [42]\n", "a pattern is a string"),
    ],
)
def test_a_redact_section_that_cannot_be_honoured_as_written_is_refused(
    tmp_path: Path, text: str, because: str
):
    """A redaction rule silently dropped is the one refusal that costs a
    secret: the module looks exactly like one that never asked, and nothing
    downstream can tell the difference (D04 §2a's refusal, 2K design §1)."""
    try:
        read_redaction_rules(_config(tmp_path, text))
    except SextantConfigError:
        return
    pytest.fail(f"honoured a `redact:` it cannot honour as written — {because}")


def test_a_misspelled_top_level_key_is_refused_by_the_redaction_reader_too(tmp_path: Path):
    """Both readers share the file's own checks, so whichever command opens it
    first reports the typo — a `redact:` section under a root key nobody reads
    is not a section that runs."""
    with pytest.raises(SextantConfigError):
        read_redaction_rules(_config(tmp_path, "redactions:\n  key_patterns: [dsn]\n"))
