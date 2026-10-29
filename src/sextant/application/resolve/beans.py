"""Bean identity (spec 2026-09-21 §3a): which declared factory method built the value an
injected parameter names. One fold per resolve over the annotation index and
`method_declarations`, driven by the catalog's bean model — the resolve layer names no
container. Consumed by fluent's `bean_via`; the field ladder's bean rung is a named follow-up.

**The rungs are per reference KIND, not one ladder** (spec §0b A2). A parameter whose
erased type is one of the model's `channel_types` is a CHANNEL reference: the qualifier,
else the parameter's own name — a declared bean's name or a channel name the channel index
already knows, because the container auto-creates a channel under a referenced name —
and never the type. The container itself sees more channel candidates than the module
declares (it registers its own error and null channels), so a fold that picked the
module's single channel bean by type would name a bean the container never injects. Any
OTHER reference (a container type no framework bean shares) takes the container's own
candidate order — the qualifier, else exactly one declared bean of that erased type, else
the one of several marked primary (two so marked fail the injection: `ambiguous`), else
the name — cited on the model (`bean-models/spring.yml`, CP-27 row 15).

No rung answers, or a rung has two candidates, is `Unresolved`, and the two are told
apart: `ambiguous` is a rung that weighed candidates and could not choose, `none` is no
candidate at all.

**Cost** (GUIDELINES §8.7): the fold reads `method_declarations` and the shared
`annotation_index` once per load and per MODEL, keyed on the model's own contents rather
than on the catalog — so every catalog naming `spring` shares one fold — and the table a
caller holds is a view over it plus the caller's own channel names.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.conditions import annotation_index
from sextant.domain.symbols import bare_descriptor, method_name, names_a_type, type_descriptor


@dataclass(frozen=True)
class BeanRef:
    """A resolved bean. `method` is the declaring method's full symbol, or None for a
    channel the index knows but no method declares — its name is then its whole
    identity; `erased_return` is the declaring method's erased return type, None where
    there is no method or the method returns a type variable; `primary` whether the
    declaring method carries the model's `primary_annotation` (final fix wave, item 1)."""

    method: str | None
    name: str
    erased_return: str | None
    primary: bool = False


@dataclass(frozen=True)
class Unresolved:
    reason: str  # 'none' | 'ambiguous'


@dataclass(frozen=True)
class Parameter:
    """An injected parameter as the caller reads it off a declared signature: the
    method's full symbol and the slot, the slot's erased type, its declared name (None
    for a method compiled without parameter names — the name rung is then skipped) and
    the qualifier `qualifier_of` read off its annotations."""

    method: str
    index: int
    erased_type: str
    name: str | None
    qualifier: str | None


@dataclass(frozen=True)
class DeclaredBeans:
    """The fold's product: every declared factory method of the module, by the full
    symbol a direct call names, by bean name and by erased return type. A name or a
    type with two declarations keeps both — the rung that reads it is what says
    `ambiguous`, in the order `method_declarations` reads them (by symbol, NFR-1)."""

    by_method: dict[str, BeanRef]
    by_name: dict[str, tuple[BeanRef, ...]]
    by_type: dict[str, tuple[BeanRef, ...]]


class BeanTable:
    """`bean_table`'s answer: the declared beans under one model, read through that
    model's channel types and the caller's own channel names."""

    def __init__(
        self, declared: DeclaredBeans, channel_types: frozenset[str], known_channels: frozenset[str]
    ) -> None:
        self._declared = declared
        self._channel_types = channel_types
        self._known_channels = known_channels

    def kind_of(self, erased_type: str) -> str:
        """`channel` for one of the model's `channel_types`, else `other`."""
        return "channel" if erased_type in self._channel_types else "other"

    def bean_of(self, reference: Parameter) -> BeanRef | Unresolved:
        """The bean this injected parameter names, by the rungs of its kind."""
        is_channel = self.kind_of(reference.erased_type) == "channel"
        if reference.qualifier is not None:
            return self._named_or_known(reference.qualifier, is_channel)
        if is_channel:
            if reference.name is None:
                return Unresolved("none")
            return self._named_or_known(reference.name, is_channel=True)
        by_type = self._declared.by_type.get(reference.erased_type, ())
        if len(by_type) == 1:
            return by_type[0]
        # Several of the type: the one marked primary is the container's choice before
        # any name is compared (CP-27 row 15 — `determinePrimaryCandidate` runs before
        # `matchesBeanName`), so a parameter named after the OTHER bean still gets the
        # primary; two marked primary fail the injection, and the name rung is not
        # tried for them either.
        primaries = [bean for bean in by_type if bean.primary]
        if len(primaries) == 1:
            return primaries[0]
        if len(primaries) > 1:
            return Unresolved("ambiguous")
        # The name rung reads every declared bean, not only the type candidates: the
        # fold carries no type hierarchy, so a parameter declared as a supertype of
        # the bean's erased return has no type candidate at all, and its name is the
        # one rung left to it. That holds as long as the fold stays hierarchy-free;
        # with one, this narrows to the candidates the way the container's does.
        if reference.name is not None and (named := self._named(reference.name)) is not None:
            return named
        return Unresolved("ambiguous" if len(by_type) > 1 else "none")

    def bean_called(self, method_symbol: str) -> BeanRef | None:
        """The bean a DIRECT call to a declaring method names — `channel(ordersChannel())`
        inside another factory method — or None for a call to any other method."""
        return self._declared.by_method.get(method_symbol)

    def _named(self, name: str) -> BeanRef | Unresolved | None:
        found = self._declared.by_name.get(name)
        if found is None:
            return None
        return found[0] if len(found) == 1 else Unresolved("ambiguous")

    def _named_or_known(self, name: str, is_channel: bool) -> BeanRef | Unresolved:
        """A declared bean of that name, else — for a CHANNEL reference only — a channel
        the index knows under it. The container auto-creates a channel under a
        referenced name, never a container or any other type, so a qualifier on a
        non-channel parameter that names no declared bean is `none` even when a channel
        happens to share the name (fix round 1)."""
        named = self._named(name)
        if named is not None:
            return named
        if is_channel and name in self._known_channels:
            return BeanRef(method=None, name=name, erased_return=None)
        return Unresolved("none")


def injected_bean(
    beans: BeanTable,
    method: str,
    parameters: Sequence[Mapping[str, Any]],
    index: int,
    model: dict[str, Any],
) -> BeanRef | Unresolved:
    """The bean the container injects into parameter `index` of the factory method
    `method`, read off its declared signature (`declared_parameters_of`'s entries): the
    slot's erased type, its declared name and its qualifier, by `bean_of`'s rungs. `none`
    for a slot the signature does not have, or one whose type it does not name."""
    if index >= len(parameters):
        return Unresolved("none")
    declared = parameters[index]
    erased = declared.get("erased_symbol") or (declared.get("type") or {}).get("symbol")
    if not isinstance(erased, str):
        return Unresolved("none")
    name = declared.get("name")
    return beans.bean_of(
        Parameter(
            method=method,
            index=index,
            erased_type=erased,
            name=str(name) if isinstance(name, str) else None,
            qualifier=qualifier_of(list(declared.get("annotations") or []), model),
        )
    )


def known_channels(workspace: Workspace) -> frozenset[str]:
    """The names the channel index knows, read for the bean fold's name rung for a channel
    reference (§3a): the `read_by` end of the channel edge (spec 2026-09-21 §3b). The
    container auto-creates a channel under any referenced name, so a name a handler's
    annotation carries is a channel whether or not a factory method declares it. Only a
    RESOLVED reader's name counts: one still spelled as a placeholder configuration never
    answered names nothing. The rows are there when the chain walk runs because
    `resolve/endpoints.py` runs the index's catalog first (`_writes_only_the_channel_edge`).
    Moved verbatim from `engines/fluent.py` with the walk that reads it."""
    return frozenset(
        str(row["channel"])
        for row in workspace.query("channel_bindings")
        if row["role"] == "read_by" and row["resolution"] == "resolved"
    )


def bean_table(workspace: Workspace, catalog: Catalog, known_channels: frozenset[str]) -> BeanTable:
    """The declared beans of the module under `catalog`'s bean model, plus
    `known_channels` — the channel names the caller's own index holds (the chain walk hands
    it the `channel_bindings` readers, `known_channels` above, spec §3b), which a channel
    reference may resolve to without any method declaring them.

    Refuses a catalog naming no `bean_model`, by file: a `bean_via` capture on such a
    catalog would resolve nothing and say nothing.
    """
    model = catalog.bean_model
    if not model:
        raise CatalogError(
            f"catalog {catalog.source}: resolves bean references but names no `bean_model` "
            f"(D02 §1c)"
        )
    where = f"bean model {model.get('id')!r} (catalog {catalog.source})"
    channel_types = frozenset(
        type_descriptor(name) for name in _strings(model, "channel_types", where)
    )
    return BeanTable(declared_beans(workspace, model), channel_types, known_channels)


def declared_beans(workspace: Workspace, model: dict[str, Any]) -> DeclaredBeans:
    """The fold: every method carrying the model's declaring annotation, once per load
    and per model. Keyed through `Workspace.once` on the model's CONTENTS — the
    declaring annotation, the name attributes and the primary annotation are all the
    fold reads — so two catalogs naming the same model share one entry."""
    where = f"bean model {model.get('id')!r}"
    return workspace.once(
        _Fold(
            declaring=type_descriptor(_string(model, "declaring_annotation", where)),
            name_attrs=_strings(model, "name_attrs", where),
            primary=type_descriptor(_string(model, "primary_annotation", where)),
        )
    )


def qualifier_of(annotations: list[Any], model: dict[str, Any]) -> str | None:
    """The bean name a parameter's own annotations qualify it with, or None. `annotations`
    is the decoded `signature.parameters[].annotations` list — `{annotation, args}` dicts
    in descriptor form. The name is read off the `value` attribute, as a string or the
    first element of an array: the one attribute the qualifier annotation declares (spec
    §0a F8; CP-27 row 14). That spelling stays here rather than in the
    model as long as every model's qualifier names its bean in `value`; a container
    whose qualifier spells it otherwise adds a `qualifier_attrs` key beside
    `name_attrs`, read here the same way."""
    where = f"bean model {model.get('id')!r}"
    qualifier = type_descriptor(_string(model, "qualifier_annotation", where))
    for use in annotations:
        if use.get("annotation") == qualifier:
            return _first_string(use.get("args") or {}, ("value",))
    return None


# The fold's key and builder in one: `Workspace.once` keys on the callable, and a
# module-level function would be one entry for every model while a closure would be
# a fresh entry per call. A frozen dataclass compares and hashes by its fields, so two
# catalogs naming the same model build the same key and share the entry.
@dataclass(frozen=True)
class _Fold:
    declaring: str  # descriptor form, the grammar `annotation_index` is keyed in
    name_attrs: tuple[str, ...]
    primary: str  # descriptor form likewise

    def __call__(self, workspace: Workspace) -> DeclaredBeans:
        index = annotation_index(workspace)
        by_method: dict[str, BeanRef] = {}
        by_name: dict[str, list[BeanRef]] = {}
        by_type: dict[str, list[BeanRef]] = {}
        for row in workspace.query("method_declarations"):
            symbol = str(row["symbol"])
            annotations = index.get(symbol, [])
            args = next(
                (args for annotation, args in annotations if annotation == self.declaring),
                None,
            )
            if args is None:
                continue
            signature = row["signature"] if isinstance(row["signature"], dict) else {}
            returned = (signature.get("returns") or {}).get("symbol")
            # A return naming a type VARIABLE is no type to index under (D00 §5a's
            # `names_a_type`): the bean is still declared, still named, still callable.
            erased_return = str(returned) if returned and names_a_type(str(returned)) else None
            name = _first_string(args, self.name_attrs) or method_name(bare_descriptor(symbol))
            bean = BeanRef(
                method=symbol,
                name=name,
                erased_return=erased_return,
                primary=any(annotation == self.primary for annotation, _ in annotations),
            )
            by_method[symbol] = bean
            by_name.setdefault(name, []).append(bean)
            if erased_return is not None:
                by_type.setdefault(erased_return, []).append(bean)
        return DeclaredBeans(
            by_method=by_method,
            by_name={name: tuple(beans) for name, beans in by_name.items()},
            by_type={erased: tuple(beans) for erased, beans in by_type.items()},
        )


def _first_string(args: dict[str, Any], names: tuple[str, ...]) -> str | None:
    """The first of `names` present in `args`, as the string it holds or the first
    element of the array it holds (D00 §5's literal model: an array attribute arrives
    as a list, a single string as itself). An empty array names nothing — the
    declaring annotation's default — so it falls through to the method's name."""
    for name in names:
        if name not in args:
            continue
        value = args[name]
        if isinstance(value, list):
            value = value[0] if value else None
        return value if isinstance(value, str) and value else None
    return None


def _string(model: dict[str, Any], key: str, where: str) -> str:
    value = model.get(key)
    if not isinstance(value, str) or not value:
        raise CatalogError(f"{where}: `{key}` must be one fully-qualified name — got {value!r}")
    return value


def _strings(model: dict[str, Any], key: str, where: str) -> tuple[str, ...]:
    value = model.get(key)
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise CatalogError(f"{where}: `{key}` must be a list of names — got {value!r}")
    return tuple(value)
