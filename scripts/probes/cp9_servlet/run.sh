#!/usr/bin/env bash
# CP-9 harness (2O Task 7b Step 0) — see ../cp9_servlet_shapes.md for the
# question, the version scope, and the recorded verdict.
#
# Two halves, one table. The LIVE half builds the probe webapp once per Tomcat
# version named below, deploys it through `Tomcat.addWebapp` so the CONTAINER's
# own annotation deployment scan is what discovers every `@WebServlet`, and
# curls one request per row: which patterns are served, which verbs a `doXxx`
# override reaches, what `HttpServlet` dispatches with no override at all, and
# what a class overriding `service()` or extending `GenericServlet` serves
# instead. The FACT half runs the committed extractor over the very same
# build's `target/classes` and prints, verbatim, what the `@WebServlet`
# annotation, the `doXxx` signature and the `superclass` edge look like in the
# fact stream.
#
# No Spring: the rule under test is the Servlet specification's and
# `HttpServlet`'s own, which is what the servlet catalogs model, and a
# framework wrapped around the container would add a second registration route
# confounding the one being measured.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADERS COME FROM THE RUNS' OWN
# OUTPUT (GUIDELINES §5.4, and CP-5's own failure it exists to prevent). The
# probe asks its OWN ServletContext which container is running it and which
# servlet API package it loaded, and prints both; the harness parses that line
# out of each process's log, files every cell under the container the process
# itself named, and ABORTS when either half disagrees with what this loop asked
# for. A version read out of the loop variable can be wrong; one read out of
# the running process cannot.
#
# The fact-half cells are filed under the same identity because they are read
# from the class files THAT build produced: a probe class compiles against the
# servlet API of the container it will run on, so a fact-shape answer is
# evidence about that build and not about the other one either.
#
# Needs a JDK 21+, Maven, and network on first run (Tomcat comes from Maven
# Central and is cached in ~/.m2 afterwards). Not a test: no test in this
# repository runs it, and NFR-1's no-network rule is about the suite, not about
# evidence gathering.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
EXTRACTOR="$REPO/src/sextant/extractor-jvm/sextant-extractor.jar"

# The containers this probe's verdict is scoped to (§5.4), as
# `<version>:<servlet API spelling>`. Two Tomcat MAJORS shipping the `jakarta`
# spelling at different Servlet levels (6.0 and 6.1) — two independent
# `HttpServlet` implementations, which is where implicit verb dispatch actually
# lives — and Tomcat 9, which ships the SAME API under `javax.servlet` and is
# the container the legacy estate the second catalog exists for actually runs
# on. Widening the verdict means adding a version here and re-running, never
# assuming.
VERSIONS=("10.1.50:jakarta" "11.0.24:jakarta" "9.0.121:javax")
PORT=18095
# A SECOND connector on the next port, differing in exactly one setting:
# `allowTrace`. TRACE is refused by a Tomcat connector before dispatch unless
# it is set, and that is deployment configuration a repository cannot see — so
# measuring the specification's own `service()` -> `doTrace` dispatch needs a
# connector that permits the method. Both connectors serve the same webapp, so
# the pair isolates the connector setting from everything else.
TRACE_PORT=$((PORT + 1))

# Filled by `probe`/`record`, read by `emit_table`. Flat `<row>|<field>|<value>`
# records rather than associative arrays, because macOS ships bash 3.2 and this
# harness has to run where the evidence is gathered. A CELL can only exist for a
# container some JVM actually reported running.
CELLS=()    # "<row>|<observed container>|<value>"
ROWS=()     # "<row>|<label>", one per row, in first-record order
OBSERVED=() # the container versions the RUNS reported, in probe order

# The container of the process being probed right now, and the servlet API
# package it reported loading — both set by `identify` from that process's own
# PROBE-IDENTITY line, never from the loop variable.
RUNNING=""
RUNNING_API=""

identify() { # <logfile> <version requested> <api package requested>
  local line container api
  line="$(grep -m1 '^PROBE-IDENTITY ' "$1" || true)"
  if [ -z "$line" ]; then
    echo "FATAL: no PROBE-IDENTITY line in $1 — the run cannot identify itself" >&2
    exit 1
  fi
  container="$(printf '%s\n' "$line" | sed -n 's/.*container=[^0-9]*\([0-9][0-9.]*\).*/\1/p')"
  api="$(printf '%s\n' "$line" | sed -n 's/.*servletApi=\([a-z.]*\).*/\1/p')"
  if [ "$container" != "$2" ]; then
    # CP-5's exact failure, fatal rather than silent: the container that
    # answered is not the one this iteration asked for.
    echo "FATAL: asked for Tomcat $2, the process reported $container (stale build?)" >&2
    exit 1
  fi
  if [ "$api" != "$3" ]; then
    # The same failure one level down: the javax column is a claim about a
    # SPELLING, so a run that loaded the other one must not be filed under it.
    echo "FATAL: asked for the $3 spelling, the process loaded $api (stale sources?)" >&2
    exit 1
  fi
  RUNNING="$container"
  RUNNING_API="$api"
  echo "identity $line"
}

remember() { # <row> <label>
  local entry known=0
  for entry in ${ROWS[@]+"${ROWS[@]}"}; do
    [ "${entry%%|*}" = "$1" ] && known=1
  done
  [ "$known" = 1 ] || ROWS[${#ROWS[@]}]="$1|$2"
}

record() { # <row> <label> <value>
  CELLS[${#CELLS[@]}]="$1|$RUNNING|$3"
  remember "$1" "$2"
}

probe() { # <row> <verb> <url> [note]
  local row=$1 verb=$2 url=$3 note=${4:-} code
  # `--head` for HEAD rather than `-X HEAD`: the latter sends the request and
  # then waits for a body a correct HEAD response never has, so it times out
  # and would record a transport failure where the container answered fine.
  if [ "$verb" = HEAD ]; then
    code="$(curl -s -o /dev/null -m 5 -w '%{http_code}' --head "http://localhost:$PORT$url")"
  else
    code="$(curl -s -o /dev/null -m 5 -w '%{http_code}' -X "$verb" "http://localhost:$PORT$url")"
  fi
  printf '%-3s %-8s %-24s -> %s\n' "$row" "$verb" "$url" "$code"
  record "$row" "\`$verb $url\`${note:+ — $note}" "$code"
}

probe_allow() { # <row> <url> <note>
  local row=$1 url=$2 note=$3 allow
  allow="$(curl -s -m 5 -D - -o /dev/null -X OPTIONS "http://localhost:$PORT$url" \
    | sed -n 's/^[Aa]llow: *//p' | tr -d '\r')"
  printf '%-3s %-8s %-24s -> %s\n' "$row" "Allow" "$url" "$allow"
  record "$row" "\`Allow\` header on \`OPTIONS $url\` — $note" "\`${allow}\`"
}

probe_trace() { # <row> <url> <note> — the connector that PERMITS the method
  local row=$1 url=$2 note=$3 code
  code="$(curl -s -o /dev/null -m 5 -w '%{http_code}' -X TRACE "http://localhost:$TRACE_PORT$url")"
  printf '%-3s %-8s %-24s -> %s\n' "$row" "TRACE+" "$url" "$code"
  record "$row" "\`TRACE $url\` on a connector with \`allowTrace=\"true\"\` — $note" "$code"
}

cell() { # <row> <container> -> the value recorded for that pair, or an em dash
  local entry
  for entry in ${CELLS[@]+"${CELLS[@]}"}; do
    case "$entry" in "$1|$2|"*) echo "${entry#"$1|$2|"}"; return ;; esac
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
  echo "=== generated observation table — transcribe verbatim into cp9_servlet_shapes.md ==="
  echo "$header"
  echo "$divider"
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

for entry in "${VERSIONS[@]}"; do
  version="${entry%%:*}"
  spelling="${entry##*:}"
  echo "=== requested Tomcat $version, the $spelling.servlet spelling ==="
  # `clean` is not decoration — CP-5's mislabelled column came from its
  # absence: without it a second iteration reuses the FIRST version's classes
  # and every row below silently re-measures container one. `identify`
  # cross-checks the running container anyway rather than trusting this line.
  mvn -q clean -Dtomcat.version="$version"

  # The `javax` column compiles the SAME committed sources under the other
  # package spelling: Tomcat 9 ships this API as `javax.servlet`, and one
  # rename is the entire difference between the two. Generated rather than
  # committed twice, so "identical modulo the spelling" stays true by
  # construction — which is precisely the claim the column measures.
  sources="src/main/java"
  if [ "$spelling" = javax ]; then
    sources="target/generated-javax/java"
    mkdir -p "$sources/probe"
    for file in src/main/java/probe/*.java; do
      sed 's/jakarta\.servlet/javax.servlet/g' "$file" >"$sources/probe/$(basename "$file")"
    done
  fi
  mvn -q -Dtomcat.version="$version" -Dprobe.sources="$sources" package
  mvn -q dependency:build-classpath -Dmdep.outputFile=target/cp.txt \
    -Dtomcat.version="$version" -Dprobe.sources="$sources"

  # A real webapp layout, because `Tomcat.addWebapp` is what runs the
  # container's own annotation scan and it scans `/WEB-INF/classes`. No
  # `web.xml` is written: its absence is the Servlet 3.0+ shape under test.
  rm -rf target/docbase target/mcbase target/tomcat-base
  mkdir -p target/docbase/WEB-INF/classes
  cp -R target/classes/probe target/docbase/WEB-INF/classes/

  # THE SAME CLASSES A SECOND TIME, under a descriptor declaring
  # `metadata-complete="true"` — the shape in which the specification switches
  # the annotation deployment scan off wholesale, so that every `@WebServlet`
  # in the module is inert. Deployed beside the first webapp rather than
  # instead of it, so the only difference between the two is the descriptor.
  # The schema is the one that build's own servlet level ships; a descriptor
  # naming a `web-app` version below 3.0 would suppress the scan for a second,
  # different reason and is not what this row measures.
  mkdir -p target/mcbase/WEB-INF/classes
  cp -R target/classes/probe target/mcbase/WEB-INF/classes/
  if [ "$spelling" = javax ]; then
    mc_namespace="http://xmlns.jcp.org/xml/ns/javaee"
    mc_version="4.0"
  else
    mc_namespace="https://jakarta.ee/xml/ns/jakartaee"
    mc_version="6.0"
  fi
  cat >target/mcbase/WEB-INF/web.xml <<XML
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="$mc_namespace"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="$mc_namespace $mc_namespace/web-app_${mc_version//./_}.xsd"
         version="$mc_version"
         metadata-complete="true">
</web-app>
XML

  java -cp "target/classes:$(cat target/cp.txt)" probe.ProbeApplication \
    "$PORT" target/docbase target/mcbase >"target/run-$version.log" 2>&1 &
  pid=$!
  trap 'kill $pid 2>/dev/null || true' EXIT
  until curl -s -o /dev/null -m 2 "http://localhost:$PORT/getonly"; do sleep 1; done
  identify "target/run-$version.log" "$version" "$spelling.servlet"
  OBSERVED[${#OBSERVED[@]}]="$RUNNING"

  # --- the address: which patterns the annotation registers ----------------
  probe 1  GET     /multi-a      "\`urlPatterns = {\"/multi-a\", \"/multi-b\"}\`"
  probe 2  GET     /multi-b      "the same class's second pattern"
  probe 3  GET     /aliased      "\`@WebServlet(\"/aliased\")\`, the \`value\` spelling"
  # --- the verb: which doXxx override reaches which method -----------------
  probe 4  GET     /verbs        "\`doGet\` overridden"
  probe 5  POST    /verbs        "\`doPost\` overridden"
  probe 6  PUT     /verbs        "no \`doPut\` on the class"
  # --- implicit dispatch, the ruling CP-9 exists to settle ------------------
  probe 7  HEAD    /getonly      "\`doGet\` only — implicit"
  probe 8  OPTIONS /getonly      "\`doGet\` only — implicit"
  probe_allow 9    /getonly      "\`doGet\` only"
  probe 10 TRACE   /getonly      "\`doGet\` only — implicit"
  # --- the same three verbs, EXPLICITLY overridden --------------------------
  probe 11 HEAD    /explicit     "\`doHead\` overridden"
  probe 12 OPTIONS /explicit     "\`doOptions\` overridden"
  probe 13 TRACE   /explicit     "\`doTrace\` overridden"
  # --- the shapes where the verb map does not apply -------------------------
  probe 14 GET     /service-only "\`service()\` overridden, no \`doXxx\`"
  probe 15 PUT     /service-only "\`service()\` overridden, no \`doXxx\`"
  probe 16 GET     /generic      "\`GenericServlet\` subclass"
  probe 17 PUT     /generic      "\`GenericServlet\` subclass"
  # --- the language rule, and the missing annotation ------------------------
  probe 18 GET     /decoy        "only \`doGet(String, HttpServletResponse)\`"
  probe 19 GET     /unannotated  "extends \`HttpServlet\`, no \`@WebServlet\`"
  # --- what the CONNECTOR refuses versus what the SPECIFICATION dispatches --
  record 30 "the servlet API package the running container reported loading" \
    "\`$RUNNING_API\`"
  probe_trace 31 /explicit "\`doTrace\` overridden"
  probe_trace 32 /getonly  "no \`doTrace\` — \`HttpServlet\`'s own"
  # --- the descriptor that switches the annotation scan off -----------------
  probe 33 GET /metadata-complete/getonly \
    "the same classes under \`metadata-complete=\"true\"\`"

  kill $pid 2>/dev/null || true
  wait $pid 2>/dev/null || true
  trap - EXIT

  # --- the fact stream, over the very build that just ran -------------------
  rm -rf target/facts
  java -jar "$EXTRACTOR" \
    --module-id sextant.probe:cp9-servlet --coordinates sextant.probe/cp9-servlet \
    --version 0.0.1 --classes target/classes --out target/facts
  while IFS='|' read -r row value; do
    printf '%-3s %s\n' "$row" "$value"
    case "$row" in
      20) label="\`@WebServlet\`'s own fact target" ;;
      21) label="\`args\` of \`urlPatterns = {\"/multi-a\", \"/multi-b\"}\`" ;;
      22) label="\`args\` of \`@WebServlet(\"/aliased\")\`" ;;
      23) label="\`args\` of \`urlPatterns = \"/verbs\"\` (one element)" ;;
      24) label="\`GetOnlyServlet#doGet\`'s recorded \`visibility\`" ;;
      25) label="\`GetOnlyServlet#doGet\`'s signature parameter symbols" ;;
      26) label="\`DecoyOverloadServlet#doGet\`'s signature parameter symbols" ;;
      27) label="\`GetOnlyServlet\`'s own \`superclass\`" ;;
      28) label="\`GenericProbeServlet\`'s own \`superclass\`" ;;
      29) label="\`args\` on \`UnannotatedServlet\` (no annotation written)" ;;
      *)  label="row $row" ;;
    esac
    record "$row" "$label" "\`$value\`"
  done < <(python3 facts.py target/facts "$RUNNING_API")
done

emit_table
