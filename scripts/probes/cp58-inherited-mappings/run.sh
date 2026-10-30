#!/usr/bin/env bash
# CP-58: build four apps (Spring MVC, Jersey, Quarkus REST, Micronaut), start each on a free
# port, request every candidate path, print the status codes. Stops each app on exit.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
export JAVA_HOME="${JAVA_HOME:-$(brew --prefix openjdk@21)}"
PIDS=()
trap 'for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null; done' EXIT

free_port() { python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])'; }

probe() { # name dir launch-command-with-@PORT@
  local name=$1 dir=$2; shift 2
  (cd "$HERE/$dir" && mvn -q -DskipTests package) || { echo "BUILD FAILED $name"; return 1; }
  local port; port=$(free_port)
  local args=("${@//@PORT@/$port}")
  (cd "$HERE/$dir" && exec "${args[@]}") >"$HERE/$dir/target/run.log" 2>&1 &
  local pid=$!; PIDS+=("$pid")
  for _ in $(seq 1 90); do
    curl -s -o /dev/null "http://127.0.0.1:$port/" && break
    kill -0 "$pid" 2>/dev/null || { echo "APP DIED $name"; tail -30 "$HERE/$dir/target/run.log"; return 1; }
    sleep 1
  done
  echo "== $name (port $port)"
  for c in "GET /orders/list" "POST /orders" "GET /products/list" "GET /products/all" \
           "POST /products" "GET /base/list" "POST /base" "GET /sub/list" "POST /sub"; do
    set -- $c
    code=$(curl -s -X "$1" -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port$2")
    echo "  $code $1 $2"
  done
  kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
}

J="$JAVA_HOME/bin/java"
probe spring-mvc spring "$J" -jar target/cp58-spring-0.jar --server.port=@PORT@ --server.address=127.0.0.1
probe jersey jersey "$J" -jar target/cp58-jersey-0.jar --server.port=@PORT@ --server.address=127.0.0.1
probe quarkus-rest quarkus "$J" -Dquarkus.http.port=@PORT@ -Dquarkus.http.host=127.0.0.1 -jar target/quarkus-app/quarkus-run.jar
probe micronaut micronaut "$J" -Dmicronaut.server.port=@PORT@ -Dmicronaut.server.host=127.0.0.1 -jar target/cp58-micronaut-0.jar
