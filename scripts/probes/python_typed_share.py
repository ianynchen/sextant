"""Share of function inputs and returns with a written type, per project (2026-11-06 Python design §2)."""

import ast
import pathlib
import sys

for root in sys.argv[1:]:
    p = a = r = ra = f = 0
    for path in pathlib.Path(root).rglob("*.py"):
        if any(s in path.parts for s in ("tests", "test", "migrations", "node_modules", ".venv")):
            continue
        try:
            tree = ast.parse(path.read_text(errors="ignore"))
        except SyntaxError:  # a file this Python cannot parse is not counted
            continue
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                f += 1
                r += 1
                ra += n.returns is not None
                for arg in n.args.args + n.args.kwonlyargs + n.args.posonlyargs:
                    if arg.arg in ("self", "cls"):
                        continue
                    p += 1
                    a += arg.annotation is not None
    print(
        f"{pathlib.Path(root).name:30} functions {f:6}  params typed {100 * a // max(p, 1):3}%  returns typed {100 * ra // max(r, 1):3}%"
    )
