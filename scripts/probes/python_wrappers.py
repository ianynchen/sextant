"""CP-wrappers: what the library decorators `value-models/python-wrappers.yml` states do with
the function they are given, read off their own source (design
2026-11-06-reading-decorators §3e).

Run with the interpreter whose environment holds tenacity, isolated:

    .venv/bin/python -I scripts/probes/python_wrappers.py

It prints the Python version the interpreter REPORTS (`sys.version_info`, the version of
the standard library read) and the tenacity version its distribution reports
(`importlib.metadata`), then checks each rule against the source of the function that
implements it (`inspect.getsource`): a rule whose source text is missing aborts the run, so
the table it prints holds only rules that were read. The output is the observation table of
`scripts/probes/python_wrappers.md`, pasted as printed.
"""

import contextlib
import functools
import inspect
import sys
from importlib import metadata

import tenacity

# (rule, function, the source text that states it)
RULES = (
    (
        "`wraps(wrapped)` returns `update_wrapper` with the wrapper still to come",
        functools.wraps,
        "return partial(update_wrapper, wrapped=wrapped,",
    ),
    (
        "`update_wrapper` returns the wrapper it was given",
        functools.update_wrapper,
        "return wrapper",
    ),
    (
        "`cache(f)` is `lru_cache(maxsize=None)(f)`",
        functools.cache,
        "return lru_cache(maxsize=None)(user_function)",
    ),
    (
        "`lru_cache(f)`: a callable first argument is the function",
        functools.lru_cache,
        "elif callable(maxsize) and isinstance(typed, bool):",
    ),
    (
        "`lru_cache(f)`: the wrapper of that function, returned at once",
        functools.lru_cache,
        "wrapper = _lru_cache_wrapper(user_function, maxsize, typed, _CacheInfo)\n        wrapper.cache_parameters = lambda : {'maxsize': maxsize, 'typed': typed}\n        return update_wrapper(wrapper, user_function)",
    ),
    (
        "`lru_cache(maxsize)`: a decorator, the function still to come",
        functools.lru_cache,
        "def decorating_function(user_function):",
    ),
    (
        "`contextmanager(func)`'s result, called, builds the manager with its arguments",
        contextlib.contextmanager,
        "return _GeneratorContextManager(func, args, kwds)",
    ),
    (
        "`asynccontextmanager(func)` likewise",
        contextlib.asynccontextmanager,
        "return _AsyncGeneratorContextManager(func, args, kwds)",
    ),
    (
        "the manager calls `func` with those arguments",
        contextlib._GeneratorContextManagerBase.__init__,
        "self.gen = func(*args, **kwds)",
    ),
    (
        "`retry(f)`: one callable argument is the function",
        tenacity.retry,
        "if len(dargs) == 1 and callable(dargs[0]):\n        return retry()(dargs[0])",
    ),
    (
        "`retry(...)` with options: a decorator, the function still to come",
        tenacity.retry,
        "def wrap(f: WrappedFn) -> WrappedFn:",
    ),
    (
        "the retrying wrapper calls `f` with its arguments",
        tenacity.BaseRetrying.wraps,
        "return copy(f, *args, **kw)",
    ),
)


def main() -> int:
    python = ".".join(str(part) for part in sys.version_info[:3])
    reported = metadata.version("tenacity")
    rows = []
    for rule, function, text in RULES:
        source = inspect.getsource(function)
        if text not in source:
            print(f"ABORT: {rule}: not in {function.__qualname__}", file=sys.stderr)
            return 1
        cells = ("—", "read") if function.__module__.startswith("tenacity") else ("read", "—")
        rows.append((rule, f"`{function.__module__}.{function.__qualname__}`", *cells))
    print(
        f"Python {python} (sys.version_info reports it); tenacity {reported} from {tenacity.__file__}"
    )
    print()
    # One column per library read: the standard library at the interpreter's version, tenacity
    # at its distribution's.
    print(f"| Rule | Read in | {python} | {reported} |")
    print("|---|---|---|---|")
    for rule, where, standard, retrying in rows:
        print(f"| {rule} | {where} | {standard} | {retrying} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
