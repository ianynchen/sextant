# Coverage — Rust

Not in the MVP. Detection shapes are defined in [COVERAGE.md](../COVERAGE.md) §1.

> **Scope.** [COVERAGE.md](../COVERAGE.md) §5 is canonical for tier and status,
> organised by protocol. This file holds what does not fit a protocol row: the
> toolchain verdict, the payload story, and the structural oddities of the language.

---

## Toolchain — the hardest of the five, and the reason is structural

Rust has excellent *compilers* and poor *compiler APIs*. There is no stable, supported way for a third-party tool to ask rustc what it knows.

| Route | What it gives | Problem |
|---|---|---|
| `syn` / `proc-macro2` | Full syntax tree | **No types at all.** Cannot resolve a method call to its impl, cannot follow a trait. |
| `rustdoc` JSON output | Item signatures, trait impls, generics | ⛔ Still **nightly-only** as of August 2026 — `cargo +nightly rustdoc -- --output-format json -Z unstable-options` — and `FORMAT_VERSION` is a breaking change between releases. Documents the *public API*, so private internals and call sites are absent. |
| `rust-analyzer` | Everything, genuinely | No stable library API; it is an LSP server, and its internals change freely. |
| MIR | The real thing | Only via unstable `-Z` flags or a rustc driver plugin, which pins us to an exact nightly. |

**There is no Rust equivalent of ASM, of `go/packages`, or of the Swift index store.** Every route is either type-free or unstable — and this is the one ⛔ in the whole document: no amount of effort on our side produces a stable compiler API that does not exist.

**The macro problem compounds it.** `#[get("/users/{id}")]` in actix-web and Rocket is a procedural macro. The attribute itself is readable with `syn` — the path string is right there in the token stream, which is the good case. But anything that *generates* routes inside a macro body is invisible without expansion, and expansion means running the compiler.

**Provisional recommendation:** for a first pass, `syn` at the syntax level, accepting `resolution: partial` on everything that needs a type. That yields the annotation-shaped frameworks and nothing else. A typed Rust pass should wait for a stable rustdoc JSON format or a decision to pin a toolchain version.

### ⛔ What is blocked, and what is not

This is the only ⛔ in the coverage set. **Blocked** means no amount of effort on our side
produces the thing, because it does not exist to be used — verified August 2026, when rustdoc
JSON remained nightly-only with a `FORMAT_VERSION` that breaks between releases.

**Blocked: anything needing a resolved type.** Dispatch through traits, call edges through
generics, `axum`'s and `warp`'s routes built as values, and any shape that must follow a type
across a crate boundary.

**Not blocked, and worth having on its own:** `actix-web` and Rocket's `#[get("/path")]`
attributes, `prost`'s `#[prost(string, tag = "1")]` field numbers, and every `serde` payload
shape — wire name, optionality and type. All of that is in the token stream and `syn` reads it
without resolving a single type. The blocked half is real but it is not the whole language.

**Alternatives, best first.**

1. **Drive `rust-analyzer` over LSP.** It has no stable library API, but LSP is a protocol and
   is stable enough to depend on. **Python needs exactly this trick for `pyright`**, whose
   maintainers give the same answer — so one LSP-backed fact source serves both languages, and
   two separate blockers collapse into one component. The strongest option, and the reason is
   that it is not Rust-specific.
2. **Ship syntax-only via `syn`**, with `resolution: partial` on everything needing a type.
   Available now, and covers the "not blocked" list above.
3. **Pin a nightly toolchain** and read rustdoc JSON behind a `FORMAT_VERSION` matrix — what
   `cargo-public-api` and docs.rs already do. Real maintenance, known shape.
4. **A rustc driver reading MIR.** Most powerful, pins an exact nightly, most brittle.

Do 2 now and 1 when types are needed, precisely because 1 is shared with Python.

---

## Inbound HTTP

| Library | Shape | Detection | Note |
|---|---|---|---|
| `actix-web` | `#[get("/users/{id}")]` on a handler fn | `annotation` | Best case — verb and path in one attribute, readable by `syn`. |
| `actix-web` (alt) | `.route("/users", web::get().to(handler))` | `fluent_chain` | Verb is a nested call in the second argument. |
| `rocket` | `#[get("/users/<id>")]`, mounted via `.mount("/api", routes![…])` | `annotation` + `registration_call` | **The prefix and the handler list are joined at the mount call**, in a different place from the attribute. `routes!` is itself a macro. |
| `axum` | `Router::new().route("/users", get(handler))` | `fluent_chain` | Currently the most popular. Verb is a function in the second argument; nesting via `.nest("/api", other_router)`. |
| `poem` | `#[handler]` + `Route::new().at("/x", get(h))` | `fluent_chain` | |
| `warp` | `warp::path("users").and(warp::get()).and_then(h)` | `combinator_dsl` | **The worst inbound form in any language surveyed.** The route is a value built from composed filters, often across functions, with the type encoding the structure. Statically recovering a path from this needs real evaluation. |
| `salvo` | `#[handler]` + `Router::with_path("x").get(h)` | `fluent_chain` | |
| `utoipa` / `aide` | OpenAPI generated from annotations | `annotation` | If present, **read the generated OpenAPI instead** — far cheaper and authoritative. |

---

## Outbound HTTP

| Library | Shape | Detection |
|---|---|---|
| `reqwest` | `client.get(url).json(&body).send().await` | `fluent_chain` |
| `hyper` | `Request::builder().method("GET").uri(u).body(…)` | `fluent_chain` |

---

## Messaging and RPC

| Protocol | Library | Shape | Detection |
|---|---|---|---|
| Kafka | `rdkafka` | `consumer.subscribe(&["topic"])`, `producer.send(FutureRecord::to("topic"))` | `registration_call` |
| gRPC | `tonic` | server `FooServer::new(impl)` + `.add_service(…)`; client `FooClient::connect(url)` | `registration_call` — generated types name the service |
| Protobuf | `prost` | `#[derive(prost::Message)]` with `#[prost(string, tag = "1")]` per field | `annotation` — **field numbers are in the attributes**, readable by `syn` with no types needed |
| SQS | `aws-sdk-rust` | `client.send_message().queue_url(u).send()` | `fluent_chain` |
| AMQP | `lapin` | `channel.basic_publish(exchange, key, …)` | `registration_call` |
| Pub/Sub | `google-cloud-pubsub` (official `googleapis/google-cloud-rust`) | **publish only — receiving is not implemented**, and the crate is pre-GA. Rust Pub/Sub has no inbound side to detect | `fluent_chain` |

---

## Payloads — declarative, and readable without types

```rust
#[derive(Serialize, Deserialize)]
struct Order {
    id: String,
    #[serde(rename = "totalAmount", skip_serializing_if = "Option::is_none")]
    total: Option<f64>,
}
```

`serde` attributes carry the wire name; `Option<T>` carries optionality; the Rust type carries the wire type. All three are **present in the syntax tree** — no type resolution required. `prost` does the same for protobuf and adds field numbers.

This is the one area where Rust is genuinely easy, and it partly rescues the language: payload shapes are recoverable even under a syntax-only scanner.

---

## Verdict

Rust is **last in implementation order**, not because the ecosystem is unmatchable but because the toolchain will not tell us what things are. The payload story is strong and the annotation-driven frameworks (actix, Rocket, prost) are reachable with `syn` alone. Everything requiring a resolved type — dispatch, `axum`'s and `warp`'s value-built routes, call edges through traits — is blocked on a stable compiler API that does not exist.
