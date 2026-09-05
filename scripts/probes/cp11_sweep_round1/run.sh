#!/usr/bin/env bash
# CP-11 harness (principles sweep round-1 fix pass) — see
# ../cp11_sweep_round1.md for the questions, the version scope and the verdicts.
#
# THE QUESTIONS. Four framework rules the round-1 fix pass MIRRORS rather than
# approximates (DR-6, GUIDELINES §8.1): OkHttp's complete verb-setter set
# (`A-C2`), Spring MVC's server-side handler predicate (`A-C7`), which
# jakarta.websocket artifact declares which annotation and what each targets
# (`A-C1`), and what `Retrofit.create` does with a non-interface (`A-C6`). Every
# one of the four was previously encoded from documentation or memory.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADERS COME FROM THE JARS' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). Each artifact
# below names WHERE it writes its own version, and `probe.py` reads the VALUE
# out of the archive it opened; a jar whose self-report disagrees with the
# coordinate that resolved it ABORTS the run rather than filling a mislabelled
# column. Two artifacts write one nowhere at all — OkHttp has no manifest
# version and no `pom.properties`, so it is read out of the `ConstantValue` of
# `okhttp3.OkHttp.VERSION`; Retrofit writes none anywhere, and is declared
# `-` here so the run prints "assumed" instead of claiming a measurement.
#
# Needs a JDK (for `javap`), Maven, and network on first run; the jars are
# cached in ~/.m2 afterwards. Not a test: nothing in the suite runs it, and
# NFR-1's no-network rule governs the suite, not evidence gathering.
# `tests/architecture/test_sweep_round1_framework_rules.py` is the offline half,
# and it pins the shipped catalogs and engines against the table this prints.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

# `<groupId>|<artifactId>|<version>|<self-report entry>|<key>`. The VERSION is a
# request; the value that reaches the table is whatever the resolved jar says
# about itself at the entry named here, and `-|-` means the artifact says
# nothing and the column is a stated assumption.
#
# spring-webmvc 6.1.6 is the version `fixtures/orders-service/pom.xml` pins.
# okhttp 4.12.0 is the version the sweep's own `A-C2` reproduction used. The two
# jakarta.websocket artifacts are the current release of the 2.2 API, and the
# question they answer — which jar declares which annotation — is why BOTH are
# resolved rather than either.
ARTIFACTS=(
  "com.squareup.okhttp3|okhttp|4.12.0|class:okhttp3.OkHttp|VERSION"
  "com.squareup.retrofit2|retrofit|2.11.0|-|-"
  "jakarta.websocket|jakarta.websocket-api|2.2.0|META-INF/MANIFEST.MF|Implementation-Version"
  "jakarta.websocket|jakarta.websocket-client-api|2.2.0|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-webmvc|6.1.6|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-webmvc|6.2.15|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-webmvc|7.0.2|META-INF/MANIFEST.MF|Implementation-Version"
  "org.springframework|spring-webmvc|7.0.9|META-INF/MANIFEST.MF|Implementation-Version"
)

specs=()
for artifact in "${ARTIFACTS[@]}"; do
  IFS='|' read -r group name version entry key <<<"$artifact"
  jar="${M2}/${group//.//}/${name}/${version}/${name}-${version}.jar"
  if [ ! -f "$jar" ]; then
    echo "resolving ${group}:${name}:${version}" >&2
    mvn -q -B dependency:get -Dtransitive=false \
      -Dartifact="${group}:${name}:${version}" >&2
  fi
  specs+=("${group}|${name}|${version}|${entry}|${key}|${jar}")
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" probe.py "${specs[@]}"
