"""The engine `gaps` hand-off (2G design §6, 2O design §1b/§1c/§5) — an
engine's own unanswered matches, filed to the 2K ledger.

**Named for its first question kind, and it is no longer the only one.**
`supertype_derived`, `injected_client` and `annotation_driven` file
`service_identity`; `config_join` files `channel_destination` (2O design §5,
Task 9). The seam is the same for both and is the reason this module exists at
all — WHERE a `gaps` function may write — so a second kind rides it rather
than earning a second pass with the identical ordering constraint. The module
and its entry point keep their names: renaming them would touch every caller
and every test that pins the pipeline's order, and the docstrings say what
they carry.

**A separate pass, not written from inside `derive_endpoints`**
(`resolve/endpoints.py`): `open_questions` is reset once, in the pipeline,
AFTER `derive_endpoints` runs (`resolve/pipeline.py`) — the same
ledger-ownership discipline `bind_parse_calls`/`resolve_format` already
follow (`resolve/open_questions.py`'s own module docstring: more than one
pass writes this table, so the reset is owned by neither). A write from
inside an engine's own `run` would be erased by that later reset.

This module re-walks the SAME two engines' own matching logic
(`supertype_derived.gaps`/`injected_client.gaps`) rather than reading it back
off `endpoints`: the row `derive_endpoints` wrote for the unresolved case
carries the SUPERTYPE's/stub type's own bare descriptor as `path` and no
handler at all, which does not carry the flagged CLASS `open_questions.py`'s
own vocabulary for `service_identity` asks for (candidates: "the class symbol
and the reason") — only the matching walk itself still has that."""

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.engines import (
    annotation_driven,
    config_join,
    injected_client,
    supertype_derived,
)
from sextant.application.resolve.open_questions import record_open_questions

# `annotation_driven` is the third, and unlike the other two it is a style
# EVERY annotation catalog declares — its `gaps` is inert for all of them and
# answers only for a catalog carrying a `corroborates` block (2O design §1b,
# fix round 2's I-2), which is why membership here is by style, as for the
# others, rather than by an id this module would have to know.
#
# `config_join` is the fourth and the first to file a question of another kind
# (`channel_destination`, 2O design §5). Membership is by style there too, and
# its `gaps` is inert for every catalog of the style but the one shape that
# earns the question — a `binding.from: annotation_value` block, whose channel
# names configuration did not answer.
_GAP_ENGINES = {
    "supertype_derived": supertype_derived.gaps,
    "injected_client": injected_client.gaps,
    "annotation_driven": annotation_driven.gaps,
    "config_join": config_join.gaps,
}


def record_service_identity_gaps(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Files one question row per unresolved match, across every
    loaded catalog naming one of the four styles above — including a catalog
    `derive_endpoints` skipped for a missing capability, since nothing here
    re-checks `catalog.requires` the way `derive_endpoints` does (the same
    unconditional read `resolve_format`/`bind_parse_calls` already rely on).
    For `supertype_derived`/`injected_client` that costs nothing: their
    `gaps` re-walks the SAME facts `run` needed, so the capability that left
    `run` nothing to derive leaves `gaps` nothing to find either.
    `annotation_driven`'s corroboration `gaps` does not re-walk its own
    catalog's facts at all, though (its own docstring states why): it reads
    the FINISHED `annotations`/`endpoints` tables back, so it can and does
    file a real question when a class it flags was never claimed as a
    handler — including when that is because a DIFFERENT catalog naming the
    same protocol got skipped. `grpc-spring.yml`'s own `requires` is written
    exactly for this: it omits `superclass`, the capability that gates
    the core gRPC catalog's `supertype_derived` match, so a scan missing it skips
    that catalog without also skipping this corroboration — which holds only
    as long as `annotation_driven.gaps` keeps reading the finished tables
    instead of its own catalog's requirements; keying it to `catalog.requires`
    the way `run` is would silence the exact scans this exists to cover.
    `config_join`'s `gaps` is in the first group: it re-walks the annotation
    facts its own `run` reads, so an unmet capability or an undeclared
    dependency leaves it nothing to find."""
    rows = [
        row
        for catalog in catalogs
        if catalog.style in _GAP_ENGINES
        for row in _GAP_ENGINES[catalog.style](workspace, catalog)
    ]
    record_open_questions(workspace, rows)
