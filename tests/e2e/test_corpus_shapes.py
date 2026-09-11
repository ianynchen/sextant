"""The always-on corpus must contain the shapes the always-on suite is supposed to
catch (F3 §4.2, W21).

## Corpus blindness, stated precisely

Wave 3 fixes method resolution: a call whose OWNER is a class the module scans, naming a
method declared on an ancestor it ALSO scans, currently gets the one word we have for
"the body is not here" — the same word used for a genuinely external library call.
Measured on `spring-petclinic-rest` at its pinned commit, that shape occurs **131**
times — F3 §4.2 recorded 96, from a rule that dropped every subclass declaring no method
of its own.

`fixtures/orders-service` scored **zero** of them. It makes 160 calls whose owner it
scans and whose method that owner does not declare, but only the 2 W21 added are
resolvable: the rest are generated code extending LIBRARY supertypes — 101 protobuf and
57 Avro — where "external boundary" is the correct answer, not a defect. So the entire
always-on suite could pass, byte-stable and contracts-clean, while neither of Wave 3's
Criticals existed anywhere it could see them.

`scripts/field_check.py` reaches petclinic, but it is opt-in and network-using and is
never part of `scripts/check.sh` — so pinning the corpus there would have left the gate
exactly as blind. The shape is therefore modelled in the fixture as well, and this file
is what stops it silently returning to zero.

## What this asserts, and what it deliberately does not

It asserts the SHAPE EXISTS — that the fixture still contains a call the resolution work
has to answer for. It does not assert what the answer is: that belongs with W22's
`type_hierarchy`/`method_resolution`, and pinning today's wrong answer here would make
this file fail when the defect is fixed.
"""

import sys
from pathlib import Path

REPO = Path(__file__).parents[2]
# One definition of the shape, shared with `scripts/field_check.py` — W21's review found
# the first version wrong in both directions, and two copies would have had to be
# corrected together.
sys.path.insert(0, str(REPO / "scripts"))

from corpus_shapes import resolvable_superclass_calls

from fixture_build import compile_fixture

FIXTURE = REPO / "fixtures" / "orders-service"


def test_the_fixture_contains_a_call_declared_only_on_a_scanned_superclass():
    """The corpus property this file exists for.

    `Customer` extends `BaseEntity`; `setId` and `getId` are declared on the base and
    called with `Customer` as the owner — `spring-petclinic-rest`'s `Owner#setId` shape,
    which occurs there 131 times and occurred here zero times until W21.
    """
    compile_fixture(FIXTURE)

    found = set(resolvable_superclass_calls(FIXTURE / "target" / "classes"))

    assert found >= {
        "com/acme/orders/model/Customer#setId",
        "com/acme/orders/model/Customer#getId",
    }, (
        "the fixture no longer contains a call whose owner it scans and whose method is "
        "declared only on a scanned ancestor. That shape is what Wave 3's resolution work "
        "answers for, and without it the always-on suite cannot fail for the right "
        f"reason — it is how this went unnoticed before W21. Found: {sorted(found)}"
    )
