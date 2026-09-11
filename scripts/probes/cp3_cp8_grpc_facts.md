# CP-3 / CP-8 — the extends relationship, and generated gRPC classes in the fact stream (2O design §0a)

**Harness, committed (R7).** Unlike CP-1/CP-6 (scratch apps, discarded), this probe's
fixture is a real, checked-in Maven project: `fixtures/grpc-probe/`. It declares one
`.proto` service (`order_service.proto`), compiles it with grpc-java's protoc plugin
(`io.grpc:protoc-gen-grpc-java:1.62.2`, wired through `io.github.ascopes:protobuf-maven-plugin`
exactly like `fixtures/orders-service` already does for plain protobuf), and implements the
service in one user class, `OrderServiceImpl`. It is a standalone fixture (own `pom.xml`,
own coordinates, `com.example:grpc-probe`) — not a module of `fixtures/pom.xml`, the same
way `orders-service` stands alone.

A later reader re-runs the whole probe with:

```bash
mvn -o -q -B -f fixtures/grpc-probe/pom.xml compile
./gradlew -p extractor-jvm shadowJar   # only if the extractor itself changed
java -jar src/sextant/extractor-jvm/sextant-extractor.jar \
  --module-id com.example:grpc-probe --coordinates com.example/grpc-probe --version 1.0.0 \
  --classes fixtures/grpc-probe/target/classes --out /tmp/grpc_probe_out \
  > /tmp/grpc_probe_report.json
```

`mvn -o` (offline) works because the one online step already ran once, priming
`~/.m2` with `protoc` 4.36.1, `protoc-gen-grpc-java` 1.62.2 and grpc-java 1.62.2's
runtime jars — the same "prime once online, then offline" shape
`.github/workflows/pr.yml` already uses for `orders-service`.

## CP-3 — is a plain `extends` relationship present in the fact stream?

**Before this task: ABSENT**, confirmed by reading the extractor rather than guessing —
`ClassScanner.Visitor.superName` (the class file's own `super_class` constant-pool entry,
handed to ASM's `visit` regardless of whether a `Signature` attribute exists) was stored
in a field and used only internally, to let `DescriptorHarvest` recognise an Avro-generated
record. No code path ever wrote it into a fact. `interfaces` erases every implemented type
to a bare symbol, and `supertype` — D00 §5a's PTR carrier — fires only when the superclass's
own signature is generic (`new ParameterizedTypeReference<...>() {}`, `class Box<T>
extends Carrier<T>`), which a plain `class Foo extends Bar` never is: no `Signature`
attribute reaches such a class file at all, so `TypeRefs.genericSuperclassFromSignature`
has nothing to read. This matches 2G's own observation (protobuf hierarchy matched via
`implements` instead) exactly, and is why this task shipped capability **9.13**: a
`superclass` field on the class symbol fact, read straight from `superName`, null only for
`java.lang.Object` (every interface carries that same constant-pool entry though no
interface "extends" it, and every root class gets it implicitly — writing it there would
say nothing with it).

**After 9.13: PRESENT.** Two independent confirmations, both from real compiled bytecode,
both reproducible from the commands above:

- `fixtures/orders-service`'s existing `DetailedOrderResult extends OrderResult` (plain,
  no generics anywhere in either class — see `tests/ingress/test_asm_scanner.py::test_a_plain_class_records_its_erased_superclass_symbol`
  for the exact assertion against the real scanned fixture).
- This probe's own `OrderServiceImpl extends OrderServiceGrpc.OrderServiceImplBase` — see
  CP-8(c) below for the exact fact.

**Verdict: FALSIFIED as stated (absent), which is why 9.13 shipped in this task** — not a
probe-only finding left for later. Capability 9.13's implementation is
`extractor-jvm/src/main/java/dev/sextant/extractor/ClassScanner.java`'s
`erasedSuperclassJson`, and its JVM-level fixture/tests are
`extractor-jvm/src/test/java/dev/sextant/extractor/PlainSubclassSample.java` +
`ClassScannerTest#keeps_the_erased_superclass_symbol_on_the_class_symbol` /
`#omits_superclass_when_it_is_plain_object`.

## CP-8 — generated gRPC classes against `fixtures/grpc-probe`

Ran against `fixtures/grpc-probe/target/classes` with the commands above (scanner_version
`9.14`): **23 documents, 658 facts, 0 uncovered.**

### (a) Does the generated `<Service>Grpc` class appear in module facts?

**CONFIRMED.** Every generated type reaches its own `.jsonl` fact file, one class file one
document (D00 §2), exactly like any other scanned class — `OrderServiceGrpc` itself plus
every one of its ten nested types (`$1`/`$2`/`$3` stub-factory lambIdas' anonymous classes,
`$AsyncService`, `$MethodHandlers`, `$OrderServiceImplBase`, `$OrderServiceStub`,
`$OrderServiceBlockingStub`, `$OrderServiceFutureStub`, the three `*DescriptorSupplier`
classes) show up under
`/tmp/grpc_probe_out/com/example/grpcprobe/proto/OrderServiceGrpc*.jsonl`, alongside the
message classes (`GetOrderRequest`/`GetOrderReply` and their builders) and the file-level
`OrderServiceOuterClass` holder. Nothing about "generated" excludes it from a scan — the
extractor has no notion of generated-vs-hand-written code; it reads whatever is in
`target/classes`, protoc-generated or not, the same as `orders-service`'s own
`OrderProtos`/`CommonProtos` already prove for plain protobuf.

### (b) Is `SERVICE_NAME` readable as a constant fact, value `<protoPackage>.<Service>`?

**FALSIFIED AS STATED, with a real but indirect recovery path — reported precisely because
CP-8(b) gates Task 5.**

`SERVICE_NAME` itself is visible only as a **declaration**:

```json
{"construct_kind":"field","enclosing":".../OrderServiceGrpc#","modifiers":{"static":true,"transient":false},
 "signature":{"returns":{"symbol":"java/lang/String#","wire_type":"string",...}},
 "symbol":".../OrderServiceGrpc#SERVICE_NAME."}
```

Its **value** — `"sextant.grpcprobe.OrderService"` — is nowhere in this fact. This is not a
gRPC-specific gap: D00 §5's `constant` fact kind (`Symbol, value`) has **no producer
anywhere in this codebase** — `sextant.domain.facts` has no `ConstantFact` class, and
`ClassScanner.visitField`'s own `Object value` parameter (ASM hands over a field's
`ConstantValue` attribute directly, when the JVM spec writes one for a compile-time-constant
field exactly like this one) is accepted and never read. Implementing a `constant` fact
kind is new scope this task did not authorize (R10 scoped this task to 9.13/9.14 only) and
is not attempted here.

**The value IS recoverable, but only where the constant is actually USED, via the shipped
`call_site`/`string_constants` capability (2C) — not via any field-level fact.** `SERVICE_NAME`
is a compile-time constant (`public static final String SERVICE_NAME = "...";`), so JLS
13.1/13.4.9 requires javac to **inline it at every use site** rather than emit a field read;
the bytecode `LDC`s the literal directly. Two call sites in `OrderServiceGrpc` carry it as a
plain string argument:

```json
{"kind":"call_site","caller":".../OrderServiceGrpc#getServiceDescriptor(...)",
 "target":{"owner":"io/grpc/ServiceDescriptor#","name":"newBuilder",...},
 "arguments":[{"kind":"string","value":"sextant.grpcprobe.OrderService"}]}
```

and the `generateFullMethodName` call in (d) below. So a consumer CAN read
`"sextant.grpcprobe.OrderService"` from bytecode alone — but only by matching a specific
call site's argument, the same style CP-8(d) already requires, never by reading the field
declaration itself. **Ledgered for Task 5:** the `supertype_derived`/`injected_client`
styles' `identity_marker: {constant: SERVICE_NAME}` catalog shape (2O design §1b/§1c)
cannot be a field-value read; it must be a call-site-argument read at
`ServiceDescriptor.newBuilder(...)`'s (or `generateFullMethodName`'s) first argument on the
matched class — which the fact stream supports today, without any new extractor capability,
just a different join than "read the field's value" implies.

### (c) Is the user class's `extends` edge to `<Service>ImplBase` visible?

**CONFIRMED**, via capability 9.13 (this task):

```json
{"construct_kind":"class","symbol":".../OrderServiceImpl#",
 "superclass":"sextant-jvm maven com.example/grpc-probe 1.0.0 com/example/grpcprobe/proto/OrderServiceGrpc$OrderServiceImplBase#"}
```

### (d) Are the wire method names readable as constants?

**CONFIRMED — as call-site string arguments, the same shape as (b)'s recovery path, not as
a `constant` fact.** `OrderServiceGrpc#getGetOrderMethod()` builds its `MethodDescriptor`
with the exact grpc-java pattern the checkpoint names:

```json
{"kind":"call_site","caller":".../OrderServiceGrpc#getGetOrderMethod(...)",
 "target":{"owner":"io/grpc/MethodDescriptor#","name":"generateFullMethodName",
           "descriptor":"(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;"},
 "arguments":[{"kind":"string","value":"sextant.grpcprobe.OrderService"},
              {"kind":"string","value":"GetOrder"}]}
```

and a second, independent occurrence — the `OrderServiceMethodDescriptorSupplier`
constructor call, also carrying the proto-cased name verbatim:

```json
{"kind":"call_site","caller":".../OrderServiceGrpc#getGetOrderMethod(...)",
 "target":{"owner":".../OrderServiceGrpc$OrderServiceMethodDescriptorSupplier#","name":"<init>",
           "descriptor":"(Ljava/lang/String;)V"},
 "arguments":[{"kind":"string","value":"GetOrder"}]}
```

`"GetOrder"` (proto-cased) is the literal argument, never a casing of the Java method name
(`getOrder`) — confirming the checkpoint's premise that the two are never derived from one
another. Both occurrences are reachable through the already-shipped `call_site` capability;
nothing new was needed for (d).

## What this settles for Task 5

- **9.13 ships** (this task) — CP-3 is closed, `superclass` is a real field.
- **(a) and (c) are unqualified good news** — the generated class and the `extends` edge to
  its `ImplBase` both reach the fact stream exactly as hoped.
- **(b) and (d) are NOT a flat falsification, but they are not a field-value read either.**
  A `supertype_derived`/`injected_client` engine can still publish `<protoPackage>.<Service>`
  and the proto-cased method name from bytecode alone, but only by reading them off the
  matched class's OWN generated `getServiceDescriptor`/`get<Method>Method`/
  `generateFullMethodName` call sites — never off `SERVICE_NAME`'s field declaration, which
  carries no value. Task 5's catalog `identity_marker`/`supertype_marker: {constant:
  SERVICE_NAME}` shape (2O design §1b/§1c) needs to be read as "the string argument at the
  class's own identity-building call site", not "the named field's value" — a design note
  for Task 5, not a gap this task leaves silent.
