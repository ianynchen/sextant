"""Measure the GENERAL case: every bean that exists conditionally, and every row derived from it.

Read-only over each analysed real-project workspace. Two ways a row ties to a conditional bean:
  way 1 — the row's own code is in a class whose class-level annotation is a condition
          (or the row's code IS a conditional method, e.g. a @Profile @Bean RouterFunction);
  way 2 — the row's code is in a class that a conditional @Bean method constructs
          (directly conditional, or inside a conditional @Configuration class).
"""

import collections
import glob
import json
import re
import sys

import duckdb

COND = re.compile(
    r"^org/springframework/(context/annotation/(Profile|Conditional)|boot/autoconfigure/condition/ConditionalOn\w+)#$"
)
BEAN = "org/springframework/context/annotation/Bean#"
CONFIG = "org/springframework/context/annotation/Configuration#"
STEREO = {
    f"org/springframework/{p}#"
    for p in (
        "stereotype/Component",
        "stereotype/Service",
        "stereotype/Repository",
        "stereotype/Controller",
        "web/bind/annotation/RestController",
        "web/bind/annotation/ControllerAdvice",
        "web/bind/annotation/RestControllerAdvice",
        "context/annotation/Configuration",
    )
}


def bare(s):
    return None if s is None else s.rsplit(" ", 1)[-1]


def owner(s):
    b = bare(s)
    return None if b is None or "#" not in b else b[: b.index("#") + 1]


def outer(t):  # a nested/anonymous/lambda-holding class's outermost type
    return (
        None
        if t is None
        else t.split("$", 1)[0] + ("" if t.split("$", 1)[0].endswith("#") else "#")
    )


roots = sorted(
    {
        p.rsplit("/.sextant/", 1)[0]
        for p in glob.glob(sys.argv[1] + "/**/.sextant/workspace.duckdb", recursive=True)
        if "/bundles/" not in p and "-at-" not in p
    }
)
T = collections.Counter()
ann_by_name = collections.Counter()
per_module = []
for root in roots:
    c = duckdb.connect()
    try:
        c.execute(f"ATTACH '{root}/.sextant/workspace.duckdb' AS w (READ_ONLY)")
        anns = c.execute("select target, annotation, args from w.annotations").fetchall()
    except duckdb.Error as e:  # a workspace from before a schema change: reported, skipped
        print("skip", root, type(e).__name__)
        continue
    by_target = collections.defaultdict(set)
    for target, a, _ in anns:
        by_target[bare(target)].add(a)
    cond_classes, cond_methods, cond_bean_methods, cond_configs = set(), set(), set(), set()
    for t, names in by_target.items():
        conds = {a for a in names if a and COND.match(a)}
        if not conds:
            continue
        for a in conds:
            ann_by_name[a.rsplit("/", 1)[-1]] += 1
        if t.endswith("#"):
            cond_classes.add(t)
            if CONFIG in names:
                cond_configs.add(t)
        else:
            cond_methods.add(t)
            if BEAN in names:
                cond_bean_methods.add(t)
    # every @Bean method inside a conditional @Configuration class is conditional too
    bean_methods = {t for t, n in by_target.items() if BEAN in n and not t.endswith("#")}
    inherited = {m for m in bean_methods if owner(m) in cond_classes}
    factories = cond_bean_methods | inherited
    # rows and their code symbols
    rows = []
    for d, h, cl in c.execute("select direction, handler, caller from w.endpoints").fetchall():
        rows.append(("endpoint-" + d, [x for x in (h, cl) if x]))
    for (h,) in c.execute("select handler from w.scheduled_work").fetchall():
        rows.append(("schedule", [h] if h else []))
    for h, adv in c.execute("select handler, advice from w.error_handlers").fetchall():
        rows.append(("error-handler", [x for x in (h, adv) if x]))
    # what each factory constructs
    constructed_by = collections.defaultdict(set)  # class -> factories constructing it
    unconditional_new = collections.defaultdict(set)
    for caller, target in c.execute(
        "select caller, target from w.call_edges where target like '%#<init>(%'"
    ).fetchall():
        cls = owner(target)
        cb = bare(caller)
        if cb in factories:
            constructed_by[cls].add(cb)
        elif owner(cb) != cls:
            unconditional_new[cls].add(cb)
    scanned_too = {t for t, n in by_target.items() if t.endswith("#") and n & STEREO}
    w1 = collections.Counter()
    w2 = collections.Counter()
    w2_ambig = collections.Counter()
    seen_rows = 0
    for kind, syms in rows:
        seen_rows += 1
        owners = {outer(owner(s)) for s in syms} | {owner(s) for s in syms}
        if owners & cond_classes or {bare(s) for s in syms} & cond_methods:
            w1[kind] += 1
            continue
        hit = [o for o in owners if o in constructed_by]
        if hit:
            if any(unconditional_new.get(o) or o in scanned_too for o in hit):
                w2_ambig[kind] += 1
            else:
                w2[kind] += 1
    m = {
        "module": root.replace(sys.argv[1] + "/", ""),
        "cond_classes": len(cond_classes),
        "cond_configs": len(cond_configs),
        "cond_methods": len(cond_methods),
        "cond_bean_methods": len(cond_bean_methods),
        "inherited_bean_methods": len(inherited),
        "rows": seen_rows,
        "way1": sum(w1.values()),
        "way2": sum(w2.values()),
        "way2_ambiguous": sum(w2_ambig.values()),
        "way1_by_kind": dict(w1),
        "way2_by_kind": dict(w2),
        "ambiguous_by_kind": dict(w2_ambig),
    }
    per_module.append(m)
    for k in (
        "cond_classes",
        "cond_configs",
        "cond_methods",
        "cond_bean_methods",
        "inherited_bean_methods",
        "rows",
        "way1",
        "way2",
        "way2_ambiguous",
    ):
        T[k] += m[k]
    for k, v in w1.items():
        T["way1:" + k] += v
    for k, v in w2.items():
        T["way2:" + k] += v
    for k, v in w2_ambig.items():
        T["ambig:" + k] += v
    c.close()
for m in per_module:
    if m["cond_classes"] or m["cond_methods"]:
        print(json.dumps(m))
print("\nmodules", len(per_module))
print(json.dumps(dict(T), indent=1))
print("annotations", dict(ann_by_name.most_common()))
