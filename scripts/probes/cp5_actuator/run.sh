#!/usr/bin/env bash
# CP-5 harness (2O Task 7 Step 0) — see ../cp5_actuator_paths.md for the
# question, the version scope, and the recorded verdict.
#
# Builds the probe app once per Boot version named below, runs it three ways on
# an embedded Tomcat, and curls one URL per row of the expectation table. Every
# probe prints `<row> <verb> <url> -> <status>` as it happens, and the run ends
# by printing the observation table itself, ready to be transcribed verbatim
# into the .md.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADERS COME FROM THE RUNS' OWN
# OUTPUT (2O Task 7 review, Critical 2). The shipped harness took a run's
# identity from the loop variable it had passed in, and a `package` without
# `clean` meant the second iteration re-ran the FIRST version's fat jar: eight
# observation cells recorded a `4.1.1` run that never happened. A version read
# out of the loop variable can be wrong; one read out of the process's own
# Spring Boot banner cannot. So each run parses `(vX.Y.Z)` from its own log,
# every status is filed under THAT version, and a run whose banner disagrees
# with the version requested aborts the harness instead of mislabelling a
# column.
#
# It also prints the discovery document of the exposed run AND of the
# default-exposure run, because two rows claim something stronger than a 404 —
# row 6, that the operation-less endpoint is absent from `GET /actuator`
# entirely, and rows 9-10, that the default exposure lists `health` and nothing
# else — and a claim a re-run cannot reproduce is not evidence.
#
# Needs a JDK 21+, Maven, and network on first run (the Boot artifacts are
# fetched from Maven Central and cached in ~/.m2 afterwards). Not a test: no
# test in this repository runs it, and NFR-1's no-network rule is about the
# suite, not about evidence gathering.
set -euo pipefail

cd "$(dirname "$0")"

# The two versions this probe's verdict is scoped to (§5.4). The base-path
# property name and the `/actuator` default are version-scoped, so widening
# the verdict means adding a version here and re-running, never assuming.
VERSIONS=("3.5.10" "4.1.1")
PORT=18085

# `management.endpoints.web.exposure.include=*` is passed per run rather than
# written into application.properties, because runs 3 measure what Boot's own
# DEFAULT exposure serves — and a value set in the app's own properties file
# would make that default unmeasurable from here.
EXPOSE_ALL="--management.endpoints.web.exposure.include=*"

# Filled by `probe`, read by `emit_table`. Flat `<row>|<field>|<value>` records
# rather than associative arrays, because macOS ships bash 3.2 and this harness
# has to run where the evidence is gathered. A CELL can only exist for a
# version some JVM actually reported booting.
CELLS=()    # "<row>|<observed version>|<status>"
ROWS=()     # "<row>|<label>", one per row, in first-probe order
OBSERVED=() # the versions the RUNS reported, in the order they were probed

# The version of the process being probed right now, set by `identify` from
# that process's own banner — never from the loop variable.
RUNNING=""

identify() { # <logfile> <version requested>
  local raw
  raw="$(grep -om1 '(v[0-9][0-9.]*[^)]*)' "$1" || true)"
  raw="${raw#(v}"
  raw="${raw%)}"
  if [ -z "$raw" ]; then
    echo "FATAL: no Spring Boot banner in $1 — the run cannot identify itself" >&2
    exit 1
  fi
  if [ "$raw" != "$2" ]; then
    # The exact failure the missing `clean` produced, now fatal rather than
    # silent: the jar that booted is not the jar this iteration asked for.
    echo "FATAL: asked for Boot $2, the process booted $raw (stale jar?)" >&2
    exit 1
  fi
  RUNNING="$raw"
  echo "banner  $1 -> Spring Boot $raw"
}

probe() { # <row> <verb> <url> <port> [note]
  local row=$1 verb=$2 url=$3 port=$4 note=${5:-} code known=0 entry
  code="$(curl -s -o /dev/null -m 5 -w '%{http_code}' -X "$verb" "http://localhost:$port$url")"
  printf '%-3s %-7s %-26s -> %s\n' "$row" "$verb" "$url" "$code"
  CELLS[${#CELLS[@]}]="$row|$RUNNING|$code"
  for entry in ${ROWS[@]+"${ROWS[@]}"}; do
    [ "${entry%%|*}" = "$row" ] && known=1
  done
  [ "$known" = 1 ] || ROWS[${#ROWS[@]}]="$row|\`$verb $url\`${note:+ — $note}"
}

cell() { # <row> <version> -> the status recorded for that pair, or an em dash
  local entry
  for entry in ${CELLS[@]+"${CELLS[@]}"}; do
    case "$entry" in "$1|$2|"*) echo "${entry##*|}"; return ;; esac
  done
  echo "—"
}

emit_table() {
  local header="| # | probe |" divider="|---|---|" v entry row label line
  for v in "${OBSERVED[@]}"; do
    header="$header $v |"
    divider="$divider---|"
  done
  echo
  echo "=== generated observation table — transcribe verbatim into cp5_actuator_paths.md ==="
  echo "$header"
  echo "$divider"
  # Rows are printed in ROW NUMBER order, not probe order: row 11 is measured
  # during run 1 but belongs at the end of the table.
  for row in $(printf '%s\n' "${ROWS[@]}" | cut -d'|' -f1 | sort -n); do
    label=""
    for entry in "${ROWS[@]}"; do
      [ "${entry%%|*}" = "$row" ] && label="${entry#*|}"
    done
    line="| $row | $label |"
    for v in "${OBSERVED[@]}"; do
      line="$line $(cell "$row" "$v") |"
    done
    echo "$line"
  done
}

for version in "${VERSIONS[@]}"; do
  echo "=== requested Spring Boot $version ==="
  # `clean` is not decoration. Without it the second loop iteration recompiles
  # nothing, `repackage` is a no-op over the jar the FIRST version already
  # produced, and every run below silently re-measures version one while this
  # script prints version two's header. That is exactly what the shipped
  # harness did, and it is why this line carries a comment — and why
  # `identify` above now cross-checks the banner rather than trusting it.
  mvn -q clean -DskipTests -Dboot.version="$version" package
  jar=target/cp5-actuator-0.0.1.jar

  # Run 1 — the default base path, everything exposed.
  java -jar "$jar" --server.port="$PORT" $EXPOSE_ALL \
    >"target/run-$version-default.log" 2>&1 &
  pid=$!
  trap 'kill $pid 2>/dev/null || true' EXIT
  until curl -s -o /dev/null -m 2 "http://localhost:$PORT/actuator"; do sleep 1; done
  identify "target/run-$version-default.log" "$version"
  OBSERVED[${#OBSERVED[@]}]="$RUNNING"
  probe 1  GET    /actuator/probe  "$PORT"
  probe 2  POST   /actuator/probe  "$PORT"
  probe 3  DELETE /actuator/probe  "$PORT"
  probe 4  PUT    /actuator/probe  "$PORT"
  probe 5  GET    /probe           "$PORT"
  probe 6  GET    /actuator/empty  "$PORT"
  probe 11 GET    /actuator/closed "$PORT" "\`defaultAccess = Access.NONE\`, exposure \`*\`"
  # Row 6's stronger half, captured rather than asserted: `empty` must not
  # appear in the discovery document at all.
  echo "discovery(exposed) $(curl -s -m 5 "http://localhost:$PORT/actuator")"
  kill $pid 2>/dev/null || true
  wait $pid 2>/dev/null || true

  # Run 2 — the base path overridden, which is the boundary this task records
  # rather than reads: nothing in Sextant reads `resolved_config` for an
  # annotation-derived row.
  java -jar "$jar" --server.port="$((PORT + 1))" $EXPOSE_ALL \
    --management.endpoints.web.base-path=/manage >"target/run-$version-basepath.log" 2>&1 &
  pid=$!
  until curl -s -o /dev/null -m 2 "http://localhost:$((PORT + 1))/manage"; do sleep 1; done
  identify "target/run-$version-basepath.log" "$version"
  probe 7 GET /manage/probe   "$((PORT + 1))" "\`base-path=/manage\`"
  probe 8 GET /actuator/probe "$((PORT + 1))" "\`base-path=/manage\`"
  kill $pid 2>/dev/null || true
  wait $pid 2>/dev/null || true

  # Run 3 — exposure left at Boot's OWN default, nothing else changed. This is
  # the second conjunct of the framework's rule (§8.1 rule 1): an `@Endpoint`
  # is served over HTTP only when it is ALSO web-exposed, and the default
  # includes `health` alone.
  java -jar "$jar" --server.port="$((PORT + 2))" \
    >"target/run-$version-default-exposure.log" 2>&1 &
  pid=$!
  until curl -s -o /dev/null -m 2 "http://localhost:$((PORT + 2))/actuator"; do sleep 1; done
  identify "target/run-$version-default-exposure.log" "$version"
  probe 9  GET /actuator/probe  "$((PORT + 2))" "exposure left at Boot's DEFAULT"
  probe 10 GET /actuator/health "$((PORT + 2))" "exposure left at Boot's DEFAULT"
  echo "discovery(default) $(curl -s -m 5 "http://localhost:$((PORT + 2))/actuator")"
  kill $pid 2>/dev/null || true
  wait $pid 2>/dev/null || true
  trap - EXIT
done

emit_table
