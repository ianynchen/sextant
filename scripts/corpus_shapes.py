"""How many calls a module makes onto a method declared on a SCANNED ancestor
(F3 §4.2, W21) — the shape Wave 3's method resolution has to answer for.

One definition, in one place, because W21's review found the first attempt wrong in
BOTH directions and two copies of it had to be corrected together (§3's don't-repeat and
the reason: the counting rule is the part most likely to change).

## The shape

A call whose OWNER is a type this module scanned, naming a method that owner does not
declare but an ancestor it ALSO scanned does. Today such a call gets the single word we
have for "the body is not here" — the same word a genuinely external library call gets.
Separating those two is what F3 §4.2 is for, and this counts the calls that separation
will move.

## Two wrong rules, and why each was wrong

The first version approximated both halves by NAME, and both approximations failed:

* **The owner test was "this owner declares at least one method of its own."** A
  subclass that declares NOTHING was dropped — which is the purest form of the shape.
  `PetType` and `Specialty` in `spring-petclinic-rest` each declare only a default
  constructor and inherit everything, and 35 of the corpus's calls land on them. The
  count came out **96** — the figure F3 §4.2 itself recorded — where the answer is
  **131**, understating Wave 3's payoff by 27%. The owner test is now membership in
  `declared_symbols`: was this type scanned.

* **The ancestor test was "some OTHER scanned type declares a method of this name."**
  That matches by name alone, which §8.1 forbids as weaker than name-plus-arity — and it
  over-counted exactly as you would expect. `mall-admin`'s `SmsCouponParam` extends
  `SmsCoupon`, which lives in a different module and is NOT scanned; the rule matched
  `getId`/`setId` against two unrelated classes that happen to declare those names, and
  reported 5 resolvable calls where there are **none**. The design said mall-admin scores
  0 and it was right; the "correction" was the error. The ancestor test now walks the
  scanned superclass and interface closure and matches name AND descriptor, which is
  what JVMS 5.4.3.3 resolution does.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from sextant.application.ports.scanner import ScanRequest
from sextant.domain.symbols import bare_descriptor, method_descriptor, owner_of
from sextant.ingress.extract.jvm.scanner import AsmScanner
from sextant.resources import extractor_jar
from sextant.storage.duckdb.workspace import DuckDbWorkspace

# Methods a `new` compiles to. They live in `constructor_declarations`, not
# `method_declarations`, so the ancestor walk would already never match one — this is
# belt and braces, and stated as such rather than as the reason. (An earlier note here
# claimed the exclusion was load-bearing; removing it changes no count.) A constructor
# is not an inherited call in any case: JVMS 5.4.3.3 does not walk supertypes for one.
_NOT_A_METHOD = ("<init>", "<clinit>")


def resolvable_superclass_calls(classes: Path) -> list[str]:
    """`owner#name` for every call onto a method declared on a scanned ancestor.

    One entry per CALL SITE, not per distinct method: the number is "how many call
    sites does the resolution work answer for", and a method called nine times is nine
    boundary steps a reader currently cannot follow.
    """
    with tempfile.TemporaryDirectory() as into:
        facts = Path(into) / "facts"
        AsmScanner(extractor_jar()).scan(
            ScanRequest(
                module_id="corpus:shape",
                coordinates="corpus/shape",
                version="0",
                classes_dir=classes,
                out_dir=facts,
            )
        )
        workspace = DuckDbWorkspace(Path(into) / "ws.duckdb")
        workspace.load_facts(facts)
        found = _count(workspace)
        workspace.close()
    return found


def _count(workspace: DuckDbWorkspace) -> list[str]:
    scanned = {bare_descriptor(str(row["symbol"])) for row in workspace.query("declared_symbols")}

    # Every method symbol a scanned type declares, keyed by its owner. A DECLARATION
    # symbol spells its overload as `name(sig_HASH).` — the disambiguator D00 §5a
    # defines — not as a parameter list, so a call site is matched by rebuilding that
    # same symbol from its own `(owner, name, descriptor)` through the seam's
    # `method_descriptor`. That is an exact join on name AND descriptor, which is what
    # JVMS 5.4.3.3 resolves on; an earlier version compared method NAMES and reported
    # five resolvable calls in `mall-admin` that were unrelated classes sharing `getId`.
    declares: dict[str, set[str]] = {}
    for row in workspace.query("method_declarations"):
        bare = bare_descriptor(str(row["symbol"]))
        owner = owner_of(bare)
        if owner is not None:
            declares.setdefault(owner, set()).add(bare)

    parents: dict[str, list[str]] = {}
    for row in workspace.query("superclasses"):
        child = bare_descriptor(str(row["symbol"]))
        parents.setdefault(child, []).append(bare_descriptor(str(row["superclass"])))
    for row in workspace.query("supertypes"):
        child = bare_descriptor(str(row["symbol"]))
        declared = json.loads(str(row["supertype"]))
        symbol = declared.get("symbol") if isinstance(declared, dict) else None
        if symbol:
            parents.setdefault(child, []).append(bare_descriptor(str(symbol)))

    found: list[str] = []
    for row in workspace.query("call_sites"):
        owner, name = str(row["owner"]), str(row["name"])
        if name in _NOT_A_METHOD or owner not in scanned:
            continue
        wanted = method_descriptor(owner, name, str(row["descriptor"]))
        if wanted in declares.get(owner, ()):
            continue
        if _declared_by_an_ancestor(owner, wanted, parents, declares):
            found.append(f"{owner}{name}")
    return found


def _declared_by_an_ancestor(
    owner: str,
    wanted: str,
    parents: dict[str, list[str]],
    declares: dict[str, set[str]],
) -> bool:
    """Whether any SCANNED ancestor of `owner` declares this exact method.

    A breadth-first walk of the scanned closure — the shape JVMS 5.4.3.3 describes. The
    symbol is rebuilt per ancestor because a declaration symbol carries its OWN owner;
    an ancestor that was not scanned contributes nothing and is not an error, which is
    the honest "external boundary" answer this count exists to separate from
    "unresolved"."""
    member = wanted[len(owner) :]
    seen: set[str] = set()
    frontier = list(parents.get(owner, ()))
    while frontier:
        current = frontier.pop(0)
        if current in seen:
            continue
        seen.add(current)
        if current + member in declares.get(current, ()):
            return True
        frontier.extend(parents.get(current, ()))
    return False


# The counts this rule produces, recorded here because they are the reason the corpus
# was added and because two earlier rules produced different ones:
#
#   spring-petclinic-rest   131   every one a hand-written inherited accessor
#   fixtures/orders-service   2   `Customer#setId` / `#getId`, added by W21
#   mall-admin                0
#
# `orders-service` also makes 160 calls onto a scanned owner that owner does not
# declare, and only those 2 are resolvable. The other 158 are generated code extending
# LIBRARY supertypes — 101 protobuf (`OrderProtos$*`, `CommonProtos$*` over
# `GeneratedMessage`, and a `$Status` enum) and 57 Avro (`AuditEvent$Builder` over
# `SpecificRecordBuilderBase`) — where "the body is not here" is the correct answer
# rather than a defect. An earlier note here called all 158 Avro builders; a third of
# them are not builders at all.
