"""CP-click: the click rules `catalogs/click.yml` and `value-models/click.yml` state, read off
the installed click's own source (design 2026-11-06-reading-decorators §2d, §3d, §4).

Run with the interpreter whose environment holds click, isolated:

    .venv/bin/python -I scripts/probes/click_commands.py

It imports click, prints the version the installed distribution REPORTS
(`importlib.metadata`), and checks each rule against the source of the function that
implements it (`inspect.getsource`): a rule whose source line is missing aborts the run, so
the table it prints can only hold rules that were read. The output is the observation table
of `scripts/probes/click_commands.md`, pasted as printed.
"""

import inspect
import sys
from importlib import metadata

import click
from click import core, decorators, utils

# (rule, function, the source text that states it)
RULES = (
    (
        "1 `command` takes its name positionally or as `name`",
        decorators.command,
        "def command(\n    name: str | _AnyCallable | None = None,",
    ),
    (
        "1 `Group.command` passes its arguments to `command` as written",
        core.Group.command,
        "cmd: Command = command(*args, **kwargs)(f)",
    ),
    (
        "1 `Group.command` adds the command to the group",
        core.Group.command,
        "self.add_command(cmd)",
    ),
    (
        "1 `Group.group` passes its arguments to `group` as written",
        core.Group.group,
        "cmd: Group = group(*args, **kwargs)(f)",
    ),
    (
        "2 no name: `f.__name__` lower-cased, `_` to `-`",
        decorators.command,
        'cmd_name = f.__name__.lower().replace("_", "-")',
    ),
    (
        "2 no name: a last part after `-` is split off",
        decorators.command,
        'cmd_left, sep, suffix = cmd_name.rpartition("-")',
    ),
    (
        "2 no name: the suffixes removed",
        decorators.command,
        'if sep and suffix in {"command", "cmd", "group", "grp"}:',
    ),
    (
        "3 `option`'s decorator returns the function",
        decorators.option,
        "_param_memo(f, cls(param_decls, **attrs))\n        return f",
    ),
    (
        "3 `argument`'s decorator returns the function",
        decorators.argument,
        "_param_memo(f, cls(param_decls, **attrs))\n        return f",
    ),
    (
        "3 `password_option` returns `option`'s decorator",
        decorators.password_option,
        "return option(*param_decls, **kwargs)",
    ),
    (
        "3 `version_option` returns `option`'s decorator",
        decorators.version_option,
        "return option(*param_decls, **kwargs)",
    ),
    (
        "3 `group(name)` decorates a function written as `name`",
        decorators.group,
        "if callable(name):\n        return command(cls=cls, **attrs)(name)",
    ),
    (
        "4 the program's name is how it was started",
        utils._detect_program_name,
        "path = sys.argv[0]",
    ),
    (
        "4 a file or entry point: its base name",
        utils._detect_program_name,
        "return os.path.basename(path)",
    ),
    (
        "5 an argument with no `required`: required unless a `default` is written",
        core.Argument.__init__,
        'if attrs.get("default", UNSET) is UNSET:\n                required = attrs.get("nargs", 1) > 0',
    ),
    ("5 an argument with a `default`: not required", core.Argument.__init__, "required = False"),
    (
        "5 an option: not required unless `required` (`Parameter`'s default)",
        core.Parameter.__init__,
        "required: bool = False",
    ),
    ("5 an option hands `required` to `Parameter`", core.Option.__init__, "**attrs: t.Any,"),
    (
        "5 an argument takes exactly one declaration",
        core.Argument._parse_decls,
        "Arguments take exactly one parameter declaration, got",
    ),
    (
        "5 an option's declaration that is an identifier is the parameter's name",
        core.Option._parse_decls,
        "if decl.isidentifier():",
    ),
    (
        "5 an option's every other declaration is a spelling",
        core.Option._parse_decls,
        "opts.append(decl)",
    ),
    (
        "5 `is_flag`: an option that takes no value",
        core.Option.__init__,
        "is_flag: bool | None = None",
    ),
)


def main() -> int:
    reported = metadata.version("click")
    rows = []
    for rule, function, text in RULES:
        source = inspect.getsource(function)
        if text not in source:
            print(
                f"ABORT: {rule}: not in {function.__qualname__} at click {reported}",
                file=sys.stderr,
            )
            return 1
        rows.append((rule, f"`{function.__module__}.{function.__qualname__}`"))
    print(f"click {reported} from {click.__file__} (importlib.metadata reports {reported})")
    print()
    print(f"| Rule | Read in | {reported} |")
    print("|---|---|---|")
    for rule, where in rows:
        print(f"| {rule} | {where} | read |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
