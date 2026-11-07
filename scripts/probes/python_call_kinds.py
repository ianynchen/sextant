"""Rough split of call sites by what is needed to know the target.

`--workspace <dir>...` prints the same question answered by the real resolver instead: every
`call_site` of an analysed workspace (`sextant module analyze <path> --workspace <dir>`), split
by what the scanner wrote (before receiver binding) and by what the resolver bound (after it).
"""

import ast
import builtins
import collections
import pathlib
import sys

# A site whose receiver the scanner left to the resolver and that is still unbound after it.
_NO_TARGET_NO_REASON = "no owner and no reason"


def _workspace_table(directory: pathlib.Path) -> None:
    """The call table of one workspace, before and after `bind_receivers`, one line per
    kind, counted per call SITE (`caller`, `ordinal`), never per binding row."""
    import duckdb  # only this mode needs it; the AST mode runs on any Python

    path = directory if directory.suffix == ".duckdb" else directory / "workspace.duckdb"
    db = duckdb.connect(str(path), read_only=True)
    before = db.execute(
        "SELECT CASE WHEN owner IS NULL THEN 'owner left to the resolver'"
        " ELSE 'owner written: ' || invoke_kind END, count(*)"
        " FROM call_sites GROUP BY ALL ORDER BY 2 DESC"
    ).fetchall()
    # A site's binding rows share one site-level `resolution` (schema.sql `bound_receivers`),
    # except a `partial` site, whose unbound paths are `unresolved` rows beside it.
    after = db.execute(
        f"""
        WITH sites AS (
            SELECT s.caller, s.ordinal, s.owner,
                   bool_or(b.owner IS NOT NULL) AS bound,
                   any_value(b.resolution) FILTER (WHERE b.owner IS NOT NULL) AS resolution,
                   count(DISTINCT b.reason) AS reasons, any_value(b.reason) AS reason,
                   count(b.caller) AS rows
            FROM call_sites s
            LEFT JOIN bound_receivers b ON b.caller = s.caller AND b.ordinal = s.ordinal
            GROUP BY s.caller, s.ordinal, s.owner
        )
        SELECT CASE
            WHEN owner IS NOT NULL THEN 'owner written by the scanner'
            WHEN bound THEN 'bound: ' || resolution
            WHEN rows = 0 AND EXISTS (
                SELECT 1 FROM call_edges e
                WHERE e.caller = sites.caller AND e.ordinal = sites.ordinal
                  AND e.callee IS NOT NULL
            ) THEN 'a function value called (edge into its body)'
            WHEN reasons > 1 THEN 'unresolved: several reasons, one per path'
            WHEN reasons = 1 THEN 'unresolved: ' || reason
            ELSE '{_NO_TARGET_NO_REASON}' END, count(*)
        FROM sites GROUP BY ALL ORDER BY 2 DESC
        """
    ).fetchall()
    db.close()
    total = sum(count for _, count in before)
    print(f"== {directory}  ({total} call sites)")
    for title, rows in (("before receiver binding", before), ("after receiver binding", after)):
        print(f"   {title}")
        for name, count in rows:
            print(f"   {count:7d}  {100 * count / total:5.1f}%  {name}")


if sys.argv[1:2] == ["--workspace"]:
    for directory in sys.argv[2:]:
        _workspace_table(pathlib.Path(directory))
    raise SystemExit(0)

B = set(dir(builtins))
for root in sys.argv[1:]:
    k = collections.Counter()
    for path in pathlib.Path(root).rglob("*.py"):
        if any(s in path.parts for s in ("tests", "test", "migrations", "node_modules", ".venv")):
            continue
        try:
            tree = ast.parse(path.read_text(errors="ignore"))
        except SyntaxError:  # a file this Python cannot parse is not counted
            continue
        imported = set()
        toplevel = set()
        for n in tree.body:
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                for a in n.names:
                    imported.add((a.asname or a.name).split(".")[0])
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                toplevel.add(n.name)
            elif isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        toplevel.add(t.id)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            params = {
                a.arg: a.annotation for a in fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs
            }
            ctor = {}
            for n in ast.walk(fn):
                if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
                    for t in n.targets:
                        if isinstance(t, ast.Name):
                            ctor[t.id] = 1
                if isinstance(n, (ast.AnnAssign,)) and isinstance(n.target, ast.Name):
                    ctor[n.target.id] = 1
            for n in ast.walk(fn):
                if not isinstance(n, ast.Call):
                    continue
                f = n.func
                if isinstance(f, ast.Name):
                    k[
                        "builtin"
                        if f.id in B and f.id not in imported | toplevel
                        else "named function/class"
                    ] += 1
                elif isinstance(f, ast.Attribute):
                    v = f.value
                    if isinstance(v, ast.Name):
                        if v.id in ("self", "cls"):
                            k["self/cls method"] += 1
                        elif v.id in imported or v.id in toplevel:
                            k["module or class attribute"] += 1
                        elif v.id in params:
                            k[
                                "typed parameter"
                                if params[v.id] is not None
                                else "UNTYPED parameter"
                            ] += 1
                        elif v.id in ctor:
                            k["local set from a call"] += 1
                        else:
                            k["other local (loop var, with, etc.)"] += 1
                    elif (
                        isinstance(v, ast.Attribute)
                        and isinstance(v.value, ast.Name)
                        and v.value.id in ("self", "cls")
                    ):
                        k["self.field method"] += 1
                    elif isinstance(v, ast.Call):
                        k["chained call"] += 1
                    elif isinstance(v, ast.Constant):
                        k["literal method (str.format…)"] += 1
                    else:
                        k["other expression"] += 1
    t = sum(k.values())
    print(f"== {pathlib.Path(root).name}  ({t} calls)")
    for name, c in k.most_common():
        print(f"   {100 * c / t:5.1f}%  {name}")
