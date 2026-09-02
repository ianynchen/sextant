"""The one fixture-build step that cannot live beside the test that needs it.

`fixtures/orders-service` declares a dependency on `com.example:orders-soap-client`
(2I Task 6's opt-in library extraction), and Maven resolves every declared
dependency before it compiles anything — so the ~30 `mvn -o compile` calls
scattered through this suite all fail unless that artifact is in the local
repository first. Installing it is therefore a precondition of the suite, not of
one test, which is what makes it a session fixture here rather than a call in
each file. The build-and-install logic itself lives in `fixture_stub.py`,
because CI's priming step needs it before the suite exists.
"""

from pathlib import Path

import pytest

import fixture_stub


@pytest.fixture(scope="session", autouse=True)
def stub_library_in_the_local_repository() -> Path:
    """Built and installed once per session, and skipped entirely when it is
    already current — every test in this suite depends on it, including the ones
    that never touch Maven, so the up-to-date path must cost nothing."""
    jar = fixture_stub.local_repository_jar()
    if fixture_stub.is_current(jar):
        return jar
    return fixture_stub.compile_and_install(offline=True)
