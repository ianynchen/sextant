# Coverage — Android and iOS

Detection shapes are defined in [COVERAGE.md](../COVERAGE.md) §1.

Mobile inverts the assumption the rest of this project rests on. A service has
**inbound endpoints**; an app almost never does. An app is nearly all outbound calls, plus
a small number of inbound boundaries that are not HTTP at all — a deep link, a push
notification, a share intent. The endpoint model still fits, but the protocol values and
the address shapes are new.

> **Scope.** [COVERAGE.md](../COVERAGE.md) §5 is canonical for tier and status,
> organised by protocol. This file holds what does not fit a protocol row: the
> toolchain verdict, the payload story, and the structural oddities of the language.

---

## Android

Kotlin is already an MVP language. Android-specific features are **post-MVP by decision**.

### The toolchain answer is: nothing changes

✅ Verified. The Android build compiles Kotlin and Java to **ordinary JVM `.class` files** and only then runs D8 to produce DEX. The intermediates sit at `app/build/intermediates/…/*.class` before dexing, and the Android Gradle Plugin exposes its own instrumentation API that takes an **ASM `ClassVisitor`** over exactly those files.

So our existing extractor works on Android **unchanged**, provided we point the scanner at the pre-dex intermediates rather than at the APK or AAB. If we ever needed to read a shipped artifact instead, DEX requires a different reader (`dexlib2`) — but there is no reason to, because the intermediates are a build output we already have.

The real Android work is therefore **catalogs and a manifest reader**, not a new scanner.

### Outbound — the bulk of an Android app's surface

| Library | Shape | Detection |
|---|---|---|
| **Retrofit** | `@GET("users/{id}")`, `@POST`, `@Body`, `@Query`, `@Path` on an interface method | **`annotation`** — nearly identical in shape to `@HttpExchange` and Feign. Tier A, and the single highest-value Android catalog. |
| OkHttp | `Request.Builder().url(u).get().build()` | `fluent_chain` |
| Ktor client | `client.get("https://…") { … }` | `registration_call` |
| Apollo (GraphQL) | generated operation classes from `.graphql` documents | `generated_descriptor` |
| Firebase / Firestore | `db.collection("users").document(id).get()` | `fluent_chain` — a data boundary worth modelling |

Base URLs live in `Retrofit.Builder().baseUrl(…)`, in a build-config field, or in a flavour-specific resource — a `config_join`, and the same problem as everywhere else.

### Inbound — not HTTP

| Boundary | Where it is declared | Detection |
|---|---|---|
| **Deep links / App Links** | `AndroidManifest.xml`: `<intent-filter>` with `<data android:scheme android:host android:pathPrefix>` | **artifact** — XML, a tier-2 source |
| Exported activities, services, receivers | `AndroidManifest.xml`, `android:exported="true"` | artifact — **also the primary Android attack surface**, so worth surfacing regardless |
| Content providers | manifest `<provider android:authorities>` + a `ContentProvider` subclass | artifact + `interface_implementation` |
| Push messages | `FirebaseMessagingService.onMessageReceived` | `interface_implementation` |
| Background work | `WorkManager` `Worker` subclasses, `@HiltWorker` | `interface_implementation` |
| In-app navigation | Navigation component graphs (XML) or Compose `NavHost` routes as strings | artifact / `registration_call` |
| Room database | `@Query("SELECT …")`, `@Insert` on DAO interfaces | `annotation` — **SQL in an annotation**, a readable data-access contract |

**`AndroidManifest.xml` is to an Android app what a controller class is to a service**: the declaration of what the outside world may reach. It should be a first-class artifact reader, not an afterthought.

### Post-MVP scope note

Per decision, MVP covers Kotlin as a JVM language — the language, the bytecode, the ordinary server-side catalogs. Retrofit, the manifest reader, Room and the intent model are deferred. They are listed here so the deferral is a choice rather than an oversight.

---

## iOS — Swift

### Toolchain — better than expected, and it needs a build

✅ Verified. Swift's compiler emits index data **as a side effect of compilation** — "index while building". `swiftc` and `clang` write a raw index store, which `IndexStoreDB` reads into a queryable database of symbols, symbol occurrences and **relations**, backed by LMDB. `sourcekit-lsp` uses exactly this to answer call-hierarchy, find-references and jump-to-definition across module boundaries.

That is a compiler-backed, type-accurate fact source — **the closest analogue to JVM bytecode of any non-JVM language here**, and better than anything Python or Rust offers. It requires a build, which fits DR-4 exactly: authority follows the build. The static-analysis tool Periphery already works this way (build first, then analyse), so the approach has precedent.

| Route | Gives |
|---|---|
| **IndexStoreDB** | Symbols, occurrences, relations, call hierarchy — typed and cross-module. Needs a completed build. |
| `SwiftSyntax` | Full syntax tree, no types. Good for reading attributes and literals. |
| `sourcekit-lsp` | The same index, over LSP |

The obvious cost is that the build is Xcode-shaped and generally macOS-only.

### Outbound

| Library | Shape | Detection |
|---|---|---|
| `URLSession` | `URLSession.shared.data(for: request)`; `URLRequest(url:)` with `httpMethod = "POST"` | `fluent_chain` — **the verb is a property assignment**, not a call argument. A shape we have not handled anywhere else. |
| **Alamofire** | `AF.request(url, method: .get, parameters: …)` | `registration_call` — verb is an enum argument. Most popular third-party Swift library. |
| **swift-openapi-generator** | typed client generated from an OpenAPI document | **best case** — the OpenAPI document is in the repository; read it directly |
| Connect-Swift | generated typed clients over Protobuf, on `URLSession` | `generated_descriptor` |
| gRPC-Swift | generated `FooAsyncClient`, service providers | `registration_call` |
| SwiftProtobuf | `struct Foo: SwiftProtobuf.Message` with field numbers in generated code | `generated_descriptor` |

### Inbound

| Boundary | Declared in | Detection |
|---|---|---|
| Custom URL schemes | `Info.plist` → `CFBundleURLTypes` | artifact |
| Universal Links | `apple-app-site-association` (a JSON file on the server) + entitlements | artifact — **and it lives outside the app repository**, which is a cross-repository join |
| App Intents / Siri | `@AssistantIntent`, `AppIntent` conformances ⚠️ | `annotation` / `interface_implementation` |
| Push notifications | `UNUserNotificationCenterDelegate` methods | `interface_implementation` |
| Share / action extensions | separate targets with `NSExtension` keys in `Info.plist` | artifact |
| Background tasks | `BGTaskScheduler` identifiers, registered as strings and declared in `Info.plist` | `registration_call` + artifact |

### Server-side Swift

Rare but real, and it produces genuine inbound HTTP endpoints:

| Framework | Shape | Detection |
|---|---|---|
| Vapor | `app.get("users", ":id") { req in … }` | `registration_call` — **path segments are variadic arguments**, not one string |
| Hummingbird | `router.get("/users/:id") { … }` | `registration_call` |

### Payloads — genuinely good

```swift
struct Order: Codable {
    let id: String
    let total: Double?
    enum CodingKeys: String, CodingKey { case id, total = "totalAmount" }
}
```

`Codable` gives declared fields and declared types; `Optional` gives nullability; `CodingKeys` gives the wire name when it differs. All statically present. This is comparable to Go struct tags and better than untyped Python or JavaScript.

---

## Verdict

**Android is cheap** — the scanner already works, and the gap is catalogs (Retrofit above all) plus an `AndroidManifest.xml` reader. It is deferred by choice, not by difficulty.

**iOS is more work but not blocked.** The index store is a real compiler-backed fact source, so Swift ranks third behind the JVM and Go, ahead of Python and Rust. The costs are a macOS build requirement and an inbound model built on `Info.plist` and entitlements rather than on route declarations.

For both platforms the honest framing is that **an app is an outbound-only participant in most systems**. That is useful — an app is exactly the client whose calls we want to match against a service's endpoints — but it means the value shows up in `system` stitching, not in per-module endpoint listings.
