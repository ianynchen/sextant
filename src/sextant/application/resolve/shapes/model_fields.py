"""A model field's names, read off the calls that make the field's value and the model's
configuration (D02 §2f; plan 2026-11-08-python-fastapi-inbound N12, N13; rulings R2, R3).

A shape model whose serialiser names a field by the CALL that made its class-body value
(`price: Decimal = Field(alias="Price")`) rather than by an annotation declares it in
`serialization`: `name_from` and `input_name_from` entries with a `call`, read in written
order, the first one written winning, `alias_priority`, `defaults`, `name_generator`,
`required: no_default` and `private_prefix`. Every rule is the serialiser's, quoted with
lines in `scripts/probes/pydantic_naming.md`; this module knows no serialiser by name.

**Each value is read through `values.producer_paths`**, the walk every reader takes, so a
helper returning the call and a module name holding it are followed; one producer read per
field with a class-body value, and one configuration fold per class, each kept for the pass.

- **The output name** is the first `name_from` entry written on the call, else the name the
  model's generator gives, else the field's name. **The input name** is the first
  `input_name_from` entry written, else the generator's, else the name. A literal
  `alias_priority` equal to `generator_wins` lets the generator replace both (R3).
- **The generator** is the class's configuration (`config_field`, made by a `config_call`)
  merged over its written bases, the last base winning, then the class's own (R2). A field
  takes the first generator set on its way from the model to the class declaring it, as
  pydantic keeps the alias a parent's generator gave an inherited field. A generator no
  `functions` entry names is not guessed at: the field's names are unresolved (§2g).
- **Resolution.** A field whose accepted input names differ from its output name is `partial`
  (N13 option B), as is one whose names the code does not let us read: an argument that is
  not a literal, an unpacked `**kwargs`, two paths that disagree, a configuration not read.
"""

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.dispatch import ancestry_of
from sextant.application.resolve.parameter_markers import _ANNOTATED, _site
from sextant.application.resolve.shapes.rooting import _catalog_symbol
from sextant.application.resolve.values import (
    EXTERNAL,
    RECEIVER,
    UNPACKED_SLOT,
    ValueIndex,
    argument_slot,
    held_at_end,
    producer_paths,
)
from sextant.domain.closed_sets import Resolution
from sextant.domain.symbols import bare_descriptor, owner_of

# The readers' keys in the index's shared upward paths (`producer_paths(..., shared=)`): one per
# stop set, since a path's end depends on it.
_VALUE_READER = "model_fields:value"
_CONFIG_READER = "model_fields:config"
_FORM_READER = "model_fields:form"
_OUTPUT_FIELD_READER = "model_fields:output_field"
_OUTPUT_OPEN_READER = "model_fields:output_open"
# The name the facts give a call of a value (`f(x)` on a value `f`, D00 §5): a decorator
# written as a call is applied by calling its result.
_CALL_OF_VALUE = "__call__"
# A default's state while the naming calls are merged (`ModelNames._required`).
_NONE_WRITTEN = "none_written"
_WRITTEN = "written"
_NOT_READ_DEFAULT = "not_read"
# A class body's own method (D00 §5a): the value a class-body annotation writes is made there.
_CLASS_BODY = "<clinit>("
# An argument written as something no literal reading answers.
_UNREAD = object()
# The one `required` rule (N12): a field is required when it writes no default.
NO_DEFAULT = "no_default"

_RESOLVED = str(Resolution.RESOLVED)
_PARTIAL = str(Resolution.PARTIAL)
_UNRESOLVED = str(Resolution.UNRESOLVED)
# The three a field's naming can reach, strongest first.
_STRENGTH = (_RESOLVED, _PARTIAL, _UNRESOLVED)


def weaker(one: str, other: str) -> str:
    """The weaker of two of a field's resolution words (`mounts.weaker`'s rule; that module
    cannot be imported from beside the expansion it reaches)."""
    return max(one, other, key=lambda word: _STRENGTH.index(word) if word in _STRENGTH else 1)


def _pascal(name: str) -> str:
    """pydantic 2.14's `alias_generators.to_pascal`, verbatim."""
    camel = name.title()
    return re.sub("([0-9A-Za-z])_(?=[0-9A-Z])", lambda m: m.group(1), camel)


def _camel(name: str) -> str:
    """pydantic 2.14's `alias_generators.to_camel`, verbatim."""
    if re.match("^[a-z]+[A-Za-z0-9]*$", name) and not re.search(r"\d[a-z]", name):
        return name
    return re.sub("(^_*[A-Z])", lambda m: m.group(1).lower(), _pascal(name))


# N12's two strategy words, each a generator function exactly. A `functions` entry naming
# another is refused by the loader.
STRATEGIES: dict[str, Callable[[str], str]] = {"camel": _camel, "pascal": _pascal}


@dataclass(frozen=True)
class Naming:
    """A shape model's call-read naming (module docstring), every dotted name converted.

    `name_from`/`input_name_from` are `(call, argument reference)` in written order; `defaults`
    `(call, default references, required_when reference, equals field symbol)`; `functions` a
    generator function's field symbol to its strategy word."""

    name_from: tuple[tuple[tuple[str, str], Any], ...]
    input_name_from: tuple[tuple[tuple[str, str], Any], ...]
    alias_priority: tuple[tuple[str, str], Any, int] | None
    defaults: tuple[tuple[tuple[str, str], tuple[Any, ...], Any, str | None], ...]
    config_field: str | None
    config_calls: frozenset[tuple[str, str]]
    generator_arg: Any
    by_name_args: tuple[Any, ...]
    functions: Mapping[str, str]
    required: str | None
    private_prefix: str | None
    # `excluded_when` (task 9 review M4, ruled 2026-11-09): the argument of a naming call, and
    # the literal it is written as, that drops the field from output. None where not declared.
    excluded_when: tuple[Any, Any] | None = None
    # `open_when` (task 9c, approved 2026-11-09): the configuration argument, and the literals
    # it may be written as, that let a model take keys no field declares. None where not
    # declared.
    open_when: tuple[Any, frozenset[str]] | None = None
    # `output_fields`: each decorator whose method is a field written on output and never read,
    # with the argument naming it and the one whose presence lets it be left out.
    output_fields: tuple[tuple[tuple[str, str], Any, Any], ...] = ()
    # `output_open_when`: the decorators whose method writes the output itself, and the methods
    # that build the schema (`(name, also_input, declared_by_default)`: whether the input is
    # built too, and the class whose own declaration is the default no one overrides).
    output_open_decorators: frozenset[tuple[str, str]] = frozenset()
    output_open_methods: tuple[tuple[str, bool, str | None], ...] = ()

    @property
    def calls(self) -> frozenset[tuple[str, str]]:
        """Every call a field's value is read at: the walk's stops."""
        return frozenset(
            [call for call, _ in self.name_from]
            + [call for call, _ in self.input_name_from]
            + [call for call, *_ in self.defaults]
            + ([self.alias_priority[0]] if self.alias_priority else [])
        )


def _call(dotted: str) -> tuple[str, str]:
    owner, _, method = dotted.rpartition(".")
    return (_catalog_symbol(owner), method)


def _function(dotted: str) -> str:
    """A module-level function's field symbol (D00 §5's `field` kind)."""
    owner, _, name = dotted.rpartition(".")
    return f"{_catalog_symbol(owner)}{name}."


def naming_of(serialization: Mapping[str, Any]) -> Naming | None:
    """The call-read naming a `serialization` block declares, None where it declares none, as
    every annotation-read model does (the loader checks each key's form)."""
    calls = [entry for entry in serialization.get("name_from", []) if "call" in entry]
    generator = serialization.get("name_generator") or {}
    if not (
        calls
        or generator
        or "required" in serialization
        or "private_prefix" in serialization
        or "input_name_from" in serialization
        or "excluded_when" in serialization
        or "open_when" in serialization
        or "output_fields" in serialization
        or "output_open_when" in serialization
    ):
        return None
    priority = serialization.get("alias_priority")
    excluded = serialization.get("excluded_when")
    opened = serialization.get("open_when")
    config_calls = generator.get("config_call", [])
    hooks = serialization.get("output_open_when", [])
    return Naming(
        name_from=tuple((_call(entry["call"]), entry["arg"]) for entry in calls),
        input_name_from=tuple(
            (_call(entry["call"]), entry["arg"])
            for entry in serialization.get("input_name_from", [])
        ),
        alias_priority=None
        if priority is None
        else (_call(priority["call"]), priority["arg"], int(priority["generator_wins"])),
        defaults=tuple(_defaults(entry) for entry in serialization.get("defaults", [])),
        config_field=generator.get("config_field"),
        config_calls=frozenset(
            _call(call)
            for call in ([config_calls] if isinstance(config_calls, str) else config_calls)
        ),
        generator_arg=generator.get("arg"),
        by_name_args=tuple(generator.get("by_name") or []),
        functions={
            _function(entry["function"]): str(entry["strategy"])
            for entry in generator.get("functions", [])
        },
        required=serialization.get("required"),
        private_prefix=serialization.get("private_prefix"),
        excluded_when=None
        if excluded is None
        else ({"keyword": excluded["keyword"]}, excluded["value"]),
        open_when=None
        if opened is None
        else (opened["arg"], frozenset(str(value) for value in opened["values"])),
        output_fields=tuple(
            (_call(entry["decorator"]), entry.get("name_from"), entry.get("absent_when"))
            for entry in serialization.get("output_fields", [])
        ),
        output_open_decorators=frozenset(
            _call(entry["decorator"]) for entry in hooks if "decorator" in entry
        ),
        output_open_methods=tuple(
            (
                str(entry["method"]),
                bool(entry.get("also_input", False)),
                _catalog_symbol(entry["except_declared_by"])
                if "except_declared_by" in entry
                else None,
            )
            for entry in hooks
            if "method" in entry
        ),
    )


def _defaults(entry: Mapping[str, Any]) -> tuple[tuple[str, str], tuple[Any, ...], Any, str | None]:
    """One `defaults` entry: its call, its default references, and its `required_when`
    reference with the field symbol that makes the call write none."""
    when = entry.get("required_when") or {}
    return (
        _call(entry["call"]),
        tuple(entry.get("default_arg") or []),
        when.get("arg"),
        _function(str(when["equals_field"])) if when else None,
    )


@dataclass(frozen=True)
class FieldName:
    """One field as the shape model names it: `output` its name on the wire out (None where it
    is not read), `input` the name a request is read under first (None likewise), `required`
    whether a request must carry it (None where the model has no `required` rule); `resolution`
    the field's (its output name, and
    N13's agreement of the input names with it), `input_resolution` the input name's alone."""

    output: str | None
    input: str | None
    required: bool | None
    resolution: str
    input_resolution: str
    # Whether an output option drops the field (`excluded_when`): None where that option is
    # written as no literal.
    excluded: bool | None = False


# A model's generator, as its configuration states it: none set, a known strategy word, a
# function no entry names, or a configuration not read.
_NONE = ("none",)
_UNKNOWN = ("unknown",)
_NOT_READ = ("not_read",)


@dataclass(frozen=True)
class _Config:
    """One class's configuration merged over its bases (R2): its generator, absent where no
    class on the way sets one, and whether a field is read under its name too (`by_name`,
    None where not read)."""

    generator: tuple[str, ...] | None
    by_name: bool | None
    # `open_when`'s argument: None where no class on the way writes it, True or False where
    # the last one writing it writes a listed literal or another, `_UNREAD` where it is not
    # read (task 9c).
    opened: Any = None


@dataclass
class ModelNames:
    """Every field name a shape model reads off calls, read on first ask and kept for the pass
    (module docstring). `index` is the walk's index (`values.cached_value_index`)."""

    workspace: Workspace
    naming: Naming
    index: ValueIndex
    _writes: dict[str, list[tuple[str, Mapping[str, Any]]]] | None = None
    _ancestry: dict[str, list[tuple[str, str, bool]]] | None = None
    _configs: dict[str, _Config] = field(default_factory=dict)
    _values: dict[str, list[Mapping[str, Any] | None] | None] = field(default_factory=dict)
    _bodies: dict[str, str] | None = None
    _headers: "dict[str, LibraryBody] | None" = None
    _methods: dict[str, dict[str, Any]] | None = None
    _decorations: dict[
        tuple[str, str, frozenset[tuple[str, str]]],
        tuple[Mapping[str, Any], Mapping[str, Any] | None] | None,
    ] = field(default_factory=dict)

    def is_private(self, name: str) -> bool:
        """Whether a declared name is no field at all (`private_prefix`)."""
        prefix = self.naming.private_prefix
        return bool(prefix) and name.startswith(str(prefix))

    def of(
        self, model: str, holder: str, name: str, annotation: Mapping[str, Any] | None = None
    ) -> FieldName:
        """Field `name`, declared by `holder`, as model `model` presents it. `annotation` is
        the field's annotation value where it is not a plain type (D00 §5a): the naming calls
        in its `Annotated` metadata are read before the class-body value's, as pydantic merges
        them (`FieldInfo.from_annotated_attribute`, `pydantic_naming.md` §5)."""
        generator = self._generator(model, holder)
        readings = [
            self._reading(
                name,
                [
                    *calls,
                    *(
                        [value]
                        if value is not None and _call_of(value) in self.naming.calls
                        else []
                    ),
                ],
                value,
                generator,
                model,
            )
            for calls in self._annotated(holder, name, annotation)
            for value in self._paths(f"{holder}{name}.")
        ]
        first = readings[0]
        if any(reading != first for reading in readings[1:]):
            agreed = all(one.excluded == first.excluded for one in readings)
            return FieldName(
                first.output,
                first.input,
                first.required,
                _PARTIAL,
                _PARTIAL,
                first.excluded if agreed else None,
            )
        return first

    def _reading(
        self,
        name: str,
        calls: list[Mapping[str, Any]],
        value: Mapping[str, Any] | None,
        generator: tuple[str, ...] | None,
        model: str,
    ) -> FieldName:
        """One path's reading: `calls` the naming calls that made the field's information in
        pydantic's merge order, each overriding what it writes; `value` where the class-body
        value ended (`_paths`)."""
        resolution = _PARTIAL if value is _VALUE_NOT_READ else _RESOLVED
        output: Any = None
        given: Any = None
        level: Any = None
        excluded: Any = None
        for site in calls:
            arguments = list(site.get("arguments") or [])
            if any(entry.get("keyword") in ("*", "**") for entry in arguments):
                # Names in an unpacked value (`Field(**kwargs)`) are not written here (R3).
                resolution = _PARTIAL
            call = _call_of(site)
            output = _merged(output, _first(arguments, call, self.naming.name_from))
            given = _merged(given, _first(arguments, call, self.naming.input_name_from))
            priority = self.naming.alias_priority
            if priority is not None and call == priority[0]:
                level = _merged(level, _literal(_argument(arguments, priority[1])))
            if self.naming.excluded_when is not None:
                excluded = _merged(
                    excluded, _literal(_argument(arguments, self.naming.excluded_when[0]))
                )
        generated: str | None = name
        if generator is not None and generator != _NONE:
            if generator[0] in STRATEGIES:
                generated = STRATEGIES[generator[0]](name)
            elif generator == _NOT_READ:
                resolution = weaker(resolution, _PARTIAL)
            else:
                generated = None
            priority = self.naming.alias_priority
            if level is _UNREAD:
                resolution = weaker(resolution, _PARTIAL)
            elif priority is not None and level == priority[2]:
                output = given = None
        output_name = _named(output, generated)
        input_name = None if given is _UNREAD else _named(given, generated)
        # What is read of each name alone: written as no literal, partial; not read at all (a
        # generator no entry names), unresolved.
        read_out = _UNRESOLVED if output_name is None and output is None else _RESOLVED
        if output is _UNREAD:
            read_out = _PARTIAL
        read_in = _UNRESOLVED if input_name is None and given is None else _RESOLVED
        if given is _UNREAD:
            read_in = _PARTIAL
        accepted = {input_name}
        by_name = self._config(model).by_name
        if input_name != name:
            if by_name is None:
                read_in = weaker(read_in, _PARTIAL)
            elif by_name:
                accepted.add(name)
        if len(accepted) > 1:
            read_in = weaker(read_in, _PARTIAL)
        required = self._required(calls, value)
        if required is None and self.naming.required == NO_DEFAULT:
            # Whether a default is written is not read (review M2): `required` is unknown.
            resolution = weaker(resolution, _PARTIAL)
        # N13 B: a field read under names other than its output name is not wholly described
        # by that name.
        whole = weaker(resolution, weaker(read_out, read_in))
        if accepted != {output_name}:
            whole = weaker(whole, _PARTIAL)
        return FieldName(
            output=output_name,
            input=input_name,
            required=required,
            resolution=whole,
            input_resolution=weaker(resolution, read_in),
            excluded=None
            if excluded is _UNREAD
            else (
                self.naming.excluded_when is not None and excluded == self.naming.excluded_when[1]
            ),
        )

    def _required(
        self, calls: list[Mapping[str, Any]], value: Mapping[str, Any] | None
    ) -> bool | None:
        """`required: no_default`: required where no default is written. Each naming call in
        merge order writes one (a `default_arg`), writes none (`required_when`'s field, `...`)
        or leaves the earlier answer; a plain class-body value is one. None where it is not
        read: a default argument in an unpacked value, a value made by a call not read
        (review M2)."""
        if self.naming.required != NO_DEFAULT:
            return None
        state: str = _NONE_WRITTEN
        for site in calls:
            arguments = list(site.get("arguments") or [])
            call = _call_of(site)
            for declared, references, when, ellipsis in self.naming.defaults:
                if call != declared:
                    continue
                written = [_argument(arguments, one) for one in references]
                guarded = _argument(arguments, when) if when is not None else None
                if any(
                    one is not None and one.get("kind") == "unresolved" and "source" not in one
                    for one in [*written, guarded]
                ):
                    state = _NOT_READ_DEFAULT
                elif (
                    isinstance(guarded, dict)
                    and guarded.get("kind") == "field"
                    and guarded.get("symbol") == ellipsis
                ):
                    state = _NONE_WRITTEN
                elif any(one is not None for one in written):
                    state = _WRITTEN
        if value is _VALUE_NOT_READ:
            state = _NOT_READ_DEFAULT
        elif value is None:
            state = _WRITTEN
        if state == _NOT_READ_DEFAULT:
            return None
        return state == _NONE_WRITTEN

    def _annotated(
        self, holder: str, name: str, annotation: Mapping[str, Any] | None
    ) -> list[list[Mapping[str, Any]]]:
        """Each path through the field's `Annotated` metadata: the naming calls among its
        elements, in written order (a nested `Annotated` first, as Python flattens it).
        `[[]]` where the field's annotation carries none. A library class's are its header's
        (task 9c)."""
        library = self._library().get(holder)
        if library is not None:
            entry = library.fields.get(name) or {}
            return [
                [
                    call
                    for call in entry.get("annotation_calls") or []
                    if _call_of(call) in self.naming.calls
                ]
            ]
        body = self._class_bodies().get(holder) if annotation is not None else None
        if body is None or annotation is None:
            return [[]]
        found: list[list[Mapping[str, Any]]] = []
        for producer, _ in producer_paths(
            self.index, held_at_end(body, annotation), 0, _ANNOTATED, shared=_FORM_READER
        ):
            form = _site(self.index, producer)
            found.extend(self._metadata(form) if _call_of(form) in _ANNOTATED else [[]])
        return found or [[]]

    def _metadata(self, form: Mapping[str, Any] | None) -> list[list[Mapping[str, Any]]]:
        """For one `Annotated` form, each path through its metadata, keeping the naming calls."""
        if form is None:
            return [[]]
        arguments = form.get("arguments") or []
        combined: list[list[Mapping[str, Any]]] = [
            nested
            for producer, _ in producer_paths(self.index, form, 0, _ANNOTATED, shared=_FORM_READER)
            for nested in (
                self._metadata(_site(self.index, producer))
                if _call_of(_site(self.index, producer)) in _ANNOTATED
                else [[]]
            )
        ] or [[]]
        stops = self.naming.calls
        for slot in range(1, len(arguments)):
            made = [
                _site(self.index, producer)
                for producer, _ in producer_paths(
                    self.index, form, slot, stops, shared=_VALUE_READER
                )
            ]
            kept: list[list[Mapping[str, Any]]] = [
                [one] if one is not None and _call_of(one) in stops else [] for one in made
            ] or [[]]
            combined = [chosen + one for chosen in combined for one in kept]
        return combined

    def _paths(self, symbol: str) -> list[Mapping[str, Any] | None]:
        """Each path of the field's class-body value: the naming call it ended at;
        `_VALUE_NOT_READ` where it ended at another call, read or not (it may hand back field
        information of its own); None where it ended at any other value (a default); `[_NO_VALUE]` where the class body
        writes no value. Read once per field."""
        if symbol in self._values:
            return self._values[symbol] or [_NO_VALUE]
        holder = owner_of(symbol)
        library = None if holder is None else self._library().get(holder)
        if library is not None:
            read = [
                self._header_end(library.fields.get(symbol[len(str(holder)) :].removesuffix(".")))
            ]
            self._values[symbol] = read
            return read
        written = self._class_body_writes().get(symbol)
        ends: list[Mapping[str, Any] | None] | None = None
        if written:
            ends = []
            stops = self.naming.calls
            for writer, value in written:
                for producer, _ in producer_paths(
                    self.index, held_at_end(writer, value), 0, stops, shared=_VALUE_READER
                ):
                    site = _site(self.index, producer)
                    if _call_of(site) in stops:
                        ends.append(site)
                    elif site is not None or producer.reason == EXTERNAL:
                        # A call not read may hand back field information of its own.
                        ends.append(_VALUE_NOT_READ)
                    elif self._writes_none(producer, value):
                        # `x: int = ...`: the value that writes no default (re-review R2-3).
                        ends.append(_NO_VALUE)
                    else:
                        # Any other value the class body writes is the field's default (a
                        # literal, a display such as `{}`, a name).
                        ends.append(None)
            # A value whose every path the walk left out is a value not read.
            ends = ends or [_VALUE_NOT_READ]
        self._values[symbol] = ends
        return ends or [_NO_VALUE]

    def _header_end(self, entry: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
        """`_paths`' answer for a library class's field, read off its header (task 9c): the
        naming call that made its value; `_VALUE_NOT_READ` for another call or a value not
        read; `_NO_VALUE` where none is written or the value writes none (`...`); None for
        any other value, a default."""
        value = None if entry is None else entry.get("value")
        if entry is None or value is None:
            return _NO_VALUE
        call = entry.get("call")
        if call is not None:
            return call if _call_of(call) in self.naming.calls else _VALUE_NOT_READ
        if value.get("kind") == "unresolved":
            return _VALUE_NOT_READ
        nothing = {ellipsis for *_, ellipsis in self.naming.defaults if ellipsis is not None}
        if value.get("kind") == "field" and value.get("symbol") in nothing:
            return _NO_VALUE
        return None

    def _writes_none(self, producer: Any, value: Mapping[str, Any]) -> bool:
        """Whether a class-body value is the one a `defaults` entry's `required_when` names as
        writing no default (`...`), written directly or reached by the walk."""
        nothing = {ellipsis for *_, ellipsis in self.naming.defaults if ellipsis is not None}
        if value.get("kind") == "field" and value.get("symbol") in nothing:
            return True
        answer = producer.ended_at
        return answer is not None and answer.value in nothing

    def _class_bodies(self) -> dict[str, str]:
        """Each class's body method (`<clinit>`), by bare class symbol."""
        if self._bodies is None:
            self._bodies = self.workspace.once(_class_bodies)
        return self._bodies

    def _library(self) -> "dict[str, LibraryBody]":
        """Each library class whose header read its body, by bare class symbol (task 9c)."""
        if self._headers is None:
            self._headers = self.workspace.once(library_bodies)
        return self._headers

    def _class_body_writes(self) -> dict[str, list[tuple[str, Mapping[str, Any]]]]:
        """Each field's writes made by its own class's body, by bare field symbol."""
        if self._writes is None:
            self._writes = self.workspace.once(_class_body_writes)
        return self._writes

    def _generator(self, model: str, holder: str) -> tuple[str, ...] | None:
        """The first generator set on the way from `model` to `holder` (module docstring)."""
        for current in _closure(model, self._parents()):
            generator = self._config(current).generator
            if generator is not None and generator != _NONE:
                return generator
            if current == holder:
                break
        return None

    def _config(self, symbol: str) -> _Config:
        """`symbol`'s configuration merged over its written bases, the last base winning, then
        its own (R2). Folded once per class."""
        remembered = self._configs.get(symbol)
        if remembered is not None:
            return remembered
        # A cycle cannot be written in a language that runs; held while it is folded anyway.
        self._configs[symbol] = _Config(None, False)
        generator: tuple[str, ...] | None = None
        by_name: bool | None = False
        opened: Any = None
        for parent, _, _ in self._parents().get(symbol, []):
            inherited = self._config(parent)
            if inherited.generator is not None:
                generator = inherited.generator
            by_name = inherited.by_name if inherited.by_name is not False else by_name
            if inherited.opened is not None:
                opened = inherited.opened
        own = self._own_config(symbol)
        if own is not None:
            if own.generator is not None:
                generator = own.generator
            if own.by_name is not False:
                by_name = own.by_name
            if own.opened is not None:
                opened = own.opened
        merged = _Config(generator, by_name, opened)
        self._configs[symbol] = merged
        return merged

    def _own_config(self, symbol: str) -> _Config | None:
        """What `symbol`'s own class body sets in its configuration: None where it writes none,
        a generator `None` where it sets none, `by_name` False where it sets it to nothing."""
        name = self.naming.config_field
        if name is None:
            return None
        library = self._library().get(symbol)
        if library is not None:
            entry = library.fields.get(name)
            if entry is None or entry.get("value") is None:
                return None
            call = entry.get("call")
            if call is None or _call_of(call) not in self.naming.config_calls:
                return _Config(_NOT_READ, None, _UNREAD)
            return self._config_call(list(call.get("arguments") or []))
        written = self._class_body_writes().get(f"{symbol}{name}.")
        if not written:
            return None
        readings: list[_Config] = []
        for writer, value in written:
            for producer, _ in producer_paths(
                self.index,
                held_at_end(writer, value),
                0,
                self.naming.config_calls,
                shared=_CONFIG_READER,
            ):
                site = _site(self.index, producer)
                if _call_of(site) not in self.naming.config_calls or site is None:
                    readings.append(_Config(_NOT_READ, None, _UNREAD))
                    continue
                readings.append(self._config_call(list(site.get("arguments") or [])))
        if not readings or any(reading != readings[0] for reading in readings[1:]):
            return _Config(_NOT_READ, None, _UNREAD)
        return readings[0]

    def _config_call(self, arguments: list[Any]) -> _Config:
        """One configuration call's generator and `by_name`, read off its arguments."""
        if any(entry.get("keyword") == "**" for entry in arguments):
            return _Config(_NOT_READ, None, _UNREAD)
        written = _argument(arguments, self.naming.generator_arg)
        generator: tuple[str, ...] | None
        if written is None:
            generator = None
        elif written.get("kind") == "null":
            generator = _NONE
        elif written.get("kind") == "field" and str(written.get("symbol")) in self.naming.functions:
            generator = (self.naming.functions[str(written.get("symbol"))],)
        else:
            generator = _UNKNOWN
        by_name: bool | None = False
        for reference in self.naming.by_name_args:
            value = _literal(_argument(arguments, reference))
            if value is _UNREAD or (value is not None and not isinstance(value, bool)):
                by_name = None
            elif value is True and by_name is not None:
                by_name = True
        opened: Any = None
        if self.naming.open_when is not None:
            reference, values = self.naming.open_when
            literal = _literal(_argument(arguments, reference))
            opened = literal if literal is None or literal is _UNREAD else literal in values
        return _Config(generator, by_name, opened)

    def opened(self, model: str) -> bool:
        """Whether `model` may carry keys no field declares (`open_when`, task 9c): its merged
        configuration writes a listed literal, or writes the argument as one not read, or is
        not read itself."""
        if self.naming.open_when is None:
            return False
        opened = self._config(model).opened
        return opened is True or opened is _UNREAD

    def output_field(
        self, model: str, holder: str, name: str
    ) -> tuple[FieldName, Mapping[str, Any] | None] | None:
        """The class-level name `name` of `holder` as a field written on output only
        (`output_fields`, task 9c), with the type its method returns; None where no such
        decorator made it. Named by the decorator's argument, else the generator's name for
        it, as a field is; required unless the argument letting it be left out is written."""
        entries = {
            decorator: (named, absent) for decorator, named, absent in self.naming.output_fields
        }
        found = self._decorated(holder, name, frozenset(entries), _OUTPUT_FIELD_READER)
        if found is None:
            return None
        site, returns = found
        named, absent = entries[_call_of(site)]  # type: ignore[index]
        arguments = list(site.get("arguments") or [])
        resolution = _RESOLVED
        if any(entry.get("keyword") in ("*", "**") for entry in arguments):
            resolution = _PARTIAL
        written = _literal(_argument(arguments, named))
        generated: str | None = name
        generator = self._generator(model, holder)
        if generator is not None and generator != _NONE:
            if generator[0] in STRATEGIES:
                generated = STRATEGIES[generator[0]](name)
            elif generator == _NOT_READ:
                resolution = _PARTIAL
            else:
                generated = None
        if written is _UNREAD or (written is not None and not isinstance(written, str)):
            resolution = _PARTIAL
        output = written if isinstance(written, str) else generated
        if output is None:
            resolution = _UNRESOLVED
        required = absent is None or _argument(arguments, absent) is None
        return FieldName(output, None, required, resolution, resolution), returns

    def output_opens(self, model: str) -> tuple[bool, bool]:
        """Whether `model`'s output, and its input, are built by something other than its
        fields (`output_open_when`, task 9c): a method on its way up carrying one of the
        decorators, or, for each method entry, the nearest declaration of that method on its
        way up where that is not the default one the entry names."""
        output = inputs = False
        closure = _closure(model, self._parents())
        decorators = self.naming.output_open_decorators
        if decorators and any(
            self._decorated(holder, name, decorators, _OUTPUT_OPEN_READER) is not None
            for holder in closure
            for name in self._decorated_names(holder)
        ):
            output = True
        for method, also_input, default in self.naming.output_open_methods:
            declarer = next((holder for holder in closure if method in self._members(holder)), None)
            if declarer is not None and declarer != default:
                output = True
                inputs = inputs or also_input
        return output, inputs

    def _members(self, holder: str) -> Mapping[str, Any]:
        """The functions `holder` defines, each to what it returns: a library class's off its
        header, a module class's off its method facts."""
        library = self._library().get(holder)
        if library is not None:
            return {name: method.get("returns") for name, method in library.methods.items()}
        if self._methods is None:
            self._methods = self.workspace.once(_class_methods)
        return self._methods.get(holder, {})

    def _decorated_names(self, holder: str) -> list[str]:
        """The functions `holder` defines whose name holds their decorators' result (D00
        §5a): a library class's decorated methods, a module class's methods its body also
        writes as a name."""
        library = self._library().get(holder)
        if library is not None:
            return [name for name, method in library.methods.items() if method.get("decorators")]
        writes = self._class_body_writes()
        return [name for name in self._members(holder) if f"{holder}{name}." in writes]

    def _decorated(
        self, holder: str, name: str, stops: frozenset[tuple[str, str]], reader: str
    ) -> tuple[Mapping[str, Any], Mapping[str, Any] | None] | None:
        """The decorator call among `stops` that made `holder`'s name `name`, and what the
        decorated method returns; None where none did. A library class's is read off its
        header; a module class's through the walk from the value its body writes the name: the
        decorator call itself, or the call of the value a decorator call returned
        (`@decorator(...)`)."""
        key = (holder, name, stops)
        if key in self._decorations:
            return self._decorations[key]
        found: tuple[Mapping[str, Any], Mapping[str, Any] | None] | None = None
        library = self._library().get(holder)
        if library is not None:
            method = library.methods.get(name) or {}
            site = next(
                (call for call in method.get("decorators") or [] if _call_of(call) in stops),
                None,
            )
            if site is not None:
                found = (site, method.get("returns"))
        else:
            returns = self._members(holder).get(name)
            for writer, value in self._class_body_writes().get(f"{holder}{name}.", []):
                site = self._decorator_site(writer, value, stops, reader)
                if site is not None:
                    found = (site, returns)
                    break
        self._decorations[key] = found
        return found

    def _decorator_site(
        self, writer: str, value: Mapping[str, Any], stops: frozenset[tuple[str, str]], reader: str
    ) -> Mapping[str, Any] | None:
        """The decorator call among `stops` that made a class-body value: the walk's end, or,
        for a decorator written as a call (`@decorator(...)`), whose result the facts call as a
        value with no owner to walk through (`__call__`, D00 §5), the call that made that
        value, read from the call the value comes from."""
        for producer, _ in producer_paths(
            self.index, held_at_end(writer, value), 0, stops, shared=reader
        ):
            site = _site(self.index, producer)
            if site is not None and _call_of(site) in stops:
                return site
        source = value.get("source")
        applied = None if source is None else self.index.sites.get((writer, int(source)))
        if (
            applied is None
            or applied.get("result") != source
            or applied.get("name") != _CALL_OF_VALUE
            or applied.get("receiver") is None
        ):
            return None
        for producer, _ in producer_paths(self.index, applied, RECEIVER, stops, shared=reader):
            made = _site(self.index, producer)
            if made is not None and _call_of(made) in stops:
                return made
        return None

    def _parents(self) -> dict[str, list[tuple[str, str, bool]]]:
        if self._ancestry is None:
            self._ancestry = ancestry_of(self.workspace)[0]
        return self._ancestry


# `_paths`' answers where the class body writes no value, and where it writes one no path of
# which the walk gives.
_NO_VALUE: Mapping[str, Any] = {}
_VALUE_NOT_READ: Mapping[str, Any] = {"arguments": []}


def _class_bodies(workspace: Workspace) -> dict[str, str]:
    """Each class's body method, `<clinit>`, by bare class symbol (D00 §5a). Read through
    `Workspace.once`: facts only."""
    found: dict[str, str] = {}
    for row in workspace.query("declared_symbols"):
        symbol = str(row["symbol"])
        bare = bare_descriptor(symbol)
        owner = owner_of(bare)
        if owner is not None and bare.startswith(owner + _CLASS_BODY):
            found[owner] = symbol
    return found


@dataclass(frozen=True)
class LibraryBody:
    """A library class's body, read off its type header (fact schema 12, task 9c): each name
    it declares and each function it defines, by name."""

    fields: Mapping[str, Mapping[str, Any]]
    methods: Mapping[str, Mapping[str, Any]]


def library_bodies(workspace: Workspace) -> dict[str, LibraryBody]:
    """Each library class whose header read its body, by bare class symbol. Read through
    `Workspace.once`: facts only."""
    found: dict[str, LibraryBody] = {}
    for row in workspace.query("type_header_bodies"):
        fields = _json(row["fields"]) or []
        methods = _json(row["methods"]) or []
        found[bare_descriptor(str(row["symbol"]))] = LibraryBody(
            fields={str(entry["name"]): entry for entry in fields},
            methods={str(entry["name"]): entry for entry in methods},
        )
    return found


def _json(value: Any) -> Any:
    """A JSON column as the workspace hands it back: text, or already read."""
    return json.loads(value) if isinstance(value, str) else value


def _class_methods(workspace: Workspace) -> dict[str, dict[str, Any]]:
    """Each module class's methods, by bare class symbol, each name to its declared return.
    Read through `Workspace.once`: facts only."""
    found: dict[str, dict[str, Any]] = {}
    for row in workspace.query("method_declarations"):
        bare = bare_descriptor(str(row["symbol"]))
        owner = owner_of(bare)
        if owner is None:
            continue
        name = bare[len(owner) :].split("(")[0]
        signature = _json(row["signature"]) or {}
        found.setdefault(owner, {}).setdefault(
            name, signature.get("returns") if isinstance(signature, dict) else None
        )
    return found


def _class_body_writes(workspace: Workspace) -> dict[str, list[tuple[str, Mapping[str, Any]]]]:
    """Each field's writes its own class's body makes, `(writer, value)`, by bare field symbol.
    Read through `Workspace.once`: facts only."""
    found: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for row in workspace.query("field_writes"):
        written, writer, symbol = row.get("value"), row.get("written_by"), row.get("field")
        if written is None or writer is None or symbol is None:
            continue
        owner = owner_of(str(symbol))
        if owner is None or not bare_descriptor(str(writer)).startswith(owner + _CLASS_BODY):
            continue
        entry = json.loads(str(written)) if isinstance(written, str) else written
        if isinstance(entry, dict):
            found.setdefault(str(symbol), []).append((str(writer), entry))
    return found


def _closure(start: str, ancestry: Mapping[str, list[tuple[str, str, bool]]]) -> list[str]:
    """`start` and its ancestors, breadth-first in written order."""
    order: list[str] = []
    queue = [start]
    while queue:
        current = queue.pop(0)
        if current in order:
            continue
        order.append(current)
        queue.extend(parent for parent, _, _ in ancestry.get(current, []))
    return order


def _call_of(site: Mapping[str, Any] | None) -> tuple[str, str] | None:
    if not site:
        return None
    return (str(site.get("owner")), str(site.get("name")))


def _argument(arguments: list[Any], reference: Any) -> dict[str, Any] | None:
    """The argument a catalog reference names, None where it is not written; an unpacked value
    that may be it is not read."""
    if reference is None or not arguments:
        return None
    slot = argument_slot(arguments, reference)
    if slot == UNPACKED_SLOT:
        return {"kind": "unresolved"}
    return None if slot is None else arguments[slot]


def _literal(argument: dict[str, Any] | None) -> Any:
    """An argument's literal value; None where it is not written or written `None`, `_UNREAD`
    where it is written as anything else."""
    if argument is None or argument.get("kind") == "null":
        return None
    if argument.get("kind") in ("string", "int", "long", "boolean"):
        return argument.get("value")
    return _UNREAD


def _first(
    arguments: list[Any],
    call: tuple[str, str] | None,
    entries: tuple[tuple[tuple[str, str], Any], ...],
) -> Any:
    """The first of `entries` written on `call` as a string, `_UNREAD` where the first written
    is anything else, None where none is written."""
    for declared, reference in entries:
        if declared != call:
            continue
        value = _literal(_argument(arguments, reference))
        if value is None:
            continue
        return value if isinstance(value, str) else _UNREAD
    return None


def _merged(earlier: Any, later: Any) -> Any:
    """One attribute merged over two calls: the later call's where it writes one."""
    return earlier if later is None else later


def _named(written: Any, generated: str | None) -> str | None:
    """A name: the one written, else the generator's (None where it is not read)."""
    if isinstance(written, str):
        return written
    return generated
