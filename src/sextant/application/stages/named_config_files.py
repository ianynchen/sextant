"""The config files the module's own CODE names (plan 3 Task 4, N3): a settings class whose
`model_config` is a call carrying an `env_file` argument names the file its values may come from.

Which libraries name a file, which class-body field holds the call, which calls count and which
argument carries the name are catalog data (`config_model.settings_form` and the
`from_argument` entry of `config_model.sources`); nothing here names a framework. A file is
named only when the argument is a string (or a tuple of strings) written in the call itself — a
name reached through a variable is a value this stage will not guess, so no file is opened (the
field that reads it says `external`, naming the expression, in the pass that has the call).

**Cost (§8.7).** Nothing is read for a module whose dependencies select no such catalog. For one
that does: the fact files' bytes are tested once for the argument's name, as `read_fact_tree`'s
`containing` does for descriptors, and only the files that hold it are parsed; then one file
per name. No pass over the facts is added to the resolve."""

from collections.abc import Sequence
from pathlib import Path

from sextant.application.ports.catalogs import Catalog
from sextant.application.ports.detector import ModuleModel
from sextant.application.resolve.config import FROM_ARGUMENT
from sextant.domain.factfile import read_fact_tree
from sextant.domain.facts import CallArgument, CallSiteFact, FieldWriteFact
from sextant.domain.resource_files import named_file
from sextant.domain.symbols import type_descriptor


def _forms(dotted: str) -> set[tuple[str, str]]:
    """The (owner, name) pairs the extractor may write for one catalog call (`a.b.C.<init>`):
    a class construction, or — for a class called as a function — the module's own call."""
    owner, _, method = dotted.rpartition(".")
    module, _, cls = owner.rpartition(".")
    forms = {(type_descriptor(owner), method)}
    if method == "<init>" and module:
        forms.add((type_descriptor(module), cls))
    return forms


def _names(argument: CallArgument) -> list[str] | None:
    """The file names an `env_file` argument writes, or `None` where it writes anything else."""
    if argument.kind == "string" and isinstance(argument.value, str):
        return [argument.value]
    if argument.kind == "array" and argument.elements is not None:
        names = [_names(one) for one in argument.elements]
        if all(one is not None and len(one) == 1 for one in names):
            return [one[0] for one in names if one]
    return None


def named_config_files(
    module: ModuleModel, fact_root: Path, catalogs: Sequence[Catalog]
) -> tuple[Path, ...]:
    """The files under the module's root its settings classes name, in the order they are named
    (a later one overrides an earlier one, so the order is the precedence), each once."""
    selected = [
        (source[FROM_ARGUMENT], form)
        for catalog in catalogs
        if (form := catalog.config_model.get("settings_form"))
        and not set(catalog.detect_coordinates).isdisjoint(module.dependency_coordinates)
        for source in catalog.config_model.get("sources", [])
        if FROM_ARGUMENT in source
    ]
    found: list[Path] = []
    for keyword, form in selected:
        field = f"#{form['config_field']}."
        calls = {pair for dotted in form["config_call"] for pair in _forms(dotted)}
        token = f'"keyword":"{keyword}"'.encode()
        for _, document, facts in read_fact_tree(fact_root, containing=token):
            if document.origin is not None or document.header_only:
                continue
            # A call's value is its `result`; a construction's is the `receiver` it fills.
            made = {
                (fact.caller, fact.result if fact.result is not None else fact.receiver): fact
                for fact in facts
                if isinstance(fact, CallSiteFact) and (fact.target.owner, fact.target.name) in calls
            }
            for fact in facts:
                if not (isinstance(fact, FieldWriteFact) and fact.field.endswith(field)):
                    continue
                written = (fact.written_by or "", fact.value.source if fact.value else None)
                call = made.get(written)
                for argument in call.arguments if call else []:
                    names = _names(argument) if argument.keyword == keyword else None
                    for name in names or []:
                        path = named_file(module.root, name)
                        if path is not None and path not in found:
                            found.append(path)
    return tuple(found)
