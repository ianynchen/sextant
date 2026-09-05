"""CP-9's fact-stream half (2O Task 7b Step 0) — see ../cp9_servlet_shapes.md.

Reads the fact files the extractor wrote for ONE build of the probe app and
prints one `<row>|<value>` record per fact-shape question CP-9 asks. `run.sh`
files each value under the container version that build's own process
reported, exactly as it files a status code.

The servlet API package is an argument rather than a constant because CP-9
claims a column for the `javax.servlet` spelling as well as the `jakarta` one,
and the annotation this looks for is named in whichever package that build
compiled against. `run.sh` passes the package the RUNNING container reported.

Nothing here interprets. Every value printed is a literal read out of the
fact stream — an annotation's own `args` JSON, a symbol's own `visibility`
string, a signature's own parameter symbols — so a row of the generated table
can be compared against the facts by eye. A question this cannot answer prints
`ABSENT`, never a guess: an absent fact is the answer CP-9 is asking for.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def web_servlet(api_package: str) -> str:
    """The address annotation's own symbol under the spelling that build used."""
    return api_package.replace(".", "/") + "/annotation/WebServlet#"


def facts(out: Path, class_name: str) -> list[dict]:
    path = out / "probe" / f"{class_name}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def bare(symbol: str | None) -> str:
    return "" if symbol is None else symbol.rsplit(" ", 1)[-1]


def annotation_args(out: Path, class_name: str, annotation: str) -> str:
    for fact in facts(out, class_name):
        if fact["kind"] == "annotation" and fact["use"]["annotation"] == annotation:
            return json.dumps(fact["use"].get("args", {}), sort_keys=True)
    return "ABSENT"


def annotation_target_kind(out: Path, class_name: str, annotation: str) -> str:
    """Whether the `@WebServlet` fact's own target is the TYPE symbol or a
    member of it — the whole of "does the address reach us at type level"."""
    class_symbol = next(
        (
            fact["symbol"]
            for fact in facts(out, class_name)
            if fact["kind"] == "symbol" and fact["construct_kind"] == "class"
        ),
        None,
    )
    for fact in facts(out, class_name):
        if fact["kind"] == "annotation" and fact["use"]["annotation"] == annotation:
            return "TYPE" if fact["target"] == class_symbol else f"MEMBER {bare(fact['target'])}"
    return "ABSENT"


def method(out: Path, class_name: str, name: str) -> dict | None:
    for fact in facts(out, class_name):
        if fact["kind"] != "symbol" or fact.get("construct_kind") != "method":
            continue
        if bare(fact["symbol"]).rpartition("#")[2].partition("(")[0] == name:
            return fact
    return None


def visibility(out: Path, class_name: str, name: str) -> str:
    found = method(out, class_name, name)
    return "ABSENT" if found is None else found["visibility"]


def parameter_types(out: Path, class_name: str, name: str) -> str:
    found = method(out, class_name, name)
    if found is None or found.get("signature") is None:
        return "ABSENT"
    return ", ".join(
        (parameter.get("type") or {}).get("symbol", "?")
        for parameter in found["signature"].get("parameters", [])
    )


def superclass(out: Path, class_name: str) -> str:
    for fact in facts(out, class_name):
        if fact["kind"] == "symbol" and fact["construct_kind"] == "class":
            return bare(fact.get("superclass")) or "ABSENT"
    return "ABSENT"


def main() -> None:
    out = Path(sys.argv[1])
    annotation = web_servlet(sys.argv[2])
    for row, value in (
        (20, annotation_target_kind(out, "MultiPatternServlet", annotation)),
        (21, annotation_args(out, "MultiPatternServlet", annotation)),
        (22, annotation_args(out, "AliasedServlet", annotation)),
        (23, annotation_args(out, "VerbsServlet", annotation)),
        (24, visibility(out, "GetOnlyServlet", "doGet")),
        (25, parameter_types(out, "GetOnlyServlet", "doGet")),
        (26, parameter_types(out, "DecoyOverloadServlet", "doGet")),
        (27, superclass(out, "GetOnlyServlet")),
        (28, superclass(out, "GenericProbeServlet")),
        (29, annotation_args(out, "UnannotatedServlet", annotation)),
    ):
        print(f"{row}|{value}")


if __name__ == "__main__":
    main()
