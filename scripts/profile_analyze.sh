#!/usr/bin/env bash
# Cold then warm `sextant module analyze` per module: wall seconds, peak RSS of the whole
# process tree (the JVM extractor is a child on Java corpora) and the cache size.
#   scripts/profile_analyze.sh <module-path>...
set -euo pipefail
cd "$(dirname "$0")/.."
# Relative module paths resolve against the repo root (the cd above). A cold run REMOVES the
# module's .sextant and .sextant-enrichment.json first. Sizes are MiB (ps RSS / 1024).
REPO=$PWD
if [ -x "$REPO/.venv/bin/sextant" ]; then BIN=$REPO/.venv/bin/sextant; else BIN=sextant; fi

# Sum of RSS (MB) over a pid and all its descendants, from one `ps` snapshot.
tree_rss_mb() {
    ps -axo pid=,ppid=,rss= | awk -v root="$1" '
        { ppid[$1] = $2; rss[$1] = $3 }
        END { for (p in rss) { q = p; while (q != "" && q != 0) { if (q == root) { s += rss[p]; break } q = ppid[q] } }
              printf "%.2f", s / 1024 } '
}

run() { # module -> "wall peakMB"
    local out; out=$(mktemp)
    ( /usr/bin/time -p "$BIN" module analyze "$1" >/dev/null 2>"$out" ) &
    local pid=$! peak=0 cur
    while kill -0 "$pid" 2>/dev/null; do
        # the subshell's tree includes the timed sextant process and its children
        cur=$(tree_rss_mb "$pid")
        peak=$(awk -v a="$cur" -v b="$peak" 'BEGIN { print (a > b) ? a : b }')
        sleep 0.3
    done
    wait "$pid" || { cat "$out" >&2; exit 1; }
    echo "$(awk '/^real/ { print $2 }' "$out") $peak"
    rm -f "$out"
}

printf '%-34s %8s %8s %8s %8s %7s\n' module cold_s cold_MiB warm_s warm_MiB cache
for m in "$@"; do
    rm -rf "$m/.sextant" "$m/.sextant-enrichment.json"
    read -r cw cp <<<"$(run "$m")"
    read -r ww wp <<<"$(run "$m")"
    printf '%-34s %8s %8.0f %8s %8.0f %7s\n' "$m" "$cw" "$cp" "$ww" "$wp" "$(du -sh "$m/.sextant" | cut -f1)"
done
