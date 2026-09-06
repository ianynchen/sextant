"""`## Traces` (2Q `G4`/`I3`, FR-6/FR-7) — the walk, rendered.

**The change that puts a trace in front of a reader**, which is what makes
every under-report in this section a wrong answer rather than a silence. The
tests below are grouped by what could be silently wrong:

- a step, or a whole trace, that the renderer drops;
- an arrow that lands on a lifeline the walk never entered, or that merges two
  types into one;
- a diagram that leaves something out and does not say so;
- a marker — `dynamic`, a stop reason, a `declared` type — that would let a
  reader read reachability as execution.

Built from hand-written `Trace` values rather than from a walked workspace, the
`test_diagrams.py` precedent: this file tests what the renderer does with a
trace, and a compiled fixture would make that answer depend on having one.
"""

import pytest

from sextant.application.query.trace import Step, Trace
from sextant.application.resolve.roots import Root, RootIdentity
from sextant.domain.closed_sets import Resolution, RootKind, TraceStop
from sextant.domain.redaction import RedactionRules, Redactor
from sextant.egress.render.document import (
    MachineDiagram,
    MachineTable,
    Run,
    _returned_value,
    _sequence_view,
    _trace_sections,
)

REDACTOR = Redactor.from_rules()


def _step(
    *,
    depth: int = 1,
    caller: str = "s maven c 1 a/Api#list().",
    ordinal: int = 0,
    invoke_kind: str = "virtual",
    target: str = "a/Service#run().",
    callee: str | None = "s maven c 1 a/Service#run().",
    result: int | None = None,
    stop: TraceStop | None = None,
    returns: tuple[tuple[int, str], ...] = (),
) -> Step:
    return Step(
        depth=depth,
        caller=caller,
        ordinal=ordinal,
        invoke_kind=invoke_kind,
        target=target,
        callee=callee,
        result=result,
        resolution=Resolution.RESOLVED,
        stop=stop,
        returns=returns,
    )


def _address(method: str = "GET", path: str = "/order/list") -> RootIdentity:
    return RootIdentity(protocol="http", method=method, path=path)


def _trace(
    *steps: Step,
    response: tuple[tuple[int, str], ...] = (),
    kind: RootKind = RootKind.INBOUND_ENDPOINT,
    identities: tuple[RootIdentity, ...] = (),
) -> Trace:
    return Trace(
        root=Root(handler="s maven c 1 a/Api#list().", kind=kind, identities=identities),
        steps=steps,
        response=response,
    )


def _diagram(trace: Trace) -> MachineDiagram:
    diagrams = [s for s in _trace_sections([trace], REDACTOR) if isinstance(s, MachineDiagram)]
    assert len(diagrams) == 1, diagrams
    return diagrams[0]


def _step_table(trace: Trace) -> MachineTable:
    tables = [
        entry.table
        for section in _trace_sections([trace], REDACTOR)
        if hasattr(section, "entries")
        for entry in section.entries
        if entry.table is not None
    ]
    assert len(tables) == 1, tables
    return tables[0]


# --- nothing is dropped ---------------------------------------------------


def test_every_step_of_the_walk_becomes_a_row():
    """The second cardinal sin in one test. A renderer that filtered — the
    JDK calls, say, or the `revisited` steps that lead nowhere — would produce
    a shorter, tidier trace that is not the trace: a call the document does
    not show is a call the document denies, and nothing in the output would
    say a filter ran."""
    trace = _trace(
        _step(
            ordinal=0, target="java/lang/Integer#intValue().", callee=None, stop=TraceStop.BOUNDARY
        ),
        _step(ordinal=1),
        _step(ordinal=2, stop=TraceStop.REVISITED),
        _step(ordinal=3, stop=TraceStop.CYCLE),
        _step(ordinal=4, stop=TraceStop.DEPTH_LIMIT),
    )
    assert len(_step_table(trace).rows) == 5
    # `sequenceDiagram`, three lifelines (Api, Integer, Service), five arrows.
    assert len(_diagram(trace).mermaid.splitlines()) == 1 + 3 + 5


def test_a_root_that_calls_nothing_still_gets_a_block_and_a_lifeline():
    """`/admin/refreshToken` on `mall-admin` is pure string work and reaches
    no terminal at all. That is an ANSWER — the roadmap names it as one of the
    two correct zeroes — so the block says so in words rather than showing an
    empty table, and the diagram draws the root's own lifeline rather than
    nothing."""
    sections = _trace_sections([_trace()], REDACTOR)
    detail = next(s for s in sections if hasattr(s, "entries"))
    assert any(
        entry.body is not None and "calls nothing" in entry.body[0][1] for entry in detail.entries
    )
    assert "participant a0 as Api" in _diagram(_trace()).mermaid


def test_a_module_with_no_roots_says_so_rather_than_dropping_the_section():
    """The `Scheduled work`/`Error handling` rule, not the `Open questions`
    one: "nothing in this module starts any work" is a finding, and a section
    that simply disappears leaves a reader unable to tell that from a Sextant
    that never walked (FR-17)."""
    sections = _trace_sections([], REDACTOR)
    assert len(sections) == 1
    assert sections[0].runs == (("text", "None found."),)


# --- a reader can find their endpoint (2Q close, defect 1) ----------------


def _summary_row(trace: Trace) -> tuple[tuple[Run, ...], ...]:
    tables = [s for s in _trace_sections([trace], REDACTOR) if isinstance(s, MachineTable)]
    assert len(tables) == 1, tables
    assert len(tables[0].rows) == 1
    return tables[0].rows[0]


def _header_text(trace: Trace) -> str:
    detail = next(s for s in _trace_sections([trace], REDACTOR) if hasattr(s, "entries"))
    return "".join(content for _kind, content in detail.entries[0].title)


@pytest.mark.pins("render_trace.a-trace-is-named-by-the-address-that-reaches-it")
def test_a_trace_carries_the_address_a_reader_searches_for():
    """**The defect this pins shipped, and an hour later was the reason 2Q was
    not usable.** A trace named by its handler descriptor and its kind alone
    puts `GET /order/list` nowhere in the section: to find the trace for an
    endpoint you had to already know the handler descriptor, which is the one
    thing a reader looking up a URL does not have.

    Both places a reader lands are asserted — the summary row they scan and
    the block header they land on — because either alone leaves half the
    section unsearchable."""
    trace = _trace(_step(), identities=(_address(),))
    assert (("code", "GET /order/list"),) in _summary_row(trace)
    assert "GET /order/list" in _header_text(trace)


def test_a_root_no_address_reaches_says_so_in_words_not_with_a_dash():
    """A scheduled job is started by a clock: it HAS no wire address, which is
    an absence rather than a value that went unread. The em dash means
    "nothing recorded" everywhere else in this document, so using it here
    would report a gap that does not exist — and inventing a label for the
    clock would be the fabrication `roots` refuses to make upstream."""
    trace = _trace(_step(), kind=RootKind.SCHEDULED)
    assert (("text", "no wire address"),) in _summary_row(trace)
    assert "—" not in _header_text(trace).replace(" — scheduled", "")


def test_a_handler_serving_several_addresses_is_one_trace_naming_all_of_them():
    """One root, one walk, one block — and every address that reaches it, in
    the roots table's own order. Printing the first would publish a coin toss;
    printing three blocks would publish one answer three times."""
    trace = _trace(_step(), identities=(_address(), _address(method="POST", path="/order/add")))
    assert (("code", "GET /order/list; POST /order/add"),) in _summary_row(trace)
    assert (
        len([s for s in _trace_sections([trace], REDACTOR) if isinstance(s, MachineDiagram)]) == 1
    )


def test_a_roots_path_passes_the_redactor_exactly_as_an_endpoints_does():
    """`path` is one of the two columns that can carry a whole address, so a
    credential in one is an exposure at the render exit (2K design §1). The
    trace section reaches the same `_wire_address` the endpoint table does, so
    it inherits that masking rather than re-implementing it — and this is the
    test that fails if it ever stops doing so."""
    redactor = Redactor.from_rules(RedactionRules(value_patterns=("s3cret",)))
    trace = _trace(_step(), identities=(RootIdentity("http", "GET", "/x?token=s3cret"),))
    tables = [s for s in _trace_sections([trace], redactor) if isinstance(s, MachineTable)]
    assert "s3cret" not in "".join(content for _kind, content in tables[0].rows[0][0])


# --- the document at scale (GUIDELINES §8.4) ------------------------------


def _many(count: int, steps_each: int = 10) -> list[Trace]:
    """`count` traces of `steps_each` steps, each rooted at its own address —
    the shape `mall-admin` has 160 of, in miniature."""
    return [
        Trace(
            root=Root(
                handler=f"s maven c 1 a/Api{index}#list().",
                kind=RootKind.INBOUND_ENDPOINT,
                identities=(_address(path=f"/order/{index}"),),
            ),
            steps=tuple(_step(ordinal=ordinal) for ordinal in range(steps_each)),
        )
        for index in range(count)
    ]


def _paragraphs(sections: list[object]) -> list[str]:
    return [
        "".join(content for _kind, content in section.runs)
        for section in sections
        if type(section).__name__ == "MachineParagraph"
    ]


@pytest.mark.pins("render_trace.every-trace-is-listed-even-when-it-is-not-drawn")
def test_a_trace_the_budget_did_not_reach_is_still_a_row_with_its_own_counts():
    """**Never drop a trace silently.** The budget decides how much of the
    document a trace gets, never whether the reader is told it exists: every
    root keeps its summary row, its addresses, its depth and its step count,
    so a reader can see that a trace was walked and how big it is even where
    its steps are not drawn. A root that vanished from this table would be a
    walk the document denies, which is the second cardinal sin."""
    traces = _many(20)
    sections = _trace_sections(traces, REDACTOR, budget=50)
    table = next(s for s in sections if isinstance(s, MachineTable))
    assert len(table.rows) == 20
    assert [row[-1] for row in table.rows].count((("text", "summary only"),)) > 0
    assert (("code", "GET /order/19"),) in [row[0] for row in table.rows]


@pytest.mark.pins("render_trace.a-budgeted-section-says-what-it-did-not-draw")
def test_the_section_says_how_much_of_itself_it_drew_and_how_to_get_the_rest():
    """M07: *"every reduced output states that it was reduced"*. The reduction
    here is whole BLOCKS rather than steps inside a diagram, so it cannot ride
    on `MachineDiagram.elides` — a block that is not drawn has no diagram to
    carry a caption — and it is a sentence under the summary table instead,
    where a reader meets the boundary. It names the count and the command,
    because "what was left out" without "how to get it" is half an answer."""
    sentence = " ".join(_paragraphs(_trace_sections(_many(20), REDACTOR, budget=50)))
    assert "5 of 20 traces" in sentence
    assert "IS THE BRIEF ONE" in sentence
    assert "without --brief" in sentence


def test_a_trace_that_is_drawn_is_drawn_whole():
    """Half a trace is the under-report this section exists not to be, so the
    budget is spent per TRACE and never per step: the last trace drawn takes
    the total past the bound rather than stopping mid-walk."""
    sections = _trace_sections(_many(20), REDACTOR, budget=50)
    tables = [
        entry.table
        for section in sections
        if hasattr(section, "entries")
        for entry in section.entries
        if entry.table is not None
    ]
    assert [len(table.rows) for table in tables] == [10] * 5


def test_only_the_traces_drawn_in_full_carry_a_diagram():
    """A diagram belongs to a block: a trace the brief document did not draw
    has no diagram, rather than a diagram floating free of the steps it
    draws."""
    sections = _trace_sections(_many(20), REDACTOR, budget=50)
    assert len([s for s in sections if isinstance(s, MachineDiagram)]) == 5


@pytest.mark.pins("render_trace.the-default-document-draws-every-trace")
def test_the_default_draws_every_trace_however_many_there_are():
    """**The default is the whole truth** (GUIDELINES §8.4, ruled 2026-09-06:
    *"we should be focused on telling the truth, not the amount of
    information"*). This section shipped for one commit with the budget as its
    DEFAULT, so a module with 160 roots documented 37 of them unless a reader
    knew a flag existed — and the reader who did not know is exactly the one
    who cannot tell an incomplete document from a complete one.

    Asserted with no `budget` argument at all, because the defect this pins is
    a DEFAULT: passing `budget=None` here would test a value no caller passes
    and would still pass on the day the default flipped back.

    Sixty traces of ten steps, deliberately: at 600 steps the old default of
    500 BITES, so restoring it drops ten traces and ten diagrams. The twenty
    the tests above use total 200 steps and would fit inside the old bound
    unchanged — a set too small to notice is how a ratchet passes over the
    mutation it names."""
    sections = _trace_sections(_many(60), REDACTOR)
    assert len([s for s in sections if isinstance(s, MachineDiagram)]) == 60
    assert "Every trace is rendered in full" in " ".join(_paragraphs(sections))
    assert "BRIEF" not in " ".join(_paragraphs(sections))


def test_the_brief_section_is_byte_identical_across_two_renders():
    """NFR-1 over the selection itself: which traces are drawn is a function
    of their order and their step counts, both fixed by `roots`, so two runs
    over one workspace choose the same ones."""
    traces = _many(20)
    assert _trace_sections(traces, REDACTOR, budget=50) == _trace_sections(
        traces, REDACTOR, budget=50
    )


# --- the arrow lands where the walk went ----------------------------------


@pytest.mark.pins("render_trace.an-arrow-ends-at-the-body-that-was-expanded")
def test_an_arrow_ends_at_the_expanded_body_not_at_the_declared_interface():
    """The defect this pins was in the first rendering of `/order/list`: the
    arrow for `orderService.list(...)` landed on `OmsOrderService`, and then
    `OmsOrderServiceImpl` sent four messages nobody had ever sent IT — a
    lifeline appearing from nowhere, in a diagram a reader cannot follow.

    An arrow ends at the body the walk expanded, because that is the lifeline
    whose own calls come next. Nothing is lost by it: the declared type is
    named on the message, and the step table carries both descriptors."""
    trace = _trace(
        _step(
            invoke_kind="interface",
            target="a/OrderService#list().",
            callee="s maven c 1 a/OrderServiceImpl#list().",
        ),
        _step(
            depth=2,
            caller="s maven c 1 a/OrderServiceImpl#list().",
            target="a/OrderMapper#selectAll().",
            callee=None,
            stop=TraceStop.BOUNDARY,
        ),
    )
    mermaid = _diagram(trace).mermaid

    assert "participant a1 as OrderServiceImpl" in mermaid
    assert "OrderService\n" not in mermaid  # the interface is no lifeline
    assert "a0->>a1: list (declared OrderService)" in mermaid
    # …and the impl's own call leaves the lifeline the first arrow arrived at,
    # which is the whole property a dangling lifeline breaks.
    assert "a1->>a2: selectAll [boundary]" in mermaid


def test_the_step_table_keeps_both_descriptors_where_dispatch_resolved_one():
    """The mirror of the test above: what the diagram compresses into
    `(declared X)`, the table spells out in full. A reader looking for
    `orderService.list(...)` in the source finds the interface here, and the
    body the walk expanded beside it."""
    trace = _trace(
        _step(
            invoke_kind="interface",
            target="a/OrderService#list().",
            callee="s maven c 1 a/OrderServiceImpl#list().",
        )
    )
    call = _step_table(trace).rows[0][2]
    assert call == (
        ("code", "a/OrderService#list()."),
        ("text", " → "),
        ("code", "a/OrderServiceImpl#list()."),
    )


def test_an_ordinary_call_names_one_descriptor_not_the_same_one_twice():
    """The near-miss for the pair above. Where dispatch resolved to the very
    method the compiler named — every static, special and same-class virtual
    call, which is most of them — there is no second answer to give, and
    `X#m → X#m` would be noise a reader has to learn to ignore."""
    call = _step_table(_trace(_step())).rows[0][2]
    assert call == (("code", "a/Service#run()."),)


def test_a_boundary_step_names_the_target_the_compiler_wrote():
    """A terminal's whole identity is its descriptor: `terminal_kind` has no
    producer, so nothing here says whether `com/macro/mall/dao/OmsOrderDao` is
    a database and `java/lang/Integer` is not. The package is what lets a
    reader tell them apart, which is why this column is never shortened."""
    trace = _trace(
        _step(target="java/lang/Integer#intValue().", callee=None, stop=TraceStop.BOUNDARY)
    )
    assert _step_table(trace).rows[0][2] == (("code", "java/lang/Integer#intValue()."),)


# --- two types are never one lifeline -------------------------------------


@pytest.mark.pins("render_trace.two-types-one-simple-name-are-two-lifelines")
def test_two_types_sharing_a_simple_name_are_two_distinguishable_lifelines():
    """`_disambiguated_shape_names`' rule, applied per diagram. Two lifelines
    both labelled `Order` do not merely read badly — a reader takes them for
    one type, and the diagram then asserts a call between things that never
    touched."""
    trace = _trace(
        _step(target="a/one/Order#save().", callee=None, stop=TraceStop.BOUNDARY),
        _step(ordinal=1, target="a/two/Order#save().", callee=None, stop=TraceStop.BOUNDARY),
    )
    mermaid = _diagram(trace).mermaid

    assert "participant a1 as a/one/Order" in mermaid
    assert "participant a2 as a/two/Order" in mermaid
    assert " as Order\n" not in mermaid


def test_a_simple_name_nothing_collides_with_stays_short():
    """The near-miss beside it: the fallback fires on a COLLISION and on
    nothing else. A diagram that spelled every lifeline as a full package path
    would be unreadable, and a rule that could never decline would look
    identical to one that always fires."""
    trace = _trace(_step(target="a/one/Order#save().", callee=None, stop=TraceStop.BOUNDARY))
    assert "participant a1 as Order" in _diagram(trace).mermaid


def test_one_type_reached_twice_is_one_lifeline():
    """A participant is keyed by its owning TYPE, so the same class called
    three times is one lifeline with three arrows — not three lifelines a
    reader would read as three collaborators."""
    trace = _trace(
        _step(ordinal=0, target="a/Service#run().", callee=None, stop=TraceStop.BOUNDARY),
        _step(ordinal=1, target="a/Service#stop().", callee=None, stop=TraceStop.BOUNDARY),
    )
    assert _diagram(trace).mermaid.count("participant ") == 2


# --- the diagram says what it leaves out ----------------------------------


@pytest.mark.pins("render_trace.every-sequence-diagram-states-its-elision")
def test_every_sequence_diagram_states_its_elision():
    """`DiagramClaim.elides`' own rule, applied to the machine half: *a
    simplified diagram that does not say it is simplified is a diagram that
    lies about the system's size*. A trace diagram is simplified by
    construction — it draws no lifeline for a body the walk never entered —
    so the statement is not optional on any of them."""
    trace = _trace(_step(callee=None, stop=TraceStop.BOUNDARY))
    elides = _diagram(trace).elides
    assert elides is not None
    assert "Reachability, not execution" in elides


def test_the_elision_counts_each_kind_of_stop_the_walk_recorded():
    """The counts are the honest part. "This diagram is complete" and "this
    diagram is complete as far as we looked" are the same picture, and only a
    number separates them."""
    trace = _trace(
        _step(ordinal=0, callee=None, stop=TraceStop.BOUNDARY),
        _step(ordinal=1, callee=None, stop=TraceStop.BOUNDARY),
        _step(ordinal=2, stop=TraceStop.REVISITED),
        _step(ordinal=3, stop=TraceStop.CYCLE),
        _step(ordinal=4, stop=TraceStop.DEPTH_LIMIT),
    )
    elides = _diagram(trace).elides or ""

    assert "which the walk did not enter: 2." in elides
    assert "not repeated here: 1." in elides
    assert "stated and not followed: 1." in elides
    assert "absent from this diagram: 1." in elides


def test_a_stop_the_walk_did_not_record_is_not_mentioned_at_all():
    """The near-miss for the counts: a clause per stop kind whether or not it
    happened would put `0 recursive arrows` on every diagram in the estate,
    and a reader learns to skip a sentence that is always there. Absence of a
    clause means absence of the thing."""
    elides = _diagram(_trace(_step(callee=None, stop=TraceStop.BOUNDARY))).elides or ""

    assert "which the walk did not enter: 1." in elides
    assert "recursion" not in elides
    assert "depth bound" not in elides


# --- markers a reader would be misled without -----------------------------


@pytest.mark.pins("render_trace.a-dynamic-step-says-the-body-is-created-not-called")
def test_a_dynamic_step_says_the_body_is_created_not_called_there():
    """An `invokedynamic` site names the body it CREATES; the lambda runs
    later, elsewhere, if at all. An arrow reading like an ordinary call there
    is the one place this diagram could assert something the graph does not
    say — a `list.forEach(x -> mapper.insert(x))` drawn as an insert that
    happens at that line."""
    trace = _trace(
        _step(
            invoke_kind="dynamic",
            target="a/Api#lambda$list$0().",
            callee="s maven c 1 a/Api#lambda$list$0().",
        )
    )
    assert "a0->>a0: lambda$list$0 (dynamic)" in _diagram(trace).mermaid


def test_an_ordinary_call_carries_no_dynamic_marker():
    """The near-miss: the marker means something only if most arrows do not
    carry it."""
    assert "(dynamic)" not in _diagram(_trace(_step())).mermaid


@pytest.mark.pins("render_trace.an-arrow-says-where-the-walk-stopped")
def test_each_stop_is_marked_on_the_arrow_that_hit_it():
    """Where a trace ENDS is the single most important fact in its diagram,
    and an unmarked arrow into a lifeline nobody entered looks exactly like an
    arrow into one that was fully explored."""
    for stop in TraceStop:
        trace = _trace(
            _step(callee=None if stop is TraceStop.BOUNDARY else "s maven c 1 a/S#r().", stop=stop)
        )
        assert f"[{stop}]" in _diagram(trace).mermaid


def test_an_expanded_step_carries_no_stop_marker():
    """The near-miss beside it. A step with no stop was expanded and its own
    calls follow — marking it would say the trace ended where it continued."""
    mermaid = _diagram(_trace(_step())).mermaid
    assert "[" not in mermaid.split("\n")[-1]


def test_a_revisited_step_is_a_row_and_never_a_copied_subtree():
    """The modelling choice the walk's own report flagged for a renderer to
    settle. A method is expanded once per trace, so the second route to it has
    no subtree of its own here — and the two wrong answers are copying the
    subtree (exponential on an ordinary diamond, D01's stated reason for not
    storing traces) and dropping the call (a call the document denies). The
    row stays, and its `Stop` says where the subtree is."""
    trace = _trace(_step(ordinal=0), _step(ordinal=1, stop=TraceStop.REVISITED))
    rows = _step_table(trace).rows

    assert len(rows) == 2
    assert rows[0][7] == (("text", "—"),)
    assert rows[1][7] == (("text", "revisited"),)


def test_the_reachability_statement_is_in_the_prose_and_in_every_diagram():
    """Said twice on purpose. A reader who skims the preamble still meets it
    under the diagram, which is the artifact most likely to be screenshotted
    out of the document and read on its own — and a sequence diagram is
    exactly the shape that LOOKS like an execution."""
    sections = _trace_sections([_trace(_step())], REDACTOR)
    preamble = " ".join(run[1] for item in sections[0].items for run in item)

    assert "REACHABILITY, never execution" in preamble
    assert "Reachability, not execution" in (_diagram(_trace(_step())).elides or "")


# --- values are printed, never interpreted --------------------------------


def test_a_void_return_and_an_unnameable_one_are_different_answers():
    """`method_returns` keeps the distinction deliberately (D00 §5): a JSON
    `null` value is a method that returns NOTHING, while `{"kind":
    "unresolved"}` is a method whose answer this pass could not name. Reading
    them as one would report every void method as an analysis failure, or
    every analysis failure as a void."""
    assert _returned_value(None, REDACTOR) == "void"
    assert _returned_value({"kind": "unresolved", "source": 13}, REDACTOR) == "unresolved value 13"


def test_two_returns_are_printed_as_two_possible_answers():
    """A method with two `return` statements has two, and neither is the one
    that runs. Printing the first would publish a coin toss as the response —
    `/admin/refreshToken` returns `CommonResult#failed` OR `#success`, and a
    document naming one of them is wrong half the time."""
    trace = _trace(
        response=(
            (0, '{"kind":"unresolved","source":21}'),
            (1, '{"kind":"unresolved","source":47}'),
        )
    )
    detail = next(s for s in _trace_sections([trace], REDACTOR) if hasattr(s, "entries"))
    response = next(e for e in detail.entries if e.title == (("text", "Response"),))
    assert response.body == (("text", "unresolved value 21; unresolved value 47"),)


def test_an_array_argument_prints_its_elements_including_an_empty_one():
    """Capability 9.15's own rule: an EMPTY `elements` list is a zero-length
    varargs call, which is a real call rather than a failure to read one, so
    `[]` is printed rather than skipped."""
    assert _returned_value({"kind": "array", "elements": []}, REDACTOR) == "array []"
    assert (
        _returned_value({"kind": "array", "elements": [{"kind": "int", "value": 1}]}, REDACTOR)
        == "array [int 1]"
    )


def test_a_kind_this_renderer_has_never_heard_of_still_prints():
    """The grammar is closed today and this renderer does not enforce it. A
    kind added to `CallArgument` and not to this file must show up as itself,
    because the alternative is a return value that silently disappears from
    every document until somebody notices."""
    assert _returned_value({"kind": "quantum", "source": 4}, REDACTOR) == "quantum value 4"
    assert _returned_value(["not", "a", "shape"], REDACTOR).startswith("unreadable ")


def test_a_returned_string_literal_passes_the_redactor():
    """The one place this section renders a VALUE rather than a name. A
    hard-coded credential returned from a method is the same exposure
    `_wire_identity` already masks in a path, and redaction is default-on at
    this exit (2K design §1)."""
    redactor = Redactor.from_rules(RedactionRules(value_patterns=["sk-[a-z0-9]+"]))
    rendered = _returned_value({"kind": "string", "value": "sk-abc123"}, redactor)
    assert "sk-abc123" not in rendered


# --- ordering is the walk's, not this renderer's --------------------------


def test_participants_and_messages_follow_the_walk_and_nothing_re_sorts_them():
    """NFR-1 binds diagram node ordering as well as content. The walk's own
    depth-first order over `call_edges` IS the source order of the statements,
    so a renderer that sorted participants alphabetically would produce a
    diagram that reads in an order the code does not have — and, worse, a
    different one whenever a class is renamed."""
    trace = _trace(
        _step(ordinal=0, target="a/Zeta#one().", callee=None, stop=TraceStop.BOUNDARY),
        _step(ordinal=1, target="a/Alpha#two().", callee=None, stop=TraceStop.BOUNDARY),
    )
    participants, messages = _sequence_view(trace)

    assert [p.label for p in participants] == ["Api", "Zeta", "Alpha"]
    assert [m.label for m in messages] == ["one [boundary]", "two [boundary]"]


def test_two_renders_of_one_trace_are_byte_identical():
    """NFR-1 stated as the property rather than as an ordering. Nothing here
    reads a clock, iterates an unordered set, or depends on a dict built from
    one."""
    trace = _trace(
        _step(ordinal=0, target="a/one/Order#save().", callee=None, stop=TraceStop.BOUNDARY),
        _step(ordinal=1, target="a/two/Order#save().", callee=None, stop=TraceStop.BOUNDARY),
        _step(ordinal=2, stop=TraceStop.REVISITED),
    )
    assert _diagram(trace).mermaid == _diagram(trace).mermaid
    assert _diagram(trace).elides == _diagram(trace).elides
