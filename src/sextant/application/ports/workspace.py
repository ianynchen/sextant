"""The Workspace port (ARCHITECTURE §7). Its surface is deliberately narrow —
bulk load, the named derivations, the named queries of D01 — so that it cannot
decay into a SQL pass-through.

**The names stay strings.** D01 declares these sets, so an enum in `domain`
would put them under the same discipline as every other closed set and let
mypy reject a typo. Considered and declined: six values across eleven call
sites, and the failure it prevents — a mistyped name — raises immediately and
is caught by any test that exercises the path. The reading cost at every call
site outweighs it. Revisit if the sets grow or a second Workspace appears."""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol, TypeVar

from sextant.domain.redaction import Redactor

T = TypeVar("T")


class Workspace(Protocol):
    def load_facts(self, fact_root: Path) -> int:
        """Bulk-ingest every fact file under fact_root. Returns rows loaded."""

    def derive(self, name: str, **params: object) -> None:
        """Run one named derivation, rebuilding its tables whole. `params`
        are bound into the derivation's SQL by name — this is how a generic
        engine (D02) passes catalog data in without the SQL ever containing
        the catalog's literals."""

    def query(self, name: str, **params: object) -> list[dict[str, object]]:
        """Run one named query. Unknown names raise KeyError.

        The rows may be shared between calls — a query over facts alone is read once
        per load and the same list handed back after that — so a caller reads them and
        never writes into a row. A JSON column the storage names as decoded arrives as
        an object (a dict, a list, or `None`), not as text; every other JSON column is
        text and the caller decodes it."""

    def once(self, build: "Callable[[Workspace], T]") -> T:
        """The value `build(self)` returns, built once per load and handed back on every
        later call until the next `load_facts` — the same lifetime the shared rows of
        `query` have, for the same reason: `build` reads fact tables alone, so nothing
        between two loads can change its answer.

        Keyed by `build` itself, so a module-level builder is one entry and there is no
        name to collide on. The contract `build` keeps: it reads only queries over facts
        (a read of a derived table is refused, because a derivation may have run between
        the build and the next call), and what it returns is read by every consumer and
        written by none — the same discipline the rows of `query` ask.

        A structure that depends on no catalog is built here so that a resolve running
        thirty catalogs folds the same 25,000 rows into the same index once, not thirty
        times: GUIDELINES §8.7's "compute once, read many"."""

    def federate(self, participants: "Mapping[str, Path]") -> None:
        """Make every participant's own graph readable from THIS workspace, as views —
        `system_endpoints` and `system_config` — without copying any of it.

        `participants` maps the name a link is matched by to the workspace holding that
        participant's graph. [D01]'s system scope is the contract: the system workspace
        owns two native tables and reads everything else through views, so nothing here
        imports, and a participant unreachable at query time fails naming it rather than
        giving a shorter answer.

        **This is the second Workspace the module docstring above said to revisit on.** It
        is one method rather than a port of its own because the surface it needs is
        exactly this one: the matcher asks named queries, and the only thing it cannot do
        through the existing surface is say which graphs are in scope.

        Calling it again replaces the previous set, so one process may analyze two
        reactors. Participants whose graph is missing are simply not passed — the
        `participants` table records them as absent with a reason, which is where that
        fact belongs (M06 attributes an unmatched call into an absent participant to the
        gap rather than to the architecture).
        """

    def export_tables(self, destination: Path, redactor: Redactor) -> list[str]:
        """Write the bundle's graph tables as Parquet, one file per table.

        `redactor` masks on the way out (2K design §1) — the tables themselves
        stay verbatim, so the parameter is not optional: a bundle is written to
        leave, and an implementation with nowhere to put the rule set would be
        one that cannot say what it masked."""

    def export_facts(self, destination: Path, redactor: Redactor) -> int:
        """Write the raw facts as Parquet, one file per document.

        `redactor` masks on the way out, as `export_tables` does and for the
        same reason: everything the bundle carries leaves, so a masked graph
        table beside an unmasked fact file would mask nothing. The workspace's
        own fact rows stay verbatim."""

    def close(self) -> None: ...


class GraphReader(Protocol):
    """One side of a boundary comparison, opened to be read and never changed: a module's
    workspace or an exported bundle, answering the same named queries whichever it is (spec
    2026-10-22 §3a), and saying what it is.

    Narrower than `Workspace` on purpose — opening one runs no schema, derives nothing and
    loads nothing, so a diff of two analyses cannot alter either. The description is read off
    `metadata.json` (a workspace) or `manifest.json` (a bundle) by the adapter, because
    `application` reads no files."""

    @property
    def module(self) -> dict[str, object]:
        """The `module` block: `id`, `kind`, `languages`, `dependency_source`."""

    @property
    def commit(self) -> str: ...

    @property
    def producer(self) -> dict[str, object]:
        """The stamps this side carries, under the names the bundle manifest gives them; one
        it lacks is absent, not `None`."""

    @property
    def environments(self) -> list[str]: ...

    @property
    def is_bundle(self) -> bool: ...

    @property
    def module_root(self) -> "Path | None":
        """The directory above the workspace — the module, for the usual `<module>/.sextant`
        layout, where `.sextant.yml` lives; `None` for a bundle, which has none."""

    def query(self, name: str, **params: object) -> list[dict[str, object]]:
        """Run one named query, as `Workspace.query` does."""

    def close(self) -> None: ...
