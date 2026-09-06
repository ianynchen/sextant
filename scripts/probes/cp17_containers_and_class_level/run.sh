#!/usr/bin/env bash
# CP-17 harness (Stage 4, the per-catalog pass; probe-backlog rank 7's residue,
# and the four measurement gaps the 2026-09-06 `annotation_driven` vocabulary
# pass left named on its own §8.3 audit table) — see
# ../cp17_containers_and_class_level.md for the questions, the version scope and
# the verdicts.
#
# THE QUESTION, asked once of eight annotation families (seven at the first
# run; `sqs-handler` was added when closing `OI-40` needed a question the
# `sqs` family does not carry, and appending it left every earlier row letter
# naming the same cell). The vocabulary pass
# shipped `mapping.annotations[].container`, and its report then listed four
# annotations whose repeatability NOTHING had measured — `@PulsarListener`,
# `@SqsListener`, `@KafkaHandler`, `@RabbitHandler` — converting four grammar
# boundaries into four `javap` questions. So, per family: (1) every attribute
# the annotation declares, with its TYPE; (2) `@Target` and `@Repeatable` on it;
# (3) whether a CONTAINER-shaped sibling exists at all, and what its `value()`
# returns, because a container need not be javac's; (4) whether a POLYMORPHIC
# HANDLER sibling exists, which two catalogs state in a comment that nothing
# measured; (5) how the post-processor finds the annotation and which
# attributes, containers and handlers it reads; and (6) where the rule is an
# ALGORITHM rather than a predicate, the discovery method VERBATIM out of the
# sources jar resolved at the same coordinate.
#
# THE TABLE IS GENERATED, AND ITS COLUMN HEADERS COME FROM THE JARS' OWN BYTES
# (GUIDELINES §5.4, and CP-5's failure it exists to prevent). Each artifact
# below names WHERE it writes its own version, and `probe.py` reads the VALUE
# out of the archive it opened; a jar whose self-report disagrees with the
# coordinate that resolved it ABORTS the run rather than filling a mislabelled
# column.
#
# Needs a JDK (for `javap`), Maven, and network on first run; the jars are
# cached in ~/.m2 afterwards. Not a test: nothing in the suite runs it, and
# NFR-1's no-network rule governs the suite rather than evidence gathering.
set -euo pipefail

cd "$(dirname "$0")"

REPO="$(cd ../../.. && pwd)"
M2="${HOME}/.m2/repository"

# `<groupId>|<artifactId>|<version>|<self-report entry>|<key>|<sources?>`. The
# VERSION is a request; the value that reaches the table is whatever the
# resolved jar says about itself at the entry named here. `sources` resolves the
# `-sources` classifier as well, for question 6.
#
# TWO minors per framework wherever a framework has two in scope, for CP-12's
# reason: an attribute set is a version-scoped fact and one reading cannot say
# whether it is stable. The lower column of each pair is the version the shipped
# catalog's own comment or `measured:` block names; the upper is the current
# generation, so each pair spans a major boundary rather than two patch
# releases. The two LEGACY SQS artifacts are one version each because each is a
# different artifact under a different groupId — they ARE the pair, and the
# catalog's comment names exactly these two.
ARTIFACTS=(
  "org.springframework.pulsar|spring-pulsar|1.2.11|META-INF/MANIFEST.MF|Implementation-Version|sources"
  "org.springframework.pulsar|spring-pulsar|2.0.7|META-INF/MANIFEST.MF|Implementation-Version|sources"
  "io.awspring.cloud|spring-cloud-aws-sqs|3.1.1|META-INF/MANIFEST.MF|Implementation-Version|sources"
  "io.awspring.cloud|spring-cloud-aws-sqs|4.1.1|META-INF/MANIFEST.MF|Implementation-Version|sources"
  "org.springframework.cloud|spring-cloud-aws-messaging|2.2.6.RELEASE|META-INF/MANIFEST.MF|Implementation-Version|"
  "io.awspring.cloud|spring-cloud-aws-messaging|2.4.4|META-INF/MANIFEST.MF|Implementation-Version|"
  "org.springframework.kafka|spring-kafka|3.1.4|META-INF/MANIFEST.MF|Implementation-Version|"
  "org.springframework.kafka|spring-kafka|4.1.1|META-INF/MANIFEST.MF|Implementation-Version|"
  "org.springframework.amqp|spring-rabbit|3.1.4|META-INF/MANIFEST.MF|Implementation-Version|"
  "org.springframework.amqp|spring-rabbit|4.1.1|META-INF/MANIFEST.MF|Implementation-Version|"
)

specs=()
for artifact in "${ARTIFACTS[@]}"; do
  IFS='|' read -r group name version entry key wants_sources <<<"$artifact"
  base="${M2}/${group//.//}/${name}/${version}/${name}-${version}"
  jar="${base}.jar"
  if [ ! -f "$jar" ]; then
    echo "resolving ${group}:${name}:${version}" >&2
    mvn -q -B dependency:get -Dtransitive=false \
      -Dartifact="${group}:${name}:${version}" >&2
  fi
  sources=""
  if [ -n "$wants_sources" ]; then
    sources="${base}-sources.jar"
    if [ ! -f "$sources" ]; then
      echo "resolving ${group}:${name}:${version}:jar:sources" >&2
      mvn -q -B dependency:get -Dtransitive=false \
        -Dartifact="${group}:${name}:${version}:jar:sources" >&2
    fi
  fi
  specs+=("${group}|${name}|${version}|${entry}|${key}|${jar}|${sources}")
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi

exec "$PY" probe.py "${specs[@]}"
