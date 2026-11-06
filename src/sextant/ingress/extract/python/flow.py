"""Each call's place in its body's control flow (D00 §5 `call_site` rule 9): `dominator`,
`on_every_exit`, `post_dominator`, `reaches_return` and `loop_group`, with the meanings the
JVM extractor gives them (`MethodFlow.FlowGraph`).

`calls.py` drives a `Flow` while it reads one body, statement by statement: the graph is
built from the syntax tree's own structure, never recovered from jumps. As on the JVM, a
call is two nodes, BEFORE it runs and AFTER it completed; node 0 is the body's entry and
node 1 its normal exit (a `return`, or the end of the body).

Exceptions, read as the JVM pass reads its handler edges:
- every expression may raise, so inside a `try` body every point (the start of a statement
  that may raise, a call's BEFORE, and the point after it while the statement may still
  raise) has an edge to the handlers. A call that is all of its statement (`a()`,
  `x = a()`, `return a()`) leaves nothing to raise once it completed, as the JVM's
  `try { a(); } catch` handler is entered only where `a` did not complete;
- a `with` block's manager may swallow what the block raised, so the block may end at any
  point and the code after it still run; or raise it again;
- a `finally` runs again on every way out of its `try`: the normal end, an exception it
  raises again, a `return`, a `break` and a `continue`. Its graph is copied for each, as
  javac copies a `finally` block, and a call in it is one site with several copies;
- `raise`, an exception a `with` or a `finally` raises again, and a failing `assert` lead
  nowhere: as a JVM `ATHROW`, they are a path that may leave the body even where a handler
  covers them. An exception no handler of the body takes leaves with no edge, as on the
  JVM.

`python -O` drops every `assert`, so its test is a branch that may be skipped. A generator
expression runs when it is consumed, possibly after the body returned: its calls have no
`post_dominator` and do not reach a return.
"""

from dataclasses import dataclass, field

_ENTRY = 0
_EXIT = 1
# The ways out of a `try` that run its `finally` again before going on.
_EXCEPTION = "exception"
_RETURN = "return"
_BREAK = "break"
_CONTINUE = "continue"
_JUMPS = (_RETURN, _BREAK, _CONTINUE)


@dataclass
class Loop:
    head: int
    # Where a `break` goes: the end of the loop, after its `else`.
    exit: int
    # Where the loop ends without a `break` (to its `else`); None for `while True`.
    done: int | None = None


@dataclass
class Finally:
    # One entry per way out, each a node its copy of the `finally` starts from.
    entries: dict[str, int]
    # The first node of the `finally` as read, and the point where it ends.
    first: int = -1


@dataclass
class Try:
    # Where an exception raised in the body goes: the handlers, in written order.
    dispatch: int
    final: Finally | None
    # Where the next handler is tried; None after a bare `except:`.
    untried: int | None = None
    # Each point the statement ends at normally.
    ends: list[int | None] = field(default_factory=list)


@dataclass
class _Site:
    ordinal: int
    # The fact's index in the reader's fact list.
    index: int
    # (BEFORE, AFTER) of each copy: more than one only in a copied `finally`.
    copies: list[tuple[int, int]]
    deferred: bool


class Flow:
    """The control-flow graph of one body, built while the body is read."""

    def __init__(self) -> None:
        self._successors: list[list[int]] = [[], []]
        self._entered = [True, False]
        self._current: int | None = _ENTRY
        # Where an exception raised here goes, innermost last.
        self._handlers: list[int] = []
        # The loops and `finally` blocks a jump leaves through, innermost last.
        self._jumps: list[Loop | Finally] = []
        self._sites: list[_Site] = []
        self._deferred = 0

    # -- building --------------------------------------------------------------------------

    def _raw(self) -> int:
        self._successors.append([])
        self._entered.append(False)
        return len(self._successors) - 1

    def _node(self) -> int:
        """A point of the body: inside a protected region, it may raise to its handler."""
        node = self._raw()
        if self._handlers:
            self._edge(node, self._handlers[-1])
        return node

    def _edge(self, source: int, target: int) -> None:
        self._successors[source].append(target)
        self._entered[target] = True

    def statement(self) -> None:
        """A statement that may raise starts here: inside a protected region, a point that
        raises to the region's handler, unless the point reached already does."""
        current = self._current
        if (
            current is not None
            and self._handlers
            and self._handlers[-1] not in self._successors[current]
        ):
            node = self._node()
            self._edge(current, node)
            self._current = node

    def here(self) -> int | None:
        """The point reached; None where no path reaches it."""
        return self._current

    def at(self, point: int | None) -> None:
        self._current = point

    def join(self, points: list[int | None]) -> int | None:
        """Continue from wherever one of `points` left off."""
        reached = list(dict.fromkeys(p for p in points if p is not None))
        if len(reached) <= 1:
            self._current = reached[0] if reached else None
            return self._current
        node = self._node()
        for point in reached:
            self._edge(point, node)
        self._current = node
        return node

    def site(self, ordinal: int, index: int) -> None:
        before = self._node()
        if self._current is not None:
            self._edge(self._current, before)
        after = self._node()
        self._edge(before, after)
        self._sites.append(_Site(ordinal, index, [(before, after)], self._deferred > 0))
        self._current = after

    def quiet(self) -> None:
        """The call just completed was all of its statement: nothing raises after it."""
        current = self._current
        if (
            current is not None
            and self._sites
            and self._sites[-1].copies[0][1] == current
            and len(self._successors[current]) == 1
        ):
            self._successors[current].clear()

    def jump(self, kind: str) -> None:
        """`return`, `break` or `continue`: through every `finally` on the way."""
        if self._current is not None:
            target = self._jump_target(kind, len(self._jumps))
            if target is not None:
                self._edge(self._current, target)
        self._current = None

    def _jump_target(self, kind: str, depth: int) -> int | None:
        for frame in reversed(self._jumps[:depth]):
            if isinstance(frame, Finally):
                return frame.entries[kind]
            if kind == _BREAK:
                return frame.exit
            if kind == _CONTINUE:
                return frame.head
        return _EXIT if kind == _RETURN else None

    def raises(self) -> None:
        """`raise`: to the handlers, and out of the body."""
        if self._current is not None:
            self._throw(self._current)
        self._current = None

    def _throw(self, source: int) -> None:
        self._edge(source, self._raw())
        if self._handlers:
            self._edge(source, self._handlers[-1])

    def defer(self, deferred: bool) -> None:
        """Enter (True) or leave (False) the per-element part of a generator expression."""
        self._deferred += 1 if deferred else -1

    # -- loops -----------------------------------------------------------------------------

    def loop(self) -> Loop:
        head = self._node()
        if self._current is not None:
            self._edge(self._current, head)
        self._current = head
        loop = Loop(head, self._node())
        self._jumps.append(loop)
        return loop

    def loop_tested(self, loop: Loop, *, endless: bool = False) -> None:
        """The loop's test was read: from here it ends, unless it is `while True`."""
        loop.done = None if endless else self._current

    def loop_test(self, loop: Loop) -> None:
        """A comprehension's `if`: where it is false, the next element is taken."""
        if self._current is not None:
            self._edge(self._current, loop.head)

    def loop_body_end(self, loop: Loop) -> None:
        if self._current is not None:
            self._edge(self._current, loop.head)
        self._jumps.pop()
        self._current = loop.done

    def loop_end(self, loop: Loop) -> None:
        """After the `else`: where the loop ended, or where a `break` left it."""
        self.join([self._current, loop.exit if self._entered[loop.exit] else None])

    # -- try -------------------------------------------------------------------------------

    def try_body(self, *, has_finally: bool) -> Try:
        final = None
        if has_finally:
            final = Finally({kind: self._raw() for kind in (_EXCEPTION, *_JUMPS)})
            self._jumps.append(final)
        attempt = Try(self._raw(), final)
        attempt.untried = attempt.dispatch
        self._handlers.append(attempt.dispatch)
        return attempt

    def try_else(self, attempt: Try) -> None:
        """The body ended normally; the `else` and the handlers raise to the `finally`."""
        self._handlers.pop()
        if attempt.final is not None:
            self._handlers.append(attempt.final.entries[_EXCEPTION])

    def try_handlers(self, attempt: Try) -> None:
        attempt.ends.append(self._current)

    def handler(self, attempt: Try) -> None:
        """The next handler is tried: its type is read where the last one did not match."""
        self._current = attempt.untried

    def handler_matched(self, attempt: Try, *, catches_all: bool) -> None:
        attempt.untried = None if catches_all else self._current

    def handler_end(self, attempt: Try) -> None:
        attempt.ends.append(self._current)

    def try_finally(self, attempt: Try) -> None:
        """No handler took the exception: it goes through the `finally`, or on out."""
        final = attempt.final
        if final is not None:
            self._handlers.pop()
            self._jumps.pop()
        if attempt.untried is not None:
            if final is not None:
                self._edge(attempt.untried, final.entries[_EXCEPTION])
            elif self._handlers:
                self._edge(attempt.untried, self._handlers[-1])
        if final is None:
            self.join(attempt.ends)
            return
        final.first = self._node()
        for end in attempt.ends:
            if end is not None:
                self._edge(end, final.first)
        self._current = final.first

    def try_end(self, attempt: Try) -> None:
        """The `finally` was read once, from the normal end. Each other way out that is
        taken runs a copy of it, and then goes on its way."""
        final = attempt.final
        if final is None:
            return
        first, last, end = final.first, len(self._successors), self._current
        for kind, entry in final.entries.items():
            if not self._entered[entry]:
                continue
            copy = self._copy(first, last)
            self._edge(entry, copy[first])
            if end is None:
                continue
            if kind == _EXCEPTION:
                self._throw(copy[end])
            else:
                target = self._jump_target(kind, len(self._jumps))
                if target is not None:
                    self._edge(copy[end], target)
        self._current = end

    def _copy(self, first: int, last: int) -> dict[int, int]:
        """Nodes `first` to `last` (excluded) again, with their edges; an edge out of them
        goes where it went."""
        copy = {node: self._raw() for node in range(first, last)}
        for node in range(first, last):
            for target in self._successors[node]:
                self._edge(copy[node], copy.get(target, target))
        for site in self._sites:
            site.copies.extend(
                (copy[before], copy[after])
                for before, after in list(site.copies)
                if first <= before < last
            )
        return copy

    # -- with ------------------------------------------------------------------------------

    def with_block(self) -> int:
        """One manager entered: the rest raises to its exit."""
        manager = self._raw()
        self._handlers.append(manager)
        return manager

    def with_end(self, manager: int) -> None:
        """The manager exits: after a normal end, or after it swallowed an exception; or it
        raises the exception again."""
        self._handlers.pop()
        self._throw(manager)
        self.join([self._current, manager])

    # -- the fields ------------------------------------------------------------------------

    def positions(self) -> list[tuple[int, dict[str, object]]]:
        """Each site's fact index and its five fields. The end of the body is a return."""
        self.jump(_RETURN)
        successors = self._successors
        count = len(successors)
        predecessors: list[list[int]] = [[] for _ in range(count)]
        for node, targets in enumerate(successors):
            for target in targets:
                predecessors[target].append(node)
        # The site whose AFTER node each node is, by ordinal.
        completes = [-1] * count
        for site in self._sites:
            for _, after in site.copies:
                completes[after] = site.ordinal
        dominators = _Tree(_ENTRY, successors, predecessors, completes)
        post = _Tree(_EXIT, predecessors, successors, completes)
        on_every_exit = [False] * count
        if dominators.order[_EXIT] != -1:
            node = dominators.idom[_EXIT]
            while True:
                on_every_exit[node] = True
                if node == _ENTRY:
                    break
                node = dominators.idom[node]
        fails = [post.order[node] == -1 for node in range(count)]
        pending = [node for node in range(count) if fails[node]]
        while pending:
            for predecessor in predecessors[pending.pop()]:
                if not fails[predecessor]:
                    fails[predecessor] = True
                    pending.append(predecessor)
        groups = _loop_groups(successors, dominators.order, self._sites, count)
        found = []
        for site in self._sites:
            copies = [c for c in site.copies if dominators.order[c[0]] != -1]
            fields: dict[str, object] = {"on_every_exit": False, "reaches_return": False}
            if copies:
                fields.update(
                    dominator=dominators.nearest_above([b for b, _ in copies], site.ordinal),
                    on_every_exit=self._on_every_exit(copies, on_every_exit),
                    post_dominator=post.nearest_above(
                        [a for _, a in copies if post.order[a] != -1], site.ordinal
                    ),
                    reaches_return=not any(fails[a] for _, a in copies),
                    loop_group=min((groups[b] for b, _ in copies if groups[b] != -1), default=None),
                )
                if site.deferred:
                    fields.update(post_dominator=None, reaches_return=False)
            found.append((site.index, fields))
        return found

    def _on_every_exit(self, copies: list[tuple[int, int]], dominates_exit: list[bool]) -> bool:
        if len(copies) == 1:
            return dominates_exit[copies[0][1]]
        # Several copies: no normal return is reachable without one of them completing.
        if not dominates_exit[_ENTRY]:
            return False
        completed = {after for _, after in copies}
        seen, stack = {_ENTRY}, [_ENTRY]
        while stack:
            for target in self._successors[stack.pop()]:
                if target == _EXIT:
                    return False
                if target not in seen and target not in completed:
                    seen.add(target)
                    stack.append(target)
        return True


class _Tree:
    """A dominator tree by Cooper, Harvey and Kennedy over `forward` from `root`; read with
    the edges flipped and the exit as the root, the post-dominator tree."""

    def __init__(
        self,
        root: int,
        forward: list[list[int]],
        backward: list[list[int]],
        completes: list[int],
    ) -> None:
        count = len(forward)
        order = [-1] * count
        postorder: list[int] = []
        visited = [False] * count
        visited[root] = True
        stack = [(root, iter(forward[root]))]
        while stack:
            node, targets = stack[-1]
            for target in targets:
                if not visited[target]:
                    visited[target] = True
                    stack.append((target, iter(forward[target])))
                    break
            else:
                stack.pop()
                postorder.append(node)
        reverse = postorder[::-1]
        for position, node in enumerate(reverse):
            order[node] = position
        idom = [-1] * count
        idom[root] = root
        changed = True
        while changed:
            changed = False
            for node in reverse[1:]:
                chosen = -1
                for predecessor in backward[node]:
                    if idom[predecessor] == -1:
                        continue
                    chosen = (
                        predecessor
                        if chosen == -1
                        else _intersect(predecessor, chosen, idom, order)
                    )
                if chosen != -1 and idom[node] != chosen:
                    idom[node] = chosen
                    changed = True
        # The nearest site above each node: a site's AFTER node, so it completed.
        nearest = [-1] * count
        for node in reverse[1:]:
            above = idom[node]
            nearest[node] = completes[above] if completes[above] != -1 else nearest[above]
        self.order, self.idom, self._nearest, self._completes = order, idom, nearest, completes

    def nearest_above(self, nodes: list[int], own: int) -> int | None:
        """The nearest site above every one of `nodes` that is not the site `own` they are
        copies of, or None."""
        if not nodes:
            return None
        common = nodes[0]
        for node in nodes[1:]:
            common = _intersect(node, common, self.idom, self.order)
        if common not in nodes and self._completes[common] not in (-1, own):
            return self._completes[common]
        found = self._nearest[common]
        if found != own:
            return None if found == -1 else found
        # Another copy of `own` is above: walk on past it.
        while self.idom[common] != common:
            common = self.idom[common]
            if self._completes[common] not in (-1, own):
                return self._completes[common]
        return None


def _intersect(one: int, other: int, idom: list[int], order: list[int]) -> int:
    while one != other:
        while order[one] > order[other]:
            one = idom[one]
        while order[other] > order[one]:
            other = idom[other]
    return one


def _loop_groups(
    successors: list[list[int]], reached: list[int], sites: list[_Site], count: int
) -> list[int]:
    """Each node's loop (D00 §5 `loop_group`): the strongly connected components of the
    graph with a call's two nodes as one, by Tarjan's algorithm. A component is a loop where
    it holds more than one node or one with an edge to itself; it is named by the lowest
    ordinal of a site in it; -1 where the node is in none."""
    one = list(range(count))
    for site in sites:
        for before, after in site.copies:
            one[after] = before
    out: list[list[int]] = [[] for _ in range(count)]
    looped = [False] * count
    for node in range(count):
        if reached[node] == -1:
            continue
        for target in successors[node]:
            if node == one[target] or reached[target] == -1:
                continue  # a call's own BEFORE-to-AFTER edge
            source, sink = one[node], one[target]
            out[source].append(sink)
            if source == sink:
                looped[source] = True
    index = [-1] * count
    low = [0] * count
    on_stack = [False] * count
    stack: list[int] = []
    component = [-1] * count
    components = 0
    counter = 0
    for root in range(count):
        if index[root] != -1 or reached[root] == -1 or one[root] != root:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack[root] = True
        work = [(root, iter(out[root]))]
        while work:
            node, targets = work[-1]
            for target in targets:
                if index[target] == -1:
                    index[target] = low[target] = counter
                    counter += 1
                    stack.append(target)
                    on_stack[target] = True
                    work.append((target, iter(out[target])))
                    break
                if on_stack[target]:
                    low[node] = min(low[node], index[target])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == index[node]:
                    while True:
                        member = stack.pop()
                        on_stack[member] = False
                        component[member] = components
                        if member == node:
                            break
                    components += 1
    size = [0] * components
    for node in range(count):
        if component[node] != -1:
            size[component[node]] += 1
    lowest = [-1] * components
    for site in sites:
        for before, _ in site.copies:
            c = component[before]
            if c != -1 and (lowest[c] == -1 or site.ordinal < lowest[c]):
                lowest[c] = site.ordinal
    groups = [-1] * count
    for node in range(count):
        c = component[node]
        if c != -1 and lowest[c] != -1 and (size[c] > 1 or looped[node]):
            groups[node] = lowest[c]
    return groups
