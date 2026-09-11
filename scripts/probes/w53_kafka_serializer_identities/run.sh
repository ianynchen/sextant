#!/usr/bin/env bash
# W53 — does every serializer class `spring-kafka-media.yml` names exist? (G-88)
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"
CONFLUENT="https://packages.confluent.io/maven/"

for artifact in "org.springframework.kafka:spring-kafka:3.1.4" "org.apache.kafka:kafka-clients:3.6.2"; do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done
for artifact in \
  "io.confluent:kafka-avro-serializer:7.6.0" \
  "io.confluent:kafka-protobuf-serializer:7.6.0" \
  "io.confluent:kafka-json-schema-serializer:7.6.0" \
  "io.confluent:kafka-json-serializer:7.6.0"
do
  echo "ensuring ${artifact} (confluent)" >&2
  mvn -q -B dependency:get -Dtransitive=false \
    -DremoteRepositories="confluent::::${CONFLUENT}" \
    -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
