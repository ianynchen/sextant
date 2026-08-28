# Coverage — Go

Not in the MVP. This is the checklist for when it is.

Detection shapes are defined in [COVERAGE.md](../COVERAGE.md) §1.

> **Scope.** [COVERAGE.md](../COVERAGE.md) §5 is canonical for tier and status,
> organised by protocol. This file holds what does not fit a protocol row: the
> toolchain verdict, the payload story, and the structural oddities of the language.

---

## Toolchain — the best of any language we surveyed except the JVM

Go hands us more than the JVM does, and it hands it over without a build.

| Need | Tool | Note |
|---|---|---|
| Parse + fully type-check a program | `golang.org/x/tools/go/packages` | Loads, resolves imports, runs the type checker. Types are **complete** — Go has no untyped escape hatch comparable to `dict` or `any` in practice. |
| SSA form | `golang.org/x/tools/go/ssa` | |
| **Call graph** | `golang.org/x/tools/go/callgraph/{static,cha,rta,vta}` | ✅ verified |

**Go ships CHA, RTA and VTA as library code.** For the JVM we planned to write class hierarchy analysis ourselves and deferred variable type analysis to a later version; for Go, all three already exist, are maintained by the Go team, and run off `go/packages`. `cha` is explicitly documented as sound on partial programs — libraries with no `main` — which is exactly our situation when scanning a module in isolation.

**Consequence:** Go's dispatch resolution is *ahead* of the JVM's on day one, not behind it. The work for Go is the boundary catalogs, not the graph.

**Caveat.** Loading requires dependencies to be resolvable (`go mod download`). That is a build input in the sense of DR-4, so authority is preserved. Build tags and `//go:generate` output are the usual sources of missing code.

---

## Inbound HTTP

| Library | Shape | Detection | Note |
|---|---|---|---|
| `net/http` (Go 1.22+) | `mux.HandleFunc("GET /items/{id}", h)` | `registration_call` | ✅ verified. Method and wildcards are **inside the pattern string** — one literal carries verb *and* path. Parse the string, don't just record it. |
| `net/http` (pre-1.22) | `mux.HandleFunc("/items/", h)` then `if r.Method == …` | `runtime_dynamic` | The verb is a branch inside the handler. Recoverable only by reading control flow. |
| `gin` | `r.GET("/path", h)`, groups via `r.Group("/api")` | `registration_call` | Groups nest a prefix — needs the receiver's provenance, like a class-level `@RequestMapping`. |
| `echo` | `e.GET("/path", h)`, `e.Group` | `registration_call` | |
| `chi` | `r.Get("/path", h)`, `r.Route("/api", func(r chi.Router){…})` | `registration_call` | `r.Route` nests via a closure — prefix lives on the enclosing call. |
| `gorilla/mux` | `r.HandleFunc("/p", h).Methods("GET")` | `fluent_chain` | Verb is a *sibling* call on the returned `*Route`. Short chain, tractable. |
| `fiber` | `app.Get("/path", h)` | `registration_call` | |

All of these except pre-1.22 `net/http` are the same underlying job: **a method call whose receiver type identifies the framework, whose name or first argument gives the verb, and whose first string argument gives the path.** One engine covers the lot.

---

## Outbound HTTP

| Library | Shape | Detection |
|---|---|---|
| `net/http` | `http.Get(url)`, `http.NewRequest("GET", url, body)` + `client.Do(req)` | `registration_call` for the first, `fluent_chain` for the second |
| `resty` | `client.R().SetBody(x).Get(url)` | `fluent_chain` |
| Generated OpenAPI clients (`oapi-codegen`) | typed methods per operation | `annotation`-equivalent — best case |

---

## Messaging and RPC

| Protocol | Library | Shape | Detection |
|---|---|---|---|
| Kafka | `segmentio/kafka-go` | `kafka.NewReader(kafka.ReaderConfig{Topic: "t", GroupID: …})` | `registration_call` — **topic is a struct-literal field**, which is easier than a positional argument, not harder |
| Kafka | `IBM/sarama` ⚠️ (was `Shopify/sarama`) | `consumer.ConsumePartition(topic, …)`, `producer.Input() <- &sarama.ProducerMessage{Topic: t}` | `registration_call` / channel send |
| Kafka | `confluent-kafka-go` | `c.SubscribeTopics([]string{"t"}, nil)` | `registration_call` |
| SQS | `aws-sdk-go-v2` | `client.SendMessage(ctx, &sqs.SendMessageInput{QueueUrl: …})` | `registration_call` — struct literal again |
| Pub/Sub | `cloud.google.com/go/pubsub` | `client.Topic("name").Publish(ctx, msg)`; `client.Subscription("s").Receive(ctx, fn)` | `fluent_chain`, two links |
| gRPC | `google.golang.org/grpc` | server `pb.RegisterFooServer(s, impl)`; client `pb.NewFooClient(conn)` | `registration_call` — **the generated registration function names the service explicitly.** Cleaner than the JVM's `extends FooImplBase`. |
| Protobuf | `google.golang.org/protobuf` | generated `.pb.go` embeds the serialized `FileDescriptorProto` as a raw byte slice ⚠️ | `generated_descriptor` |
| AMQP | `rabbitmq/amqp091-go` ⚠️ (was `streadway/amqp`) | `ch.QueueDeclare(name, …)`, `ch.Publish(exchange, key, …)` | `registration_call` |
| NATS | `nats.go` | `nc.Subscribe("subject", cb)`, `nc.Publish("subject", data)` | `registration_call` |

---

## Payloads — the strongest story of any language here

```go
type Order struct {
    ID       string  `json:"id"`
    Total    float64 `json:"total,omitempty"`
    Internal string  `json:"-"`
}
```

Struct tags give us the **wire name**, and the Go type gives the **wire type**, and both are statically present with no inference. `omitempty` is a strong signal for optionality, and `-` is an explicit exclusion. Pointer types (`*string`) versus value types is a further nullability signal.

This is better than Java, where Jackson defaults mean an unannotated field still serialises and the wire name is derived from the getter by convention.

---

## Verdict

**Go should be the first language after the JVM.** Full types without a build step, a maintained call-graph library that already includes the analysis we deferred for Java, uniformly `registration_call`-shaped web frameworks, and payload shapes that are declared rather than inferred. There is no `runtime_dynamic` cluster of the kind that Python's `boto3` and JavaScript's bundlers create.

The only genuinely awkward case is pre-1.22 `net/http`, where the verb lives in an `if` inside the handler.
