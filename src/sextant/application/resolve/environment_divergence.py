"""The `environment_divergence` hand-off (2G design §6's ledger, 2O design
§2b) — a derived route whose base path configuration answers differently per
environment.

**A separate pass, not written from inside `derive_endpoints`**, for the reason
`resolve/service_identity.py` states for its own three engines: `open_questions`
is reset once, in the pipeline, AFTER `derive_endpoints` runs, so a write from
inside an engine's `run` would be erased by that later reset.

**Why the question rather than a row per environment.** One repository is one
resource; a prefix that differs between environments does not make it two. The
row keeps the identity with its prefix left as the configuration EXPRESSION
(D02's own treatment of an address it cannot resolve), and this ledger carries
the per-environment values a human — or 2K's enrichment seat — can settle it
with. `config_join`'s cross-environment rule, applied by analogy exactly as the
design asks.
"""

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.dependencies import unmet_dependency
from sextant.application.resolve.engines import derived_resource
from sextant.application.resolve.open_questions import record_open_questions

# Keyed by STYLE, like `service_identity.py`'s own registry: which catalog ids
# exist is a property of the catalog directory, and a pass that named one would
# have to be edited every time a family gained a file.
_GAP_ENGINES = {"derived_resource": derived_resource.gaps}


def record_environment_divergence(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """Files one question per derived resource whose base path configuration
    did not settle on a single value.

    **The dependency gate is re-applied here**, unlike
    `resolve/service_identity.py`'s unconditional read, and the difference is
    not an inconsistency: that pass's engines match on evidence that NAMES
    their framework, so a skipped catalog finds nothing anyway, while this
    style's evidence is a repository interface that names no framework at all.
    Ungated, a module with no Spring Data REST on its build would file
    questions about the base path of an API it does not serve — the same
    fabrication the gate exists to prevent, one table over.
    """
    rows = [
        row
        for catalog in catalogs
        if catalog.style in _GAP_ENGINES and unmet_dependency(workspace, catalog) is None
        for row in _GAP_ENGINES[catalog.style](workspace, catalog)
    ]
    record_open_questions(workspace, rows)
