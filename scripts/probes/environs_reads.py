"""Pin how the `environs` library reads a key of the process environment (ruled 2026-11-26).

Run it inside the orders-django fixture's own environment, never Sextant's:

    fixtures/orders-django/.venv/bin/python -I scripts/probes/environs_reads.py

Every rule is asserted, then printed. Rules are in `environs_reads.md`.
"""

from __future__ import annotations

import importlib.metadata
import inspect
import os
import platform
import tempfile

import environs
from environs import Env, FileAwareEnv

METHODS = {
    "__call__": ("text", "text"),
    "str": ("text", "text"),
    "bool": ("true", True),
    "int": ("7", 7),
    "float": ("1.5", 1.5),
    "list": ("a,b", ["a", "b"]),
    "json": ('{"a": 1}', {"a": 1}),
}
DEFAULTS = {
    "__call__": "d",
    "str": "d",
    "bool": False,
    "int": 3,
    "float": 2.5,
    "list": ["z"],
    "json": {"z": 0},
}


def main() -> None:
    print(f"python {platform.python_version()}")
    print(f"environs {importlib.metadata.version('environs')}")

    assert issubclass(FileAwareEnv, Env) and FileAwareEnv is not Env
    print("FileAwareEnv is a subclass of Env")

    for owner in (Env, FileAwareEnv):
        env = owner()
        for method, (raw, parsed) in METHODS.items():
            read = getattr(env, method)
            # The method is a class attribute a factory made, not a `def` of the class.
            assert "_field2method" in vars(Env)[method].__qualname__
            names = list(inspect.signature(read).parameters)
            assert names[:2] == ["name", "default"], names
            os.environ.pop("PROBE_KEY", None)
            default = DEFAULTS[method]
            assert read("PROBE_KEY", default) == default
            assert read(name="PROBE_KEY", default=default) == default
            try:
                read("PROBE_KEY")
            except environs.EnvError:
                pass
            else:
                raise AssertionError("an unset key with no default must raise")
            os.environ["PROBE_KEY"] = raw
            assert read("PROBE_KEY") == parsed
            assert read("PROBE_KEY", default) == parsed
            os.environ.pop("PROBE_KEY")
            print(f"{owner.__name__}.{method}(name, default): the key, else the default")

    # FileAwareEnv: KEY_FILE names a file whose content is the value, read before KEY.
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as held:
        held.write("from-file")
    os.environ["PROBE_KEY"] = "from-env"
    os.environ["PROBE_KEY_FILE"] = held.name
    assert FileAwareEnv()("PROBE_KEY") == "from-file"
    assert Env()("PROBE_KEY") == "from-env"
    os.environ.pop("PROBE_KEY_FILE")
    assert FileAwareEnv()("PROBE_KEY") == "from-env"
    os.environ.pop("PROBE_KEY")
    os.unlink(held.name)
    print("FileAwareEnv: KEY_FILE, where set, names a file read before KEY; Env reads KEY alone")

    # A prefix changes the key that is read: not stated by the catalog entries.
    os.environ["APP_PROBE_KEY"] = "prefixed"
    env = Env()
    with env.prefixed("APP_"):
        assert env("PROBE_KEY") == "prefixed"
    os.environ.pop("APP_PROBE_KEY")
    print("Env.prefixed(p): the key read is p + name")


if __name__ == "__main__":
    main()
