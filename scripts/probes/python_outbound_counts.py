"""Count the shapes plan 3 reads in a Python corpus: outbound HTTP calls, environment reads,
settings classes and guards on settings fields (plan 3, Task 0).

    python -I scripts/probes/python_outbound_counts.py <corpus-root>...

Reads files with `ast` only and never imports the corpus. Test files and environments are skipped
(test code is never analysed). Names are tracked by import and by assignment inside one file, so
a client held in another module's attribute is counted under "other receiver".
"""

from __future__ import annotations

import ast
import collections
import sys
from pathlib import Path

LIBS = {"requests": "requests", "httpx": "httpx"}
VERBS = {"get", "options", "head", "post", "put", "patch", "delete"}
SKIP_DIRS = {".venv", "venv", "node_modules", "site-packages", ".git", "__pycache__"}
CLIENT_CTORS = {"Session", "Client", "AsyncClient"}


def is_test(path: Path) -> bool:
    return (
        any(p in ("tests", "test", "testing") for p in path.parts)
        or path.name.startswith("test_")
        or path.name == "conftest.py"
    )


def files(root: Path):
    for p in root.rglob("*.py"):
        if SKIP_DIRS & set(p.parts) or is_test(p.relative_to(root)):
            continue
        yield p


def dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def scan(
    tree: ast.Module, out: collections.Counter, settings: dict[str, int], guard_names: set[str]
) -> None:
    mod_alias: dict[str, str] = {}  # local name -> lib
    fn_alias: dict[str, tuple[str, str]] = {}  # local name -> (lib, member)
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name in LIBS:
                    mod_alias[a.asname or a.name] = a.name
        elif isinstance(n, ast.ImportFrom) and n.module in LIBS:
            for a in n.names:
                fn_alias[a.asname or a.name] = (n.module, a.name)
    clients: dict[str, str] = {}  # dotted receiver -> lib

    def ctor_lib(call: ast.AST) -> str | None:
        if not isinstance(call, ast.Call):
            return None
        d = dotted(call.func)
        if d is None:
            return None
        head, _, member = d.rpartition(".")
        if head in mod_alias and member in CLIENT_CTORS:
            return mod_alias[head]
        if not head and d in fn_alias and fn_alias[d][1] in CLIENT_CTORS:
            return fn_alias[d][0]
        return None

    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            lib = ctor_lib(n.value)
            if lib:
                for t in n.targets:
                    if d := dotted(t):
                        clients[d] = lib
        elif isinstance(n, ast.AnnAssign) and n.value is not None and (lib := ctor_lib(n.value)):
            if d := dotted(n.target):
                clients[d] = lib
        elif isinstance(n, (ast.With, ast.AsyncWith)):
            for it in n.items:
                if (
                    (lib := ctor_lib(it.context_expr))
                    and it.optional_vars is not None
                    and (d := dotted(it.optional_vars))
                ):
                    clients[d] = lib

    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            d = dotted(n.func)
            if d:
                head, _, member = d.rpartition(".")
                if head in mod_alias and (member in VERBS or member in ("request", "stream")):
                    form = (
                        "request(method,..)"
                        if member == "request"
                        else ("stream" if member == "stream" else "module-level verb")
                    )
                    out[(mod_alias[head], form)] += 1
                elif (
                    not head
                    and d in fn_alias
                    and (fn_alias[d][1] in VERBS or fn_alias[d][1] in ("request", "stream"))
                ):
                    out[
                        (
                            fn_alias[d][0],
                            "from-import "
                            + ("request(method,..)" if fn_alias[d][1] == "request" else "verb"),
                        )
                    ] += 1
                elif head in clients and (member in VERBS or member in ("request", "stream")):
                    out[
                        (
                            clients[head],
                            "client request(method,..)"
                            if member == "request"
                            else "session/client verb",
                        )
                    ] += 1
                elif (
                    member in VERBS | {"request"}
                    and head
                    and any(head.endswith(s) for s in ("client", "session", "http"))
                    and head not in clients
                ):
                    out[("?", "other receiver named client/session")] += 1
            # environment reads
            if d in ("os.getenv", "getenv"):
                out[("env", "os.getenv")] += 1
            elif d in ("os.environ.get", "environ.get"):
                out[("env", "os.environ.get")] += 1
            elif d in ("os.environ.setdefault", "environ.setdefault", "os.environ.pop"):
                out[("env", "os.environ.setdefault/pop")] += 1
        elif isinstance(n, ast.Subscript) and dotted(n.value) in ("os.environ", "environ"):
            out[
                ("env", "os.environ[...] " + ("write" if isinstance(n.ctx, ast.Store) else "read"))
            ] += 1
        elif (
            isinstance(n, ast.Compare)
            and any(isinstance(o, (ast.In, ast.NotIn)) for o in n.ops)
            and any(dotted(c) in ("os.environ", "environ") for c in n.comparators)
        ):
            out[("env", "'X' in os.environ")] += 1

    bases: dict[str, list[str]] = {}
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            bases[n.name] = [b for b in (dotted(x) for x in n.bases) if b]
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and any(
            b.split(".")[-1] == "BaseSettings" or b.split(".")[-1] in settings
            for b in (dotted(x) or "" for x in n.bases)
        ):
            fields = [
                s.target.id
                for s in n.body
                if isinstance(s, ast.AnnAssign)
                and isinstance(s.target, ast.Name)
                and not s.target.id.startswith("_")
                and s.target.id != "model_config"
                and "ClassVar" not in (ast.unparse(s.annotation))
            ]
            settings[n.name] = len(fields)
            guard_names.update(fields)


def guards(root: Path, names: set[str]) -> collections.Counter:
    """If/IfExp/assert tests whose expression reads an attribute named like a settings field."""
    c: collections.Counter = collections.Counter()
    for p in files(root):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, ValueError):
            continue
        for n in ast.walk(tree):
            if isinstance(n, (ast.If, ast.IfExp, ast.Assert, ast.While)):
                reads = [
                    a for a in ast.walk(n.test) if isinstance(a, ast.Attribute) and a.attr in names
                ]
                if reads:
                    c["guards reading a settings-field-named attribute"] += 1
                    if any(
                        dotted(a.value)
                        and dotted(a.value).split(".")[-1]
                        in ("settings", "config", "conf", "cfg", "SETTINGS", "CONFIG")
                        for a in reads
                    ):
                        c["... of which on settings/config receiver"] += 1
    return c


for arg in sys.argv[1:]:
    root = Path(arg)
    out: collections.Counter = collections.Counter()
    settings: dict[str, int] = {}
    names: set[str] = set()
    nfiles = 0
    for p in files(root):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, ValueError):
            continue
        nfiles += 1
        scan(tree, out, settings, names)
    print(f"== {root} ({nfiles} files)")
    for (lib, form), n in sorted(out.items()):
        print(f"  {lib:9} {form:40} {n}")
    print(f"  settings classes: {len(settings)}, fields: {sum(settings.values())}  {settings}")
    for k, v in guards(root, names).items():
        print(f"  {k}: {v}")
