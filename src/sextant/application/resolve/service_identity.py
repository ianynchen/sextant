"""The `service_identity` hand-off (2G design §6, 2O design §1b/§1c) —
`supertype_derived`/`injected_client`'s own gaps, filed to the 2K ledger.

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
    injected_client,
    supertype_derived,
)
from sextant.application.resolve.open_questions import record_open_questions

# `annotation_driven` is the third, and unlike the other two it is a style
# EVERY annotation catalog declares — its `gaps` is inert for all of them and
# answers only for a catalog carrying a `corroborates` block (2O design §1b,
# fix round 2's I-2), which is why membership here is by style, as for the
# others, rather than by an id this module would have to know.
_GAP_ENGINES = {
    "supertype_derived": supertype_derived.gaps,
    "injected_client": injected_client.gaps,
    "annotation_driven": annotation_driven.gaps,
}


def record_service_identity_gaps(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Files one `service_identity` row per unresolved match, across every
    loaded catalog naming one of the two styles above. A catalog
    `derive_endpoints` skipped for a missing capability re-reads the same
    empty facts here and finds nothing to file — no capability re-check
    needed, the same reasoning `resolve_format`/`bind_parse_calls` already
    rely on for their own unconditional reads."""
    rows = [
        row
        for catalog in catalogs
        if catalog.style in _GAP_ENGINES
        for row in _GAP_ENGINES[catalog.style](workspace, catalog)
    ]
    record_open_questions(workspace, rows)
