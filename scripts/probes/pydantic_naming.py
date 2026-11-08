"""Pydantic's naming rules, and mealie's field names under three generators (plan 2, Task 0).

Run it inside a throwaway environment that has `pydantic` and `pyhumps` installed, never inside
the repository's `.venv`:

    uv venv /tmp/probe && uv pip install -p /tmp/probe/bin/python fastapi==0.162.0 pyhumps
    /tmp/probe/bin/python scripts/probes/pydantic_naming.py <mealie's mealie/ folder>

Part 1 reads every class that reaches `BaseModel` by name (ast only) and compares
`pydantic.alias_generators.to_camel`, `to_pascal` and `humps.main.camelize` on each field name.
Part 2 builds small models and prints the aliases pydantic gives each field. What the results
mean for N12 and N13 is in `pydantic_naming.md`. The probe imports pydantic and builds models on
purpose. Sextant itself never does that (spec 7).
"""

from __future__ import annotations

import ast
import importlib.metadata
import json
import sys
from pathlib import Path
from typing import ClassVar, Optional

import pydantic
from humps.main import camelize
from pydantic import AliasChoices, AliasGenerator, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel, to_pascal


def last_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return last_name(node.value)
    return None


def field_names(root: Path) -> tuple[int, set[str], set[str]]:
    """Class count, public field names and underscore names of the model classes under `root`."""
    trees: list[ast.Module] = []
    for path in root.rglob("*.py"):
        try:
            trees.append(ast.parse(path.read_text(encoding="utf-8")))
        except (SyntaxError, UnicodeDecodeError, ValueError):
            continue
    bases: dict[str, set[str]] = {}
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases.setdefault(node.name, set()).update(
                    b for b in (last_name(base) for base in node.bases) if b
                )
    models = {"BaseModel"}
    changed = True
    while changed:
        changed = False
        for name, parents in bases.items():
            if name not in models and parents & models:
                models.add(name)
                changed = True
    public: set[str] = set()
    private: set[str] = set()
    classes = 0
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in models:
                classes += 1
                for stmt in node.body:
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                        (private if stmt.target.id.startswith("_") else public).add(stmt.target.id)
    return classes, public, private


def part_one(root: Path) -> list[tuple[str, str, str]]:
    classes, names, private = field_names(root)
    rows = [(n, to_camel(n), to_pascal(n), camelize(n)) for n in sorted(names)]
    print("## Part 1: mealie field names")
    print(f"model classes (by name closure): {classes}")
    print(f"distinct field names: {len(names)} (underscore names skipped: {len(private)})")
    print("to_camel differs from humps.camelize:", [(n, c, h) for n, c, _, h in rows if c != h])
    print(
        "to_pascal differs from to_camel with its first letter raised:",
        [(n, p, c) for n, c, p, _ in rows if p != c[:1].upper() + c[1:]],
    )
    print(
        "names changed by to_camel:",
        sum(1 for n, c, _, _ in rows if c != n),
        "| by humps.camelize:",
        sum(1 for n, _, _, h in rows if h != n),
    )
    differ = sum(1 for _, c, _, h in rows if c != h)
    pascal = sum(1 for _, c, p, _ in rows if p != c[:1].upper() + c[1:])
    return [
        (f"`humps.camelize` differs from `to_camel` ({len(rows)} names)", "n/a", str(differ)),
        ("`to_pascal` differs from `to_camel` with its first letter raised", str(pascal), "n/a"),
    ]


def up(name: str) -> str:
    return name.upper()


def show(label: str, model: type[BaseModel], **data: object) -> None:
    fields = {
        name: {
            "alias": info.alias,
            "validation_alias": str(info.validation_alias) if info.validation_alias else None,
            "serialization_alias": info.serialization_alias,
            "required": info.is_required(),
        }
        for name, info in model.model_fields.items()
    }
    out: dict[str, object] = {"fields": fields}
    if data:
        try:
            out["dump_by_alias"] = model.model_validate(data).model_dump(by_alias=True)
        except Exception as exc:  # noqa: BLE001 - the probe reports every failure
            out["validate_error"] = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
    print(label, json.dumps(out))


class Plain(BaseModel):
    my_field: int = 0


class GenOnly(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)
    my_field: int = 0


class AliasBeatsGen(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)
    my_field: int = Field(0, alias="Explicit")


class Priority1(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)
    my_field: int = Field(0, alias="Explicit", alias_priority=1)


class Priority1WithSerialization(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)
    my_field: int = Field(0, alias="Al", serialization_alias="Ser", alias_priority=1)


class SerAlias(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)
    my_field: int = Field(0, serialization_alias="Ser")


class SerAndAlias(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)
    my_field: int = Field(0, alias="Al", serialization_alias="Ser")


class ValAlias(BaseModel):
    my_field: int = Field(0, validation_alias=AliasChoices("a", "b"))


class ValAndAlias(BaseModel):
    my_field: int = Field(0, alias="Al", validation_alias="Val")


class GeneratorObject(BaseModel):
    model_config = ConfigDict(
        alias_generator=AliasGenerator(validation_alias=to_pascal, serialization_alias=to_camel)
    )
    my_field: int = 0


class PopByName(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    my_field: int = 0


class Parent(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ChildKeepsGen(Parent):
    my_field: int = 0


class ChildOverridesGen(Parent):
    model_config = ConfigDict(alias_generator=to_pascal)
    my_field: int = 0


class ChildNoneGen(Parent):
    model_config = ConfigDict(alias_generator=None)
    my_field: int = 0


class ChildAddsOther(Parent):
    model_config = ConfigDict(str_strip_whitespace=True)
    my_field: int = 0


class Left(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)


class Right(BaseModel):
    model_config = ConfigDict(alias_generator=to_pascal)


class Both(Left, Right):
    my_field: int = 0


class Shouting(BaseModel):
    model_config = ConfigDict(alias_generator=up)
    my_field: int = 0


class Misc(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)
    _private: int = 0
    cv: ClassVar[int] = 1
    needs: int
    opt_no_default: Optional[int]  # noqa: UP045 - the spelling is the case
    opt_none: Optional[int] = None  # noqa: UP045
    ell: int = Field(...)
    empty_field: int = Field()
    factory: list[int] = Field(default_factory=list)


def part_two() -> None:
    print("\n## Part 2: aliases pydantic gives a field", f"(pydantic {pydantic.VERSION})")
    show("plain", Plain)
    show("generator_only", GenOnly, myField=1)
    show("alias_beats_generator", AliasBeatsGen, Explicit=1)
    show("alias_priority_1_generator_wins", Priority1, myField=1)
    show("alias_priority_1_with_serialization_alias", Priority1WithSerialization)
    show("serialization_alias_beats_generator", SerAlias, myField=1)
    show("serialization_alias_and_alias", SerAndAlias, Al=1)
    show("validation_alias_choices", ValAlias, b=1)
    show("alias_and_validation_alias", ValAndAlias, Val=1)
    show("AliasGenerator_object", GeneratorObject)
    show("populate_by_name", PopByName, my_field=1)
    show("custom_generator_function", Shouting, MY_FIELD=1)
    print("\n### Config merge across bases")
    show("child_keeps_parent_generator", ChildKeepsGen, myField=1)
    show("child_overrides_generator", ChildOverridesGen, MyField=1)
    show("child_sets_generator_none", ChildNoneGen, my_field=1)
    show("child_adds_other_config", ChildAddsOther, myField=1)
    print(
        "  child config:",
        {k: getattr(v, "__name__", v) for k, v in ChildAddsOther.model_config.items()},
    )
    show("two_parents_written_left_then_right", Both)
    print(
        "  mro:",
        [c.__name__ for c in Both.__mro__][:4],
        "| merged generator:",
        Both.model_config["alias_generator"].__name__,
    )
    print("\n### Required, private, class variables")
    show("misc", Misc)
    print(
        "  private attributes:",
        list(Misc.__private_attributes__),
        "| class vars:",
        list(Misc.__class_vars__),
    )
    print("\n### Input by field name")
    print(
        "  without populate_by_name, input my_field=5 gives",
        GenOnly.model_validate({"my_field": 5}).my_field,
        "(0: the name was ignored)",
    )
    print(
        "  with populate_by_name, input my_field=5 gives",
        PopByName.model_validate({"my_field": 5}).my_field,
    )


def observation_table(rows: list[tuple[str, str, str]]) -> None:
    """The table of `pydantic_naming.md`, headed by the versions this process reported."""
    pyhumps = importlib.metadata.version("pyhumps")
    print("\n## Observation table (generated)")
    print(f"| Question | {pydantic.VERSION} | {pyhumps} |")
    print("|---|---|---|")
    for label, in_pydantic, in_pyhumps in rows:
        print(f"| {label} | {in_pydantic} | {in_pyhumps} |")
    print(
        f"\n`pydantic.VERSION` printed {pydantic.VERSION}; `importlib.metadata` printed pyhumps {pyhumps}."
    )


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    rows = part_one(Path(argv[0]).resolve())
    part_two()
    rows += [
        (
            "`Both(Left, Right)` takes the generator of",
            Both.model_config["alias_generator"].__name__,
            "n/a",
        ),
        (
            "`alias_priority=1` with `alias` and `serialization_alias` gives output name",
            Priority1WithSerialization.model_fields["my_field"].serialization_alias or "none",
            "n/a",
        ),
        (
            "`serialization_alias` beats the generator: output name",
            SerAlias.model_fields["my_field"].serialization_alias or "none",
            "n/a",
        ),
        (
            "`Optional[int]` with no default is required",
            str(Misc.model_fields["opt_no_default"].is_required()),
            "n/a",
        ),
    ]
    observation_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
