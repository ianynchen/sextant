# Per-path truth: follow hand-offs, never merge paths

Status: approved 2026-11-02 (the user: "we should tell the truth … as long as we have the code,
we have the call graph and can trace"; "Yes, build it"). Branch `fix/per-path-truth`, cut from
`cov/vertx` (PR #88).

## 1. The defect

A value Sextant publishes at `resolved` must be true on every path that reaches it. Two readers
break that today.

**A. The walk ignores a hand-off.** `values.py`'s `escapes` window counts only calls made ON a
value. A value handed to another method as an ARGUMENT is ignored, a narrowing stated in
`_through`'s docstring ("a value handed to another method as an ARGUMENT can be mutated too …
Counting every hand-off would make the commonest readable shape … unresolved"). So:

```java
WebClientOptions o = new WebClientOptions().setDefaultHost("search");
configure(o);                                   // sets the port to 9090
WebClient client = WebClient.create(vertx, o);
client.get("/q").send();                        // Vert.x sends to search:9090
```

publishes peer `search`, `resolved`. The same narrowing applies to every reader of the walk.

**B. The Vert.x options reader merges paths.** `client_base._Options.defaults_of` and `parts_of`
merge the parts every path read (`_agreed`): a part two paths read differently is "set and not
read", and a part one path does not set is ABSENT, as if no path set it. With two factories, one
setting port 8080 and one setting none, the row is `search`, `resolved` — wrong for the first.
An options object Sextant could not read at all (an unlisted factory overload, an unrooted chain,
`new WebClientOptions(json)`) is also read as "nothing set", so `client.get("search", "/q")`
publishes `search` while its port is unknown.

## 2. The rules

1. **A hand-off into code we have is followed.** Between the call that produced a value and the
   call that uses it (the `escapes` window), a call that hands the value to a parameter of a body
   `call_edges` resolves — a method of this module, or of a jar named in `.sextant.yml`
   `extract_libraries` — is walked into. Inside that body, the calls made on the parameter
   (`receiver_parameter`) are read by the same window rule, in their order, at the hand-off's
   position in the caller's order; a further hand-off of the parameter is followed the same way
   (a cycle is `cycle`). A call with several resolved callees is several paths. A method's OWN
   parameter is a value produced when the method is entered: its window runs from the entry to
   the use, so `send(o) { configure(o); create(vertx, o); }` reads the hand-off inside `send`
   (fix round 1, C1).
2. **A hand-off into code we do not have is unknown.** A callee `call_edges` leaves NULL (the JDK,
   a library not named, another module), a write of the value into a field, a call that reaches
   the value below the top level of an argument (an array element, a merge candidate), an
   instance call on the value's own type whose receiver the facts cannot name (a parameter
   reassigned on a branch), and a call through a type a lambda or method reference in the
   module implements (`dispatch` lists no such body) end the path with `escapes`. Never
   "nothing happened".

   **A lambda capture** (a `dynamic` site) is followed through the capture fold (OI-150/OI-266,
   `value_index`), which DOES say which parameter of which body a capture lands on — this rule
   first said the facts do not, which was stale. A body that does nothing to that parameter (no
   call on it, no hand-off of it, no field write) cannot change the value, so the capture is
   not a hand-off. A body that does anything is `escapes`: when the body runs is not known, so
   what it does cannot be placed in the window. A capture the fold does not map is `escapes`
   (fix round 1, M6).
3. **An immutable value cannot be changed by a hand-off.** A hand-off whose parameter type (read
   off the site's own descriptor) is a primitive, `java.lang.String`, or a boxed primitive is not
   a hand-off for this rule; nor is any hand-off of, or call on, a value whose OWN type the facts
   state is one of those (its producer's declared return, a concat's `String`, a construction's
   type, a parameter's declared type) — SLF4J's `info(String, Object)` types a logged `String`
   `Object` (fix round 1, M1). **A compiler's null checks are not hand-offs either** — ruled
   by the user on 2026-11-02: a call to `kotlin.jvm.internal.Intrinsics`
   (`checkNotNullParameter`, `checkNotNullExpressionValue`, `checkNotNull`,
   `checkParameterIsNotNull`, `checkExpressionValueIsNotNull`) takes the value without
   handing it off, because the compiler, not the author, inserts these and they only check
   for null and throw. Recognised by the owner class alone, declared as catalog data
   (`value-models/compiler-null-checks.yml`, D02 §1f's `not_hand_offs`), since the walk names
   no language. This is a property of the JVM type, not of any method, so it is one
   structural rule (OI-143's ruling allows it), and it keeps `log.info(url)` before
   `client.get(url)` resolved.
4. **Paths are never merged into one answer.** Each path composes its own address; paths giving
   the same address are one row, different addresses one row each (enumerable is exact). A path
   whose part is unread or unknown gives its own row with peer NULL, path kept, `partial`; other
   paths keep their rows.
5. **A framework default is used only where it is proven.** On a path whose options object was
   built by the no-argument constructor and whose every call (rules 1-2) was read, a part no call
   set is the framework's own default, declared in the client model (`unset`; Vert.x: host
   `localhost`, port `80`, CP-56 row 132). Anywhere else the part is unknown. This reverses the
   Vert.x spec's §2a/item 23 ("unset defaults are never published"), a ruling made under the
   delegation, not the user's.
6. **A setter whose own argument has several values is unread** (`_Options._value`, unchanged):
   pairing two independent setters' candidates would publish combinations no path makes.

## 3. Not changed

- The Ktor block ladder (`_Ladder.base_of`) answers `non_enumerable` for two bases (ruling M-1).
  It does not lie, so it stays.
- A value written into a field and changed later through that field by another method is out of
  the window this rule reads; logged as an issue, not built.

## 4. Done when

- Each rule has a test that fails before the change, on `fixtures/orders-vertx-web` where it is a
  Vert.x shape and on a unit fixture where it is the walk.
- The full gate passes, and `scripts/field_check.py` is run: every moved count is explained per
  module, never re-pinned silently.
- D02 (the options `client_base`, `unset`), the Vert.x spec (§2a, §3d, item 23), the client
  model and COVERAGE's WebClient row say the new rules.
