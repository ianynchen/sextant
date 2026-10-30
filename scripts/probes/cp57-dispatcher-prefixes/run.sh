#!/usr/bin/env bash
# CP-57: build both Spring Boot 3.5.14 apps, start each on a free port, request every
# ordering of every subset of the candidate prefixes (/c /m /j /w) for every handler,
# print the paths that answered 2xx. Stops each app on exit.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
export JAVA_HOME="${JAVA_HOME:-$(brew --prefix openjdk@21)}"
PIDS=()
trap 'for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null; done' EXIT

free_port() { python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])'; }

# every ordered selection of the prefixes, including none
prefix_combos() {
python3 - "$@" <<'P'
import itertools, sys
ps = sys.argv[1:]
print("")
for n in range(1, len(ps) + 1):
    for c in itertools.permutations(ps, n):
        print("".join(c))
P
}

probe() { # name dir jar handlers... ; prefixes via PREFIXES env
  local name=$1 dir=$2 jar=$3; shift 3
  (cd "$HERE/$dir" && mvn -q -DskipTests package) || { echo "BUILD FAILED $name"; return 1; }
  local port; port=$(free_port)
  "$JAVA_HOME/bin/java" -jar "$HERE/$dir/target/$jar" --server.port="$port" --server.address=127.0.0.1 \
    >"$HERE/$dir/target/run.log" 2>&1 &
  local pid=$!; PIDS+=("$pid")
  for _ in $(seq 1 90); do
    curl -s -o /dev/null "http://127.0.0.1:$port/" && break
    kill -0 "$pid" 2>/dev/null || { echo "APP DIED $name"; tail -30 "$HERE/$dir/target/run.log"; return 1; }
    sleep 1
  done
  echo "== $name (port $port)"
  local combos; combos=$(prefix_combos $PREFIXES)
  for h in "$@"; do
    echo "-- $h"
    while IFS= read -r pre; do
      code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port${pre}${h}")
      case "$code" in 2*) echo "  $code ${pre}${h}";; esac
    done <<<"$combos"
  done
  kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
}

PREFIXES="/c /m /j" probe servlet servlet cp57-servlet-0.jar /mvc /fn /legacy /jersey /actuator/health
PREFIXES="/c /w" probe reactive reactive cp57-reactive-0.jar /flux /fnflux /gw/x /actuator/health
