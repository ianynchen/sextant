# Sextant

Sextant reads compiled code and produces an accurate, queryable model of a software
system: what it exposes, what it calls, what data crosses each boundary, and how the
pieces reach each other. Its outputs serve two readers equally — a person designing a
change, and an agent answering questions without scanning a codebase.

This file is the project's glossary. It defines what terms mean, not how anything works.

## Language

### Units of analysis

**Module**:
One buildable unit of code. A repository holds one or more.
_Avoid_: repo, repository, project, sub-project, package

**System**:
A set of modules analysed together so the connections between them become visible.
_Avoid_: estate, landscape, platform

**Service**:
A module that is deployed and participates in a system by exposing or consuming
endpoints.
_Avoid_: app, application, microservice

**Library**:
A module that is published for other modules to depend on, rather than deployed.

**Compiled library**:
A dependency read from its built artifacts — a jar, or a folder of class files —
without needing its source or its build.

**Library source**:
A dependency whose source participates in the build, so it is analysed as a module in
its own right.

**Component**:
A named grouping of symbols inside a service, describing a responsibility that the code
does not express structurally. Components are judgements, not facts, and never appear
without an overlay.
_Avoid_: layer, subsystem, slice

**Workspace**:
The store holding one module's or one system's facts and derived graph.

**Bundle**:
A portable, self-describing export of a workspace, used to move a module's analysis to
where a system is assembled.
_Avoid_: archive, package, dump

### Code facts

**Fact**:
One statement about code, produced by an extractor and never edited afterwards. Facts
are the only thing extraction produces; everything else is derived from them.

**Symbol**:
One code entity — a type, a function, a field, or a namespace — under an identifier
that is stable across runs and unique across an estate.
_Avoid_: node, entity, identifier, FQN

**Occurrence**:
A place in a document where a symbol appears.

**Edge**:
A relationship between two symbols.

**Shape**:
The structure of a payload: its fields, their types, and whether each is required.
Shapes are compared by wire identity, never by the name of the type carrying them.
_Avoid_: schema, model, DTO, contract

**Trace**:
The call structure reachable from one inbound endpoint, from its root to every terminal.
_Avoid_: path, flow, chain, tour

**Path**:
The set of all routes between two named symbols. Distinct from a trace, which starts at
an endpoint and is bounded by terminals rather than by a destination.

### Boundaries

**Endpoint**:
A place where something enters or leaves a process — an HTTP route, a SOAP operation, a
gRPC method, a message topic or subscription. Protocol is a property of an endpoint, not
a different kind of thing.
_Avoid_: route, API, channel, interface

**Inbound**:
An endpoint the module exposes. Every inbound endpoint is the root of a trace.

**Outbound**:
An endpoint the module calls. Every outbound endpoint is a terminal, and a candidate for
a link.

**Root**:
The kind of thing a trace starts from — an inbound endpoint, a scheduled job, or a
program entry point.

**Terminal**:
The kind of thing a trace stops at — an outbound call, a return, a silent end,
persistence, a thrown exception, an unresolved call, a handoff to another thread, or a
cycle.

**Link**:
A matched pair of one module's outbound endpoint and another module's inbound endpoint.
_Avoid_: connection, dependency, integration

**Alias**:
An alternative name a service answers to, used to resolve a call's target to a
participant.

**External participant**:
Something a system calls that is not one of its modules, named so that the dependency is
visible rather than unresolved.

### Trust

Three independent properties, deliberately never collapsed into one score. "Confidence"
is not used, because it means all three at once and therefore none of them.
_Avoid_: confidence, certainty, score, weight

**Resolution**:
How certain the target of a fact is, as one of four values:
- `resolved` — exactly one target, proven.
- `narrowed` — several targets, and the set is known to be complete.
- `partial` — several targets, and the set is known to be incomplete.
- `unresolved` — no target known, with a recorded reason.

**Evidence**:
What produced a fact — a compiler, syntax alone, a name match, a declared contract, a
person, or a model.

**Precedence**:
Which source wins when two of them claim the same thing. A person outranks code, and
code outranks a model.

**Candidate**:
One of the several possible targets a `narrowed` or `partial` fact carries.

**Unknown region**:
An unresolved call site reached while answering a question, reported with its location
so a person can look at what the analysis could not.

**Blast radius**:
The answer to "if this changes, what is affected", reported as three parts — what is
definitely affected, what may be, and which unknown regions were reached. Never a single
number.
_Avoid_: impact analysis, reach, fan-out

**Open question**:
A recorded disagreement between two sources that a person should settle, kept rather
than resolved silently.

**Drift**:
A disagreement between a contract as declared and the same contract as implemented.

### Extraction

**Extractor**:
The reader for one language or artifact kind. It emits facts and nothing else.
_Avoid_: parser, scanner, analyser

**Capability**:
A named thing an extractor can do. Extractors declare the capabilities they have and
engine styles require the ones they need, so a missing capability degrades a feature
visibly instead of silently.

**Catalog**:
Data describing what a framework's API means — which call is an outbound HTTP request,
which annotation declares a topic. Framework knowledge is catalog data, never code.
_Avoid_: rules, plugin, adapter

**Engine**:
A generic interpreter that reads catalogs and finds endpoints. An **engine style** is the
shape of pattern an engine matches, such as an annotation, a single call, or a chain of
calls building one request.

**Uncovered source**:
A source file the compiled artifacts do not account for, which makes an analysis partial
and must be reported as such.

### Overlays

**Overlay**:
Anything layered onto the code-derived graph that did not come from reading code. An
overlay never produces facts and never overrides evidence silently.
_Avoid_: sidecar, annotation, enrichment, plugin

**Curation**:
An overlay written by a person, carrying the highest precedence in the model. A curated
statement is treated by every consumer as ground truth.

**Proposal**:
A candidate Sextant found but will not act on alone, written for a person to accept,
reject, or amend into a curation.
