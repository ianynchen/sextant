"""`.sextant.yml` — Sextant's OWN input, and the one place a malformed file is
refused rather than read as an honest absence (DR-6's exemption)."""

from pathlib import Path

import pytest

from sextant.ingress.detect.sextant_config import SextantConfigError, read_extract_libraries


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
            "extract_libraries: ['com.example:orders:1.0.0']\n",
            "a version is read from the build, never restated here",
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
    with pytest.raises(SextantConfigError):
        read_extract_libraries(_config(tmp_path, text)), because
