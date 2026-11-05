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
the name — cited on the model (`bean-models/spring.yml`, CP-27 row 15). For such a
reference the qualifier and the name choose only among the candidates of its type: a bean
of the type or of a subtype of it (`dispatch.ancestry_of`), as the container does.

No rung answers, or a rung has two candidates, is `Unresolved`, and the two are told
apart: `ambiguous` is a rung that weighed candidates and could not choose, `none` is no
candidate at all.

**Cost** (GUIDELINES §8.7): the fold reads `method_declarations` and the shared
`annotation_index` once per load and per MODEL, keyed on the model's own contents rather
than on the catalog — so every catalog naming `spring` shares one fold — and the table a
caller holds is a view over it plus the caller's own channel names.

**Which recipe fills a container-filled parameter** (spec 2026-11-05 di-recipe-hop §2):
`injected_parameters` answers, for each parameter the container fills, the one recipe
(provider method) the container chooses for it, by that container's own rule (the model's
`injection`). It reads EVERY bean model, not one catalog's (D02 §1c), and is built once per
resolve. The value walk reads it.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.conditions import annotation_index
from sextant.application.resolve.dependencies import resolved_by_the_build_tool
from sextant.application.resolve.dispatch import dispatch_of
from sextant.domain.symbols import (
    bare_descriptor,
    member_name,
    method_name,
    names_a_type,
    type_descriptor,
)


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
    reason: str  # 'none' | 'ambiguous' | 'unread' (`UNREAD`: the one candidate's hierarchy
    # was not read, so whether it is a candidate at all is not known)
    # For `ambiguous`, the beans the rung that could not choose weighed, in fold order. Not
    # part of equality: the reason is the answer, the beans are what it was weighed over.
    candidates: tuple[BeanRef, ...] = field(default=(), compare=False)


@dataclass(frozen=True)
class ProvidedBy:
    """A container-filled parameter receives the value of this one recipe: `provider` is the
    recipe method's full symbol."""

    provider: str


@dataclass(frozen=True)
class Ambiguous:
    """Several recipes match the parameter in the module, and the container's choice between
    them is not in the module (another component, another environment). `candidates` are
    their full symbols, sorted."""

    candidates: tuple[str, ...]


@dataclass(frozen=True)
class NotProvided:
    """No recipe in the module matches the parameter: `reason` is `NO_RECIPE` or
    `UNREAD_TYPE`."""

    reason: str


Injection = ProvidedBy | Ambiguous | NotProvided

# No recipe in the module has the parameter's key (the recipe is in another module, or the
# container makes the value another way).
NO_RECIPE = "no_recipe"
# The parameter's declared type is absent or is a type variable, so it gives no key.
UNREAD_TYPE = "unread_type"


# `TypeLattice.assignable`'s three answers.
ASSIGNABLE = "assignable"
NOT_ASSIGNABLE = "not_assignable"
UNREAD = "unread"


class TypeLattice:
    """The module's type hierarchy, as the bean rungs read it: each type's direct supertypes
    (`dispatch.ancestry_of`), and which types were READ — scanned (the module, a reactor
    sibling, an opted-in library), or a dependency whose class-file header was read
    (`type_header`). A type outside both was not read: its supertypes are not known. `own`
    are the module's types and its siblings'; `resolved` whether the build tool answered the
    module's classpath, so every type a jar holds had its header read. The platform's root class is never a
    recorded supertype (D00 §5), so a walk ends at the last type that names one."""

    def __init__(
        self,
        ancestors: Mapping[str, Sequence[tuple[str, str, bool]]],
        scanned: frozenset[str],
        headers: frozenset[str],
        own: frozenset[str],
        resolved: bool,
    ) -> None:
        self._ancestors = ancestors
        self._read = scanned | headers
        self._own = own
        self._resolved = resolved
        self._answers: dict[tuple[str, str], str] = {}

    def is_read(self, bare: str) -> bool:
        """Whether this type's own place in the hierarchy was read."""
        return bare in self._read

    def assignable(self, child: str, declared: str) -> str:
        """Whether a value of `child` can be given where `declared` is asked for.
        `ASSIGNABLE` where the walk from `child` reaches `declared`. `NOT_ASSIGNABLE` where it
        does not and either every type on the walk was read, or no type the walk left unread
        can reach `declared`:
        - `declared` is the module's own or a sibling's: no dependency extends a type of the
          module that depends on it;
        - `declared` was read and the classpath was resolved: every type a jar holds then has
          its header, so a type with none is the platform's, and a platform type extends
          nothing in a jar or in the module.
        `UNREAD` otherwise: a type whose supertypes are not known may reach `declared`."""
        key = (child, declared)
        if key not in self._answers:
            self._answers[key] = self._walk(child, declared)
        return self._answers[key]

    def _walk(self, child: str, declared: str) -> str:
        seen: set[str] = set()
        pending = [child]
        unread = False
        while pending:
            current = pending.pop()
            if current == declared:
                return ASSIGNABLE
            if current in seen:
                continue
            seen.add(current)
            unread = unread or current not in self._read
            pending.extend(ancestor for ancestor, _, _ in self._ancestors.get(current, ()))
        if not unread or declared in self._own:
            return NOT_ASSIGNABLE
        if self._resolved and declared in self._read:
            return NOT_ASSIGNABLE
        return UNREAD


def type_lattice(workspace: Workspace) -> TypeLattice:
    """The module's `TypeLattice`, built once per load (GUIDELINES §8.7): the hierarchy
    `dispatch_of` already read, one read of the dependency headers and of the module's own
    types, and whether the build tool resolved the classpath."""
    return workspace.once(_lattice)


def _lattice(workspace: Workspace) -> TypeLattice:
    dispatch = workspace.once(dispatch_of)
    headers = frozenset(
        bare_descriptor(str(row["symbol"])) for row in workspace.query("type_headers")
    )
    own = frozenset(bare_descriptor(str(row["symbol"])) for row in workspace.query("own_types"))
    return TypeLattice(
        dispatch.ancestors,
        frozenset(dispatch.scanned),
        headers,
        own,
        resolved_by_the_build_tool(workspace),
    )


def erased_type_of(declared: Mapping[str, Any]) -> str | None:
    """A declared parameter's erased type as its signature entry spells it (the descriptor's
    class, else the declared type's symbol), or None where the entry names no type."""
    erased = declared.get("erased_symbol") or (declared.get("type") or {}).get("symbol")
    return str(erased) if erased else None


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
    model's channel types and the caller's own channel names. `lattice` is the module's
    type hierarchy, read to tell which beans are candidates of a parameter's type."""

    def __init__(
        self,
        declared: DeclaredBeans,
        channel_types: frozenset[str],
        known_channels: frozenset[str],
        lattice: TypeLattice,
    ) -> None:
        self._declared = declared
        self._channel_types = channel_types
        self._known_channels = known_channels
        self._lattice = lattice

    def kind_of(self, erased_type: str) -> str:
        """`channel` for one of the model's `channel_types`, else `other`."""
        return "channel" if erased_type in self._channel_types else "other"

    def bean_of(self, reference: Parameter) -> BeanRef | Unresolved:
        """The bean this injected parameter names, by the rungs of its kind."""
        is_channel = self.kind_of(reference.erased_type) == "channel"
        if is_channel:
            called = reference.qualifier if reference.qualifier is not None else reference.name
            if called is None:
                return Unresolved("none")
            return self._named_or_known(called, is_channel=True)
        # Every rung below weighs only the candidates of the parameter's type, as the
        # container does (`findAutowireCandidates`): a bean of the type or of a subtype of it.
        # `maybe` are beans whose hierarchy was not read to the end (`TypeLattice`).
        sure, maybe = self._candidates(reference.erased_type)
        if reference.qualifier is not None:
            # A qualifier naming a bean that is not assignable fails the container's start,
            # so a bean whose hierarchy was not read is kept here.
            return self._one_named(reference.qualifier, sure + maybe)
        weighed = sure + maybe
        if len(weighed) == 1:
            # One candidate whose hierarchy was not read: whether it is one is not known.
            return sure[0] if sure else Unresolved(UNREAD, weighed)
        # Several: the one marked primary is the container's choice before any name is
        # compared (CP-27 row 15 — `determinePrimaryCandidate` runs before
        # `matchesBeanName`), so a parameter named after the OTHER bean still gets the
        # primary; two marked primary fail the injection, and the name rung is not tried
        # for them either. A primary whose hierarchy was not read may not be a candidate.
        primaries = [bean for bean in weighed if bean.primary]
        if len(primaries) == 1 and primaries[0] in sure:
            return primaries[0]
        if primaries:
            return Unresolved("ambiguous", tuple(primaries))
        # The name rung is strict: only a bean known to be of the type.
        if reference.name is not None:
            named = self._one_named(reference.name, sure)
            if isinstance(named, BeanRef) or named.reason == "ambiguous":
                return named
        return Unresolved("ambiguous", weighed) if weighed else Unresolved("none")

    def bean_called(self, method_symbol: str) -> BeanRef | None:
        """The bean a DIRECT call to a declaring method names — `channel(ordersChannel())`
        inside another factory method — or None for a call to any other method."""
        return self._declared.by_method.get(method_symbol)

    def _named(self, name: str) -> BeanRef | Unresolved | None:
        found = self._declared.by_name.get(name)
        if found is None:
            return None
        return found[0] if len(found) == 1 else Unresolved("ambiguous", found)

    def _candidates(self, erased_type: str) -> tuple[tuple[BeanRef, ...], tuple[BeanRef, ...]]:
        """The declared beans of `erased_type` or of a subtype of it, in fold order: those
        known to be, and those whose hierarchy was not read to the end (`TypeLattice`)."""
        sure: list[BeanRef] = []
        maybe: list[BeanRef] = []
        for erased, beans in self._declared.by_type.items():
            verdict = self._lattice.assignable(erased, erased_type)
            if verdict == ASSIGNABLE:
                sure.extend(beans)
            elif verdict == UNREAD:
                maybe.extend(beans)
        return tuple(sure), tuple(maybe)

    @staticmethod
    def _one_named(name: str, beans: Sequence[BeanRef]) -> BeanRef | Unresolved:
        """The one bean of `beans` called `name`; `none` for no such bean."""
        found = tuple(bean for bean in beans if bean.name == name)
        if not found:
            return Unresolved("none")
        return found[0] if len(found) == 1 else Unresolved("ambiguous", found)

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
    erased = erased_type_of(declared)
    if erased is None:
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
    return BeanTable(
        declared_beans(workspace, model), channel_types, known_channels, type_lattice(workspace)
    )


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


def injected_parameters(
    workspace: Workspace,
    models: Mapping[str, Mapping[str, Any]],
    configured_by: Iterable[str] = (),
) -> Mapping[tuple[str, int], Injection]:
    """For each parameter the container fills, keyed `(method full symbol, index)`, the recipe
    the container chooses for it (spec 2026-11-05 di-recipe-hop §2). `models` are every bean
    model by id (`Catalog.bean_models`); a model with no `injection` declares no recipe.

    The container fills each parameter of a method that carries the model's
    `declaring_annotation` (a recipe's own parameters), and of a constructor that carries one
    of its `injecting_annotations`. The model's `injection` chooses the recipe:
    `exact_key` mirrors Dagger, `candidates` takes Spring's ladder (`bean_of`) unchanged.

    Two kinds of slot get NO entry, so the walk keeps its own reading of them:
    - a slot carrying one of `configured_by` (dotted annotation names: the catalogs'
      `field_sources.value_annotation`, Spring's `@Value`): the container fills it from
      configuration, not from a recipe;
    - under `candidates`, a slot whose declared type carries type arguments: Spring fills
      `List<T>` with every bean of `T`, and the ladder keys on the erasure, so its answer
      would be false (missing, never false: `annotation_driven.generic_parameter`).

    Built once per load through `Workspace.once`, keyed on the models' contents
    (GUIDELINES §8.7), and catalog-free: it reads facts only."""
    return workspace.once(
        _Injected(
            json.dumps(models, sort_keys=True),
            frozenset(type_descriptor(name) for name in configured_by),
        )
    )


def meta_annotated_types(workspace: Workspace, markers: frozenset[str]) -> frozenset[str]:
    """Every annotation type carrying one of `markers` as a class-level annotation: module
    types through their own annotation facts, library types (`@Named`) through the class-level
    annotations their type header recorded. One level, the marker on the type itself, which is
    where a qualifier is declared. Two reads per call: once per declaring catalog in the
    dispatch reader, once per resolve in `injected_parameters` (GUIDELINES §8.7)."""
    return frozenset(
        bare_descriptor(str(row["target"]))
        for query in ("annotations", "type_header_annotations")
        for row in workspace.query(query)
        if bare_descriptor(str(row["annotation"])) in markers
    )


# `injected_parameters`' key and builder in one, as `_Fold` below: the models as canonical
# JSON, so two equal mappings build one key and share the entry.
@dataclass(frozen=True)
class _Injected:
    models: str
    configured_by: frozenset[str]  # descriptor form

    def __call__(self, workspace: Workspace) -> dict[tuple[str, int], Injection]:
        index = annotation_index(workspace)
        declarations = {str(row["symbol"]): row for row in workspace.query("method_declarations")}
        constructors = {
            str(row["symbol"]): json.loads(str(row["signature"] or "{}")) or {}
            for row in workspace.query("constructor_declarations")
        }
        models = json.loads(self.models)
        found: dict[tuple[str, int], Injection] = {}
        # Sorted by id, so a method two models claim gets one answer in every run (NFR-1).
        for model_id in sorted(models):
            model = models[model_id]
            if model.get("injection") is None:
                continue
            declaring = type_descriptor(str(model["declaring_annotation"]))
            injecting = frozenset(
                type_descriptor(name) for name in model.get("injecting_annotations") or []
            )
            filled: dict[str, list[dict[str, Any]]] = {}
            for symbol, row in declarations.items():
                if any(annotation == declaring for annotation, _ in index.get(symbol, [])):
                    filled[symbol] = _parameters(row["signature"])
            for symbol, signature in constructors.items():
                if any(annotation in injecting for annotation, _ in index.get(symbol, [])):
                    filled[symbol] = _parameters(signature)
            if model["injection"] == "exact_key":
                choose = _ExactKey(workspace, model, index, declarations).recipe_for
            else:
                choose = _Ladder(workspace, model).recipe_for
            ladder = model["injection"] == "candidates"
            for method, parameters in sorted(filled.items()):
                for position, declared in enumerate(parameters):
                    configured = any(
                        bare_descriptor(str(use.get("annotation"))) in self.configured_by
                        for use in declared.get("annotations") or []
                    )
                    if configured or (ladder and (declared.get("type") or {}).get("arguments")):
                        continue
                    found.setdefault((method, position), choose(method, parameters, position))
        return found


class _ExactKey:
    """Dagger's rule (spec §2a): the key is the qualifier annotation with all of its
    attributes and the full type with its type arguments. An unqualified parameter matches
    an unqualified recipe only; there is no name rung and no primary. A recipe that adds to
    a collection (`multibinding_annotations`) is never a candidate for `T`. Dagger refuses
    two recipes of one key on one component, but Sextant sees the whole module, not the
    component: one recipe is the answer, several are `Ambiguous`. "The module" is what the
    analysis read: the module's own classes and the reactor siblings it depends on, which
    the detector scans as library roots (Maven W24, Gradle W55), so a sibling's recipe is
    read and uniqueness is decided over the module and those siblings together. A recipe in
    a jar the analysis does not scan is not read (`NO_RECIPE`).

    Whether an annotation is a qualifier is read off its type. Where that type was not read
    (`TypeLattice.is_read`) and no read qualifier is beside it, the key is not known: the slot
    is `UNREAD_TYPE`, and so is every unqualified slot of a type that has such a recipe."""

    def __init__(
        self,
        workspace: Workspace,
        model: Mapping[str, Any],
        index: Mapping[str, list[tuple[str, dict[str, Any]]]],
        declarations: Mapping[str, Mapping[str, Any]],
    ) -> None:
        self._workspace = workspace
        self._declarations = declarations
        self._qualifiers = meta_annotated_types(
            workspace,
            frozenset(type_descriptor(name) for name in model["qualifier_meta_annotations"]),
        )
        declaring = type_descriptor(str(model["declaring_annotation"]))
        multibinding = frozenset(
            type_descriptor(name) for name in model.get("multibinding_annotations") or []
        )
        self._lattice = type_lattice(workspace)
        self._recipes: dict[tuple[Any, Any], list[str]] = {}
        # The types with an unqualified recipe that may yet be qualified (`_unread_qualifier`).
        self._unsure: set[Any] = set()
        for symbol, row in declarations.items():
            uses = index.get(symbol, [])
            names = {annotation for annotation, _ in uses}
            if declaring not in names or names & multibinding:
                continue
            signature = row["signature"] if isinstance(row["signature"], dict) else {}
            returned = _type_key(signature.get("returns"))
            if returned is not None:
                key = (self._qualifier_key(uses), returned)
                self._recipes.setdefault(key, []).append(symbol)
                if not key[0] and self._unread_qualifier(
                    [use for use in uses if use[0] != declaring]
                ):
                    self._unsure.add(returned)
        self._type_enclosing: dict[str, str] | None = None

    def recipe_for(
        self, method: str, parameters: Sequence[Mapping[str, Any]], position: int
    ) -> Injection:
        declared = parameters[position]
        declared_type = _type_key(declared.get("type"))
        if declared_type is None:
            return NotProvided(UNREAD_TYPE)
        uses = [
            (str(use.get("annotation")), dict(use.get("args") or {}))
            for use in declared.get("annotations") or []
        ]
        qualifier = self._qualifier_key(uses)
        if not qualifier and (self._unread_qualifier(uses) or declared_type in self._unsure):
            return NotProvided(UNREAD_TYPE)
        candidates = self._one_per_recipe(self._recipes.get((qualifier, declared_type), []))
        if not candidates:
            return NotProvided(NO_RECIPE)
        if len(candidates) == 1:
            return ProvidedBy(candidates[0])
        return Ambiguous(tuple(sorted(candidates)))

    def _qualifier_key(self, uses: Sequence[tuple[str, dict[str, Any]]]) -> tuple[str, ...]:
        """The qualifier annotations among `uses`, each with all of its attributes, as one
        comparable value: empty for an unqualified slot."""
        return tuple(
            sorted(
                bare_descriptor(annotation) + json.dumps(args, sort_keys=True)
                for annotation, args in uses
                if bare_descriptor(annotation) in self._qualifiers
            )
        )

    def _unread_qualifier(self, uses: Sequence[tuple[str, dict[str, Any]]]) -> bool:
        """Whether `uses` carry an annotation whose type was not read, so whether it is a
        qualifier is not known. Asked only where no read qualifier is among them: Dagger
        refuses two qualifiers on one binding, so beside a read one it is not a qualifier."""
        return any(not self._lattice.is_read(bare_descriptor(annotation)) for annotation, _ in uses)

    def _one_per_recipe(self, candidates: list[str]) -> list[str]:
        """`candidates` less the second method of one recipe. A compiler can emit one recipe of
        a nested object (a companion) as two methods with the declaring annotation: the
        object's own instance method, and a static method of the same name and descriptor on
        the enclosing type that forwards to it. The container makes one recipe of the two and
        calls the static one (measured on the OI-304 probe with Dagger 2.57.2: the component
        calls the enclosing module's factory). So the instance method is dropped where the
        enclosing type of its own type declares that static twin."""
        if len(candidates) < 2:
            return candidates
        if self._type_enclosing is None:
            self._type_enclosing = {
                str(row["symbol"]): str(row["enclosing"])
                for row in self._workspace.query("located_symbols")
                if row["enclosing"] is not None
            }
        statics = {
            (str(self._declarations[symbol]["enclosing"]), _member(symbol))
            for symbol in candidates
            if _modifier(self._declarations[symbol], "static")
        }
        return [
            symbol
            for symbol in candidates
            if _modifier(self._declarations[symbol], "static")
            or (
                self._type_enclosing.get(str(self._declarations[symbol]["enclosing"])),
                _member(symbol),
            )
            not in statics
        ]


class _Ladder:
    """Spring's rule (spec §2b): the existing ladder, `bean_of`, unchanged. The fold's
    channel names are none: a channel the index knows is not a recipe."""

    def __init__(self, workspace: Workspace, model: Mapping[str, Any]) -> None:
        self._model = dict(model)
        self._declared = declared_beans(workspace, self._model)
        channel_types = frozenset(
            type_descriptor(name) for name in model.get("channel_types") or []
        )
        self._beans = BeanTable(self._declared, channel_types, frozenset(), type_lattice(workspace))

    def recipe_for(
        self, method: str, parameters: Sequence[Mapping[str, Any]], position: int
    ) -> Injection:
        answer = injected_bean(self._beans, method, parameters, position, self._model)
        if isinstance(answer, BeanRef):
            return NotProvided(NO_RECIPE) if answer.method is None else ProvidedBy(answer.method)
        if answer.reason == UNREAD:
            return NotProvided(UNREAD_TYPE)
        if answer.reason != "ambiguous":
            return NotProvided(NO_RECIPE)
        return Ambiguous(
            tuple(sorted(str(bean.method) for bean in answer.candidates if bean.method))
        )


def _parameters(signature: Any) -> list[dict[str, Any]]:
    return list((signature if isinstance(signature, dict) else {}).get("parameters") or [])


def _type_key(declared: Any) -> tuple[Any, ...] | None:
    """A declared type with its type arguments, recursively, as one comparable value; None
    where no type is declared or the type is a type variable (D00 §5a's `names_a_type`).
    Nullability is not part of it: the container does not key on it."""
    if not isinstance(declared, Mapping) or not declared.get("symbol"):
        return None
    symbol = str(declared["symbol"])
    if not names_a_type(symbol):
        return None
    arguments = []
    for argument in declared.get("arguments") or []:
        key = _type_key(argument)
        if key is None:
            return None
        arguments.append(key)
    return (symbol, tuple(arguments))


def _member(symbol: str) -> str:
    """A method's name and descriptor without its type: the part two twins share."""
    return member_name(bare_descriptor(symbol))


def _modifier(row: Mapping[str, Any], name: str) -> bool:
    modifiers = row.get("modifiers")
    return isinstance(modifiers, dict) and bool(modifiers.get(name))


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
