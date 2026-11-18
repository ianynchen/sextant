"""The configuration key each field of a settings class is read from (plan 3 Task 5, N2; rulings
R23-R26).

A settings class is one whose lookup order reaches the config model's `settings_base`. Its
configuration is the call its `config_field` holds (a `config_call`), merged over its lookup
order with the class itself winning, as pydantic merges `model_config`. Each field's key is the
prefix (`prefix_key`) and the first name `name_from` finds: a keyword of the call that made the
field's class-body value, or the reserved entry `name`, the field's own name. Whether the
prefix applies to a name or to an alias is `prefix_key.target`; `case_insensitive` says how
the key is spelled. Every word is catalog data (`config_model.settings_form`); nothing here
names a library. The rules copied are measured in `scripts/probes/pydantic_settings_rules.md`.

**A key is a fact about the repository** (deployment decides): the field's class-body literal
is its default, rendered after the model's `default_separator` (R25), and is the value only
where nothing the deployment or the named file sets says otherwise, which `resolved_peers`
answers per environment. A file named through no literal may set any key, so no default is
rendered and the per-environment answer names that expression (R26). A name rule written as
no literal leaves the key unknown: `None`.

**Cost (§8.7).** Read only for a module whose config model has a `settings_form`: one pass over
`fields`, one over `field_writes`, the effective call sites already read, and one lookup order
per class declaring a field (`Dispatch` keeps its linearizations)."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sextant.application.ports.workspace import Workspace
from sextant.application.resolve.dispatch import Dispatch
from sextant.application.resolve.effective_calls import effective_call_sites
from sextant.domain.symbols import bare_descriptor, member_name, owner_of, type_descriptor

# The `returns_arguments` row form that carries the module's config model to the value walk
# (`with_config_model`): its placeholders, and its `settings_form` where it declares one.
CONFIG_MODEL_FORM = "config_model"
# The `name_from` entry that is the field's own declared name rather than a keyword.
_DECLARED_NAME = "name"
# A class body's own method (D00 §5a): a class-body value is written there.
_CLASS_BODY = "<clinit>("
_LITERALS = ("string", "int", "long", "boolean")


def config_call_forms(dotted: str) -> set[tuple[str, str]]:
    """The (owner, name) pairs the extractor may write for one catalog call (`a.b.C.<init>`):
    a class construction, or, for a class called as a function, the module's own call."""
    owner, _, method = dotted.rpartition(".")
    module, _, cls = owner.rpartition(".")
    forms = {(type_descriptor(owner), method)}
    if method == "<init>" and module:
        forms.add((type_descriptor(module), cls))
    return forms


@dataclass(frozen=True)
class SettingsKey:
    """One settings field's configuration key: `key` None where a name rule is written as no
    literal; `default` the class-body literal as text, None where none is written; `file` what
    a file named through no literal is chosen by, None where every named file is written."""

    key: str | None
    default: str | None
    file: str | None

    def expression(self, placeholders: Mapping[str, str]) -> str | None:
        """`${KEY}`, or `${KEY<separator>DEFAULT}` where a default stands (R25)."""
        if self.key is None:
            return None
        inside = self.key
        if self.default is not None and self.file is None:
            inside += placeholders["default_separator"] + self.default
        return placeholders["open"] + inside + placeholders["close"]

    def file_detail(self) -> str:
        """R26: the per-environment detail of a key a file named through no literal may set."""
        return f"{self.key} is set by the deployment or by the file {self.file} names"


def settings_keys(
    workspace: Workspace, model: Mapping[str, Any], dispatch: Dispatch
) -> dict[str, SettingsKey]:
    """Each settings field's key, by bare field symbol; empty where `model` has no
    `settings_form`."""
    form = model.get("settings_form")
    if not form:
        return {}
    base = type_descriptor(str(form["settings_base"]))
    calls = {pair for dotted in form["config_call"] for pair in config_call_forms(dotted)}
    file_key = next(
        (
            str(source["from_argument"])
            for source in model.get("sources", [])
            if "from_argument" in source
        ),
        None,
    )
    sites = {
        (str(site["caller"]), int(str(site["result"]))): site
        for site in effective_call_sites(workspace)
        if _CLASS_BODY in str(site["caller"]) and site.get("result") is not None
    }
    writes: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for row in workspace.query("field_writes"):
        writer, value = row.get("written_by"), row.get("value")
        if writer is None or value is None or _CLASS_BODY not in str(writer):
            continue
        entry = json.loads(str(value)) if isinstance(value, str) else value
        if isinstance(entry, dict):
            writes.setdefault(bare_descriptor(str(row["field"])), []).append((str(writer), entry))

    def made_by(field: str) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
        """The class-body value written to `field`, and the call that made it, if a call did."""
        written = writes.get(field, [])
        if len(written) != 1:
            return None, None
        writer, entry = written[0]
        source = entry.get("source")
        return entry, None if source is None else sites.get((writer, int(str(source))))

    def own_config(cls: str) -> dict[str, Mapping[str, Any]]:
        _, site = made_by(f"{cls}{form['config_field']}.")
        if site is None or (site.get("owner"), site.get("name")) not in calls:
            return {}
        return {
            str(argument["keyword"]): argument
            for argument in site.get("arguments") or []
            if isinstance(argument, Mapping) and argument.get("keyword")
        }

    settings: dict[str, bool] = {}
    configs: dict[str, dict[str, Mapping[str, Any]]] = {}
    found: dict[str, SettingsKey] = {}
    for row in workspace.query("fields"):
        if row["static"]:
            continue
        field = bare_descriptor(str(row["symbol"]))
        cls = owner_of(field)
        if cls is None:
            continue
        if cls not in settings:
            order = dispatch.lookup_order(cls)
            settings[cls] = base in order
            if settings[cls]:
                merged: dict[str, Mapping[str, Any]] = {}
                for one in reversed(order):
                    merged.update(own_config(one))
                configs[cls] = merged
        if not settings[cls] or member_name(field) == form["config_field"]:
            continue
        found[field] = _key(field, configs[cls], made_by(field), form, file_key)
    return found


def _key(
    field: str,
    config: Mapping[str, Mapping[str, Any]],
    made: tuple[Mapping[str, Any] | None, Mapping[str, Any] | None],
    form: Mapping[str, Any],
    file_key: str | None,
) -> SettingsKey:
    entry, site = made
    default = (
        None if entry is None or entry.get("kind") not in _LITERALS else _text(entry.get("value"))
    )
    file = None
    if file_key is not None and file_key in config and not _named(config[file_key]):
        file = _expression_text(config[file_key])
    unknown = SettingsKey(None, default, file)
    prefix_key = form["prefix_key"]
    prefix = _literal(config, prefix_key["keyword"], "")
    target_rule = prefix_key["target"]
    target = _literal(config, target_rule["keyword"], target_rule["default"])
    insensitive_rule = form["case_insensitive"]
    unless = insensitive_rule["unless"]
    sensitive = _literal(config, unless["keyword"], None)
    if prefix is None or target is None or (sensitive is None and unless["keyword"] in config):
        return unknown
    insensitive = (
        bool(insensitive_rule["default"]) if sensitive is None else sensitive != unless["value"]
    )
    arguments = {
        str(argument["keyword"]): argument
        for argument in (site.get("arguments") or [] if site is not None else [])
        if isinstance(argument, Mapping) and argument.get("keyword")
    }
    name: str | None = None
    applies: list[str] = []
    for source in form["name_from"]:
        if source == _DECLARED_NAME:
            name, applies = member_name(field), target_rule["name"]
            break
        if source in arguments:
            written = arguments[source]
            if written.get("kind") != "string":
                return unknown
            name, applies = str(written["value"]), target_rule["alias"]
            break
    if name is None or target not in (*target_rule["name"], *target_rule["alias"]):
        return unknown
    key = (str(prefix) if target in applies else "") + name
    return SettingsKey(key.upper() if insensitive else key, default, file)


def _literal(config: Mapping[str, Mapping[str, Any]], keyword: str, absent: Any) -> Any:
    """The literal `config` writes for `keyword`, `absent` where it writes none; None where it
    writes something that is no literal."""
    written = config.get(keyword)
    if written is None:
        return absent
    if written.get("kind") not in _LITERALS:
        return None
    return written.get("value")


def _named(argument: Mapping[str, Any]) -> bool:
    """Whether a file argument is written in the call: a string or a tuple of strings."""
    if argument.get("kind") == "string":
        return True
    elements = argument.get("elements")
    return (
        argument.get("kind") == "array"
        and isinstance(elements, list)
        and all(isinstance(one, Mapping) and one.get("kind") == "string" for one in elements)
    )


def _expression_text(argument: Mapping[str, Any]) -> str:
    """How a person reads the expression a file is chosen by: the name read, else its kind."""
    symbol = argument.get("symbol")
    if symbol is not None:
        return f"`{bare_descriptor(str(symbol))}`"
    return f"a value written as {argument.get('kind')}"


def _text(value: Any) -> str:
    """A literal as the text a deployment would write for it."""
    return str(value)
