#!/usr/bin/env bash
# W19b — the enumeration pass for the three slices that are NOT about methods on an
# owner type: annotations in a package, repository interfaces, and one annotation's
# own meta-annotations (F2 §3.8, G-47/G-45/G-41).
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

for artifact in \
  "org.springframework.integration:spring-integration-core:6.2.4" \
  "org.springframework.data:spring-data-commons:3.2.5" \
  "org.springframework.data:spring-data-mongodb:4.2.5" \
  "org.springframework.data:spring-data-r2dbc:3.2.5" \
  "org.springframework.data:spring-data-cassandra:4.2.5" \
  "org.springframework.data:spring-data-elasticsearch:5.2.5" \
  "org.springframework.data:spring-data-neo4j:7.2.5" \
  "org.springframework.data:spring-data-jpa:3.2.5" \
  "org.springframework.data:spring-data-keyvalue:3.2.5" \
  "org.springframework.data:spring-data-redis:3.2.5" \
  "org.springframework.data:spring-data-ldap:3.2.5" \
  "org.springframework.data:spring-data-couchbase:5.2.5" \
  "org.springframework.data:spring-data-rest-core:4.2.5" \
  "com.netflix.graphql.dgs:graphql-dgs:8.7.1"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
