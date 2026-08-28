# Coverage — TypeScript and JavaScript

Not in the MVP. Detection shapes are defined in [COVERAGE.md](../COVERAGE.md) §1.
The typing analysis is in [COVERAGE.md](../COVERAGE.md) §10.

> **Nothing in this file ships today** — see [COVERAGE.md](../COVERAGE.md) §2.
>
> **Scope.** [COVERAGE.md](../COVERAGE.md) §5 is canonical for tier and status,
> organised by protocol. This file holds what does not fit a protocol row: the
> toolchain verdict, the payload story, and the structural oddities of the language.

---

## Toolchain — much better than Python, on one condition

**TypeScript source is the second-best fact source of any language here, after JVM bytecode. Compiled JavaScript is the worst.** The gap between them is total, and it inverts the decision we made for the JVM.

| Route | Gives |
|---|---|
| **TypeScript Compiler API** (`typescript` package, `ts.TypeChecker`) | A real type checker: `getTypeAtLocation`, `getSignatureFromDeclaration`, symbol resolution, declaration following. Shipped, supported, stable, and usable as a library — unlike anything in Python or Rust. |
| `ts-morph` | Ergonomic wrapper over the same checker |
| `Jelly` (`@cs-au-dk/jelly`) | JS/TS call-graph construction — flow-insensitive control-flow and points-to analysis with access paths. Named in the literature as the reference JS call-graph tool (§10). BSD-3-Clause. |
| Babel / SWC / `oxc` parsers | Syntax only, no types |

### Why compiled output is useless to us

Everything we would want to read is destroyed by the build:

- **Types are erased.** That is the design.
- **Decorators become `__decorate([...])` calls** with the metadata flattened into arguments.
- **Bundlers rename, inline, tree-shake and merge modules.** esbuild/rollup/webpack output has no reliable module or symbol identity.

So the JVM rule — *scan what is compiled* — **must be inverted for TypeScript: scan the source, and require `tsconfig.json` as the build input** that establishes authority under DR-4. `tsconfig.json` plays the role `pom.xml` plays for Maven: it names the sources, the module resolution, and the compiler settings.

**Plain JavaScript with no TypeScript and no JSDoc is the floor case for the whole project** — no types, no build manifest describing types, and dynamic dispatch everywhere.

---

## Inbound HTTP

| Framework | Shape | Detection | Payload types |
|---|---|---|---|
| **NestJS** | `@Controller("users")` on the class + `@Get(":id")` on the method; `@Body() dto: CreateUserDto` | **`annotation`** | **Yes** — DTO classes with `class-validator` decorators |
| Express | `app.get("/users/:id", handler)`, `router.post(...)`, mounted by `app.use("/api", router)` | `registration_call` | No — `req.body.x` |
| Fastify | `fastify.get("/users/:id", { schema: {...} }, handler)` | `registration_call` | **Yes** — the options object carries a **JSON Schema** for body, params and response. A gift: the contract is literally declared. |
| Koa + `@koa/router` | `router.get("/users", handler)` | `registration_call` | No |
| Hapi | `server.route({ method: "GET", path: "/users", handler })` | `registration_call` | Yes — `options.validate` with Joi |
| **Next.js App Router** | `app/api/users/[id]/route.ts` exporting `export async function GET(req)` | **`filesystem`** | No |
| Next.js Pages Router | `pages/api/users/[id].ts` with a default export | `filesystem` | No |
| SvelteKit / Remix / Nuxt | file-based routes with `+server.ts` / `loader` / `action` conventions | `filesystem` | No |
| **tRPC** | `router({ getUser: publicProcedure.input(z.object({id: z.string()})).query(fn) })` | `fluent_chain` | **Yes** — `zod` schema is the contract, and it is right there |
| Hono | `app.get("/users", handler)` | `registration_call` | With `zValidator` middleware |

### `filesystem` routing is a detection shape we have never designed for

In Next.js, SvelteKit, Remix and Nuxt, **the endpoint path is the file's path on disk** and **the HTTP verb is the name of the exported symbol**. There is no annotation, no registration call, and no string literal containing the route anywhere in the code.

Our whole model assumes a fact is extracted from a declaration or a call. This one is extracted from a *directory walk* plus an export list, with framework-specific conventions for dynamic segments (`[id]` → `:id`, `[...slug]` → catch-all) and for route groups (`(marketing)` contributes nothing to the URL). It is not hard, but it is a new engine, and it is the single most common way to write an HTTP endpoint in the modern JavaScript ecosystem.

### NestJS is the highest-value non-JVM target in this document

`@Controller` + `@Get`/`@Post` + `@Body`/`@Param`/`@Query`, on classes, with `reflect-metadata` and typed DTOs. It is structurally the same as Spring MVC. The catalog we would write for it is close to a translation of `spring-web.yml`, and the engine is the one we already have.

---

## Outbound HTTP

| Library | Shape | Detection |
|---|---|---|
| `fetch` (global) | `fetch(url, { method: "POST", body })` | `registration_call` — verb in an options object |
| `axios` | `axios.get(url)`, `axios({method, url})`, `instance.post(...)` with `baseURL` on the instance | `registration_call` + instance provenance |
| `got`, `ky`, `undici`, `node-fetch` | similar | `registration_call` |
| Generated clients (`openapi-typescript`, `orval`) | one typed method per operation | best case — read the OpenAPI document instead |

---

## Messaging and RPC

| Protocol | Library | Shape | Detection |
|---|---|---|---|
| Kafka | `kafkajs` | `consumer.subscribe({ topic: "orders" })`, `producer.send({ topic, messages })` | `registration_call` — topic in an object literal |
| Kafka | `@confluentinc/kafka-javascript`, `node-rdkafka` | `consumer.subscribe(["orders"])` | `registration_call` |
| **SQS** | `@aws-sdk/client-sqs` (v3) | `client.send(new SendMessageCommand({ QueueUrl: … }))` | `registration_call` — **command classes are real, statically visible types.** Far better than Python's `boto3`. |
| Pub/Sub | `@google-cloud/pubsub` | `pubsub.topic("orders").publishMessage(…)`; `subscription.on("message", cb)` | `fluent_chain` |
| gRPC | `@grpc/grpc-js` + `@grpc/proto-loader` | `protoLoader.loadSync("foo.proto")` then dynamic service objects | **`runtime_dynamic`** — the service is built at runtime from a `.proto` **file path**. The path is a literal, so the right move is to read the `.proto` as an artifact. |
| gRPC | `ts-proto`, `protobufjs` (static mode) | generated typed service definitions | `generated_descriptor` |
| WebSocket | `socket.io` | `io.on("connection", s => s.on("event", cb))`, `socket.emit("event", data)` | `registration_call` — string event names, matchable like topics |
| Queues | `bullmq` | `new Queue("name")`, `new Worker("name", fn)` | `registration_call` |

---

## Payloads

| Style | Recoverable | Note |
|---|---|---|
| **`zod`** | **Yes, with work** | `z.object({ name: z.string(), age: z.number().optional() })` is a **runtime expression**, not a type — recovering the shape means partially evaluating a builder chain. But `z.infer<typeof Schema>` ties it back to the type system, so **the TypeScript checker can often resolve it for us** — much cheaper than interpreting the chain. |
| TypeScript `interface` / `type` | Yes | Directly from the checker, including optionality (`?`) and unions |
| `class-validator` (NestJS) | Yes | `@IsString()`, `@IsOptional()` on DTO fields — carries `required` explicitly |
| Fastify JSON Schema | Yes | Already in the exact form we want |
| `io-ts`, `valibot`, `TypeBox` | Yes, with work | Same builder-expression problem as zod |
| Plain `req.body.x` in JavaScript | No | Floor case |

---

## Verdict

**TypeScript should rank just behind Go**, and well ahead of Python and Rust — the compiler API is a genuine, supported type checker, and `Jelly` exists for call graphs.

Three things must be settled before implementation:

1. **Read source, not build output.** The JVM rule inverts here. `tsconfig.json` becomes the build input that carries authority.
2. **`filesystem` routing needs a new engine.** It is not expressible in any catalog style we have designed, and it covers Next.js, SvelteKit, Remix and Nuxt.
3. **Plain JavaScript must be reported honestly**, not scanned as though it were TypeScript. Absent a `tsconfig.json` or JSDoc annotations, payload shapes are `resolution: unresolved`.
