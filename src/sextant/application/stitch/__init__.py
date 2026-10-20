"""The stitcher (M06): match endpoints across the participants of one system.

**Matching is core computation, not an adapter** (M06, "Where the code lives"), so it lives
under `application/` and reaches every participant's graph only through the `Workspace`
port's federated views. No SQL here; no file reading; no framework names.

What this package answers, and what it deliberately does not, is the spec
`docs/superpowers/specs/2026-10-19-reactor-linking-design.md` and the seven decisions the
user settled on 2026-10-19. The short form, because a reader of this module should not have
to open the spec to know the shape:

* the participant set is a **reactor** — one build, every module its own participant;
* a link is built from protocol equality, then wire identity, then uniqueness (M06 steps 1,
  2 and 4). Step 3, structural compatibility, is specified and not built;
* **nothing above `name_match`**. Several survivors is `narrowed` with every candidate
  listed, never a pick; nothing matched is no link at all, and the document says so;
* an address whose AUTHORITY went unread is never matched by path alone.
"""

from sextant.application.stitch.links import Link, Unmatched, match
from sextant.application.stitch.participants import (
    Participant,
    participants_of,
    with_registered_names,
)

__all__ = [
    "Link",
    "Participant",
    "Unmatched",
    "match",
    "participants_of",
    "with_registered_names",
]
