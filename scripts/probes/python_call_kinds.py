"""Rough split of call sites by what is needed to know the target."""

import ast
import builtins
import collections
import pathlib
import sys

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
