# Python performance baseline (OI-208, plan 1, task 0)

Date: 2026-11-06. Machine: the development Mac. Python 3.15.2.

## Question

Can a Python scanner meet the budget in spec section 5?
Cold analysis: ceiling 300 s, target 60 s. Warm analysis: ceiling 30 s, target 10 s.
Test project: `examples/py-polar/server`.

## How it was measured

- Probe: `scripts/probes/python_timing.py <path>`. It reads, parses (`ast.parse`) and walks every
  `.py` file once. It never imports the scanned code. Run with `python -I`.
- The probe counts every `ast.Call` node. It counts test files too.
- JVM rate: the workspaces store no timing. So I timed a real run. I deleted
  `examples/mall/mall-admin/.sextant`, then ran
  `sextant module analyze examples/mall/mall-admin`. Wall time: 6.14 s (scan 1.5 s, resolve 4.1 s).
  The workspace holds 25,057 call sites. Rate: 25,057 / 6.14 = about 4,080 call sites per second.
  This includes about 1 s of program start.

## Numbers

| Tree | Files | Call sites (all) | Cold read+parse+walk | Warm (hash cache) |
|---|---|---|---|---|
| examples/py-polar/server | 2,053 | 113,448 | 1.64 s | 0.03 s |
| src/sextant | 161 | 18,552 | 0.28 s | 0.00 s |

- Parse speed: about 65,000 to 69,000 call sites per second, on one core, no parallelism.
- JVM resolver: about 4,080 call sites per second.

Two counts differ from the spec. The spec says 2,382 files and 47,716 call sites.
This probe finds 2,053 `.py` files (1,411 outside `tests/` and `test/`) and 113,448 `ast.Call`
nodes. The spec's counts probably use another filter. I use the spec's 47,716 for the projection,
as the brief says. Using 113,448 is shown as a worst case.

## Projection for polar, cold

- Parse and walk: 1.6 s (measured; this already covers all 2,053 files).
- Resolve at the JVM rate: 47,716 / 4,080 = 11.7 s.
- Total: about 13 s.
- Worst case, 113,448 call sites at the JVM rate: 27.8 s + 1.6 s = about 29 s.

## Verdict

- The 60 s target is reachable. The projection is 13 s, which is 4.6 times under the target.
  The worst case (29 s) is still under the target.
- The 300 s ceiling is not at risk.
- Warm analysis: reading and hashing all files takes 0.03 s. The 10 s warm target is limited
  by the resolver, not by the scanner. If the resolver is not cached, warm is about 12 s, so
  a resolver cache or a smaller re-resolve is needed to meet the 10 s warm target. The 30 s
  warm ceiling is met either way.

## Caveats

- The JVM rate is a proxy. The Python resolver will bind receivers across 257 packages
  and may cost more per call site. The budget has room for about 4.6 times more cost per call site.
- The JVM run is from one machine and one project. Re-measure after each task that changes a pass.
