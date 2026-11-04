"""The init script's CONVENTION branch (OI-273 fix round 1, review m1), through a real Gradle 8.

A Kotlin plugin older than the source-set extension (1.6.21, measured on Gradle 8.14.1)
registers its `kotlin` source-directory set as a convention object, not an extension, and
Gradle 9 removed conventions altogether — so the branch can only be exercised on Gradle 8.
Downloading that plugin needs the network, so the build here registers the SAME shape itself:
a convention named `kotlin` whose `kotlin` property is a `SourceDirectorySet`, added to
`allSource` the way the old plugin did. No dependency and no plugin is resolved.

**Self-skipping, and never a download.** The Gradle 8.14.1 distribution is used only where
a wrapper has already unpacked it (`~/.gradle/wrapper/dists/gradle-8.14.1-all`), run as the
`gradle` on PATH; otherwise the test skips rather than fetch 200 MB mid-run. CI unpacks no
Gradle 8, so this runs on a developer machine and in the guard check there.
"""

import os
from pathlib import Path

import pytest

from sextant.ingress.detect.gradle import GradleDetector

_DISTRIBUTION = "gradle-8.14.1-all"

_BUILD = """\
plugins { id 'java' }

class KotlinConventionStub {
    final org.gradle.api.file.SourceDirectorySet kotlin
    KotlinConventionStub(org.gradle.api.file.SourceDirectorySet kotlin) { this.kotlin = kotlin }
}

def kotlinSet = objects.sourceDirectorySet("kotlin", "kotlin")
kotlinSet.srcDir("src/main/kotlin")
sourceSets.main.allSource.source(kotlinSet)
sourceSets.main.convention.plugins.put("kotlin", new KotlinConventionStub(kotlinSet))
"""


@pytest.mark.pins("detect.a-CONVENTION-registered-source-set-names-a-language")
def test_a_source_set_registered_as_a_convention_names_its_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    unpacked = Path.home() / ".gradle" / "wrapper" / "dists" / _DISTRIBUTION
    launchers = sorted(unpacked.glob("*/gradle-8.14.1/bin/gradle"))
    if not launchers:
        pytest.skip(
            f"{_DISTRIBUTION} is not unpacked on this machine; this test never downloads it"
        )
    # No wrapper in the project, so the detector takes `gradle` from PATH — this one.
    monkeypatch.setenv("PATH", f"{launchers[0].parent}{os.pathsep}{os.environ['PATH']}")
    project = tmp_path / "oldkt"
    (project / "src" / "main" / "kotlin" / "k").mkdir(parents=True)
    (project / "src" / "main" / "kotlin" / "k" / "Hello.kt").write_text("package k\n")
    (project / "settings.gradle").write_text("rootProject.name = 'oldkt'\n")
    (project / "build.gradle").write_text(_BUILD)

    module = GradleDetector().detect(project).modules[0]

    assert module.source_roots == (project / "src" / "main" / "kotlin",)
    assert module.languages == {"kotlin"}
