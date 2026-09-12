#!/usr/bin/env bash
# W63 — does Apache CXF's JAX-WS frontend decide "which public method is an
# operation" the same way the reference implementation does (jaxws-rt 4.0.2):
# inherited public methods included, `static`/`final` excluded, `@WebMethod
# (exclude = true)` honoured, and an operation with no `@WebMethod` of its own
# exposed only when the METHOD'S OWN declaring class carries `@WebService`.
# jaxws-rt 4.0.2 is resolved here directly (not just cited from CP-13) so its
# bytecode and its live service model can both be read side by side with CXF's.
set -euo pipefail
cd "$(dirname "$0")"
REPO="$(cd ../../.. && pwd)"

# `cxf-rt-frontend-jaxws` and `cxf-core` per the task brief. `JaxWsServiceConfiguration`
# and `JaxWsImplementorInfo` resolve out of the first. `cxf-core` DOES carry an
# `org/apache/cxf/service/factory/` package (`AbstractServiceFactoryBean` and five
# siblings) — but not the brief's two named classes,
# `ReflectionServiceFactoryBean` / `AbstractServiceConfiguration`. `unzip -l`
# showed those two live at 4.0.5 in `org.apache.cxf.wsdl.service.factory`, shipped in
# `cxf-rt-wsdl` (a transitive dependency of `cxf-rt-frontend-jaxws` via
# `cxf-rt-bindings-soap`, confirmed by `mvn dependency:tree`) — so that artifact is
# fetched too, and `sweep.py` records the mismatch rather than silently reading the
# brief's assumed package. `jaxws-rt` is the reference implementation itself.
for artifact in \
  "org.apache.cxf:cxf-rt-frontend-jaxws:4.0.5" \
  "org.apache.cxf:cxf-core:4.0.5" \
  "org.apache.cxf:cxf-rt-wsdl:4.0.5" \
  "jakarta.jws:jakarta.jws-api:3.0.0" \
  "com.sun.xml.ws:jaxws-rt:4.0.2"
do
  echo "ensuring ${artifact}" >&2
  mvn -q -B dependency:get -Dtransitive=false -Dartifact="${artifact}" >/dev/null 2>&1 || true
done

if [ -x "$REPO/.venv/bin/python" ]; then PY="$REPO/.venv/bin/python"; else PY=python3; fi
exec "$PY" sweep.py
