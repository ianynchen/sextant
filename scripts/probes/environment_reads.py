"""Pin what a read of the process environment returns (plan 3, Task 3; ruling N1).

Run it with the interpreter of the environment being scanned:

    fixtures/orders-fastapi/.venv/bin/python -I scripts/probes/environment_reads.py

Every rule is asserted, then printed. The key is read from the real environment, so the
verdicts are the interpreter's own; Sextant itself never runs it (spec 7). Rules and the typeshed
symbols are in `environment_reads.md`.
"""

from __future__ import annotations

import os
import platform

KEY = "SEXTANT_PROBE_ABSENT_KEY"
os.environ.pop(KEY, None)
print(f"python {platform.python_version()}")


def rule(text: str) -> None:
    print(f"RULE: {text}")


assert type(os.environ).__name__ == "_Environ" and type(os.environ).__module__ == "os"
assert "__getitem__" in vars(type(os.environ)) and "get" not in vars(type(os.environ))
rule(
    "`os.environ` is an `os._Environ`; `__getitem__` is its own, `get` is inherited from `Mapping` (typeshed declares both on `_Environ`)"
)
assert os.getenv.__module__ == "os"
rule("`os.getenv` is a function of module `os`")

assert os.getenv(KEY) is None
assert os.getenv(KEY, "d") == "d" and os.getenv(key=KEY, default="d") == "d"
assert os.environ.get(KEY) is None and os.environ.get(KEY, "d") == "d"
assert os.environ.get(key=KEY, default="d") == "d"
rule(
    "an unset key gives the default, or None where none is given: the default is the code's, never the environment's"
)
try:
    os.environ[KEY]
    raise AssertionError
except KeyError:
    pass
rule("`os.environ[key]` of an unset key raises KeyError: it carries no default")

os.environ[KEY] = "set"
assert (
    os.getenv(KEY, "d") == "set" and os.environ.get(KEY, "d") == "set" and os.environ[KEY] == "set"
)
assert (os.getenv(KEY) or "d") == "set"
rule("a set key gives its value whatever default the call carries")
os.environ[KEY] = ""
assert (os.getenv(KEY) or "d") == "d" and os.getenv(KEY, "d") == ""
rule(
    "`getenv(k) or d` and `getenv(k, d)` differ for an empty value: the `or` form falls back, the default form does not"
)

import inspect

assert list(inspect.signature(os.getenv).parameters) == ["key", "default"]
assert list(inspect.signature(os.environ.get).parameters) == ["key", "default"]
rule("`getenv` and `environ.get` take `key` then `default`, each by position or by keyword")
print("OK")
