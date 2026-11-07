"""Time the Python read path over a source tree: read, parse and walk every file.

Usage: python -I scripts/probes/python_timing.py <path> [<path> ...]

The scanned code is parsed, never imported or run.
It prints the file count, the cold time, the warm time with a content-hash
cache, the call-site count, and the JVM resolver rate for comparison.
"""

import ast
import hashlib
import pathlib
import sys
import time

# Call sites per second of the JVM resolver. Measured on 2026-11-06:
# examples/mall/mall-admin, 25,057 call sites, cold `sextant module analyze`.
JVM_CALL_SITES = 25057
JVM_SECONDS = 6.14  # wall time of that run, from an empty .sextant directory


def walk_file(data: bytes) -> int:
    """Parse one file and visit every node once; return its call-site count."""
    try:
        tree = ast.parse(data)
    except (SyntaxError, ValueError):  # a file this Python cannot parse is not counted
        return 0
    return sum(1 for node in ast.walk(tree) if isinstance(node, ast.Call))


def scan(files: list[pathlib.Path], cache: dict[str, int] | None) -> tuple[float, int]:
    start = time.perf_counter()
    calls = 0
    for path in files:
        data = path.read_bytes()
        if cache is None:
            calls += walk_file(data)
            continue
        key = hashlib.sha256(data).hexdigest()
        if key not in cache:
            cache[key] = walk_file(data)
        calls += cache[key]
    return time.perf_counter() - start, calls


def main() -> None:
    for root in sys.argv[1:]:
        files = sorted(pathlib.Path(root).rglob("*.py"))
        cold, calls = scan(files, None)
        cache: dict[str, int] = {}
        scan(files, cache)  # fill the cache
        warm, _ = scan(files, cache)  # read and hash only
        print(f"{root}: files={len(files)} call_sites={calls}")
        print(f"  cold read+parse+walk: {cold:.2f} s ({calls / cold:,.0f} call sites/s)")
        print(f"  warm with content-hash cache: {warm:.2f} s")
    if JVM_SECONDS:
        print(f"JVM resolver: {JVM_CALL_SITES / JVM_SECONDS:,.0f} call sites/s")


if __name__ == "__main__":
    main()
