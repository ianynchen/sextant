#!/usr/bin/env bash
# CP-23 harness — see ../cp23_kotlin_call_shapes.md for the questions, the version
# scope and the verdicts.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADER COMES FROM THE CLASS FILES' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). `probe.py` reads
# `@kotlin.Metadata`'s `mv` off `Shapes.class` and the version header of the
# `.kotlin_module` kotlinc wrote beside it, rather than trusting the `kotlin.version`
# the POM asked for; `EXPECTED` below is what those bytes are expected to report,
# and a disagreement aborts the run. Each Maven profile compiles into its own
# `target/<profile>` (`indy`, the compiler's default, and `class`, `-Xlambdas=class`)
# after a `clean` of that directory, so no cell can come from a stale build.
#
# Needs a JDK at `$JAVA_HOME` (for `javap` and to run the extractor), Maven, and
# network on the first run only (kotlinc 2.2.0 is cached in ~/.m2 afterwards). The
# extractor jar is built by Gradle first so Q8 reads the tree as it stands. Not a
# test: nothing in the suite runs it.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
: "${JAVA_HOME:?JAVA_HOME must name the JDK whose javap and java the probe runs}"
EXPECTED=2.2.0

build() {
  local profile="$1"
  echo "compiling profile ${profile}" >&2
  mvn -q -B -o clean package -P "${profile}" >&2 \
    || mvn -q -B clean package -P "${profile}" >&2
}
build indy
build class

echo "building the extractor jar" >&2
(cd "$REPO/extractor-jvm" && ./gradlew --quiet shadowJar)

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" probe.py \
  "INDY=$PWD/target/indy/classes" \
  "CLASS=$PWD/target/class/classes" \
  "EXTRACTOR=$REPO/src/sextant/extractor-jvm/sextant-extractor.jar" \
  "JAVA_HOME=$JAVA_HOME" \
  "EXPECTED=$EXPECTED"
