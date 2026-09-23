"""The producer positions the shipped catalogs declare, pinned to the probes that
measured them (GUIDELINES §5.4; spec 2026-09-22 §7b; D02 §1f, §2h).

## The gap this closes, and how it was found

Two false positives were found and fixed while the value model was built, and both lived
in a SHIPPED CATALOG's declaration of a producing call:

* `java.net.URI`'s constructor declared with no `arity`, so `new URI("ws", host, "/path")`
  published the SCHEME as the address — three catalogs carried that form
  (`scripts/probes/a2t8_http_client_builders.md`, its `java.net.URI` table).
* `payload_ctor_arg: "last"` on `ProducerRecord`, whose two `Iterable<Header>` overloads
  put the record's HEADERS last, so those were published as the payload
  (`scripts/probes/cp34_producer_record_ctors.md`).

**Both fixes were pinned in the ENGINE and not in the knowledge.** The engine tests build
invented catalogs, so reverting either shipped value left the whole suite green — the
review that found this changed `spring-kafka-replying.yml`'s `payload_ctor_arg` from `4`
back to `5`, reintroducing the fabrication verbatim, and nothing failed. No fixture
exercises either path, which is exactly why "no shipped row moved" was true of the fix and
would be true of the regression.

So this file asserts the CATALOG DATA, which is where the defects were. It adds no fixture
call site and derives no row: a multi-argument `ProducerRecord` or `URI` site in a fixture
would move shipped rows, and that movement belongs to whoever owns it.

## The direction, which is the point

It pins the CATALOG against the MEASUREMENT, `test_sweep_round1_framework_rules.py`'s own
rule: the expected values are READ OUT OF the probe's generated table rather than written
here, so re-running a harness after a framework bump and pasting a changed table makes the
catalog fail until it is brought back into line — which is the moment a version-scoped rule
is supposed to be re-decided (§5.4). Nothing in this file states a position of its own.

It is OFFLINE and deterministic (NFR-1): it reads committed files and runs nothing.
"""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).parents[2]
CATALOGS = REPO / "src" / "sextant" / "catalogs"
CP34 = REPO / "scripts" / "probes" / "cp34_producer_record_ctors.md"
A2T8 = REPO / "scripts" / "probes" / "a2t8_http_client_builders.md"

PRODUCER_RECORD = "org.apache.kafka.clients.producer.ProducerRecord"
URI = "java.net.URI"

# The generated table's own header, matched in full for `test_sweep_round1_framework_rules`'s
# reason: a header that has drifted means the columns below are being read positionally
# against something else.
_CP34_HEADER = (
    "| # | declared parameters | erased descriptor | value slot | last slot | "
    "`last` is the value? |"
)
# a2t8's `java.net.URI` section header, and the member column's own spelling.
_A2T8_SECTION = "### `java.net.URI` — the factories `url_via` follows"
_MEMBER = re.compile(r"^`([\w<>$]+)\((.*)\)`$")
_BACKTICKED = re.compile(r"^`(.*)`$")


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _bare(text: str) -> str:
    match = _BACKTICKED.match(text.strip())
    return match.group(1) if match else text.strip()


def cp34_rows() -> list[tuple[str, int, bool]]:
    """`(erased descriptor, value slot, whether `last` is the value)` per constructor,
    read off CP-34's generated table."""
    lines = CP34.read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == _CP34_HEADER), None)
    assert start is not None, (
        f"{CP34.relative_to(REPO)} carries no observation table with the header its harness "
        f"generates:\n  {_CP34_HEADER}\nRe-run scripts/probes/cp34_producer_record_ctors/run.sh "
        "and paste its output in verbatim."
    )
    rows = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        _, _, descriptor, value_slot, _, agrees = _cells(line)
        rows.append((_bare(descriptor), int(value_slot), agrees == "yes"))
    return rows


def uri_members() -> list[tuple[str, int, bool]]:
    """`(member name, parameter count, whether the catalog encodes it)` for every
    `java.net.URI` member a2t8 measured."""
    text = A2T8.read_text(encoding="utf-8")
    start = text.index(_A2T8_SECTION)
    section = text[start:].split("\n\n")[1]
    found = []
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        member, _, verdict = _cells(line)
        match = _MEMBER.match(member)
        assert match is not None, f"a2t8's `java.net.URI` table row is not a member: {member}"
        name, parameters = match.group(1), match.group(2)
        found.append((name, len(parameters.split(", ")), verdict.startswith("**encoded**")))
    return found


def _hop_entries(catalog_id: str, owner: str) -> list[dict[str, object]]:
    """Every `channel_via`/`url_via` entry in one catalog naming `owner`, at any depth —
    the same four keys `ingress.catalogs.yaml_source._HOP_KEYS` hoists, read here off the
    file so this rule sees a declaration wherever a style puts it."""
    found: list[dict[str, object]] = []

    def walk(node: object) -> None:
        if isinstance(node, list):
            for entry in node:
                walk(entry)
        elif isinstance(node, dict):
            for key, value in node.items():
                if key in ("channel_via", "url_via") and isinstance(value, list):
                    found.extend(
                        entry
                        for entry in value
                        if isinstance(entry, dict) and entry.get("owner") == owner
                    )
                else:
                    walk(value)

    walk(yaml.safe_load((CATALOGS / f"{catalog_id}.yml").read_text(encoding="utf-8")) or {})
    return found


def _record_wrappers(catalog_id: str, wrapper_type: str) -> list[dict[str, object]]:
    document = yaml.safe_load((CATALOGS / f"{catalog_id}.yml").read_text(encoding="utf-8")) or {}
    matches = document.get("matches") or {}
    return [
        entry
        for entry in (matches.get("record_wrappers") or [])
        if isinstance(entry, dict) and entry.get("type") == wrapper_type
    ]


def catalogs_declaring(key: str, owner_or_type: str) -> list[str]:
    """Every shipped catalog whose file names `owner_or_type` under `key`. Enumerated off
    the directory, never listed, for `declared_measurements`' reason: a hand-maintained
    roster drifts, and the one thing this rule must not do is stop seeing a catalog."""
    found = []
    for path in sorted(CATALOGS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        if key in text and owner_or_type in text:
            found.append(path.stem)
    return found


def test_every_shipped_producer_record_wrapper_carries_cp34s_measured_positions():
    """The `payload_ctor_arg` regression, pinned in the knowledge.

    For each constructor CP-34 measured where `last` is NOT the value, every catalog
    declaring a `ProducerRecord` wrapper must name that overload by `descriptor` and
    carry the value's measured index. Reverting one to `"last"`'s answer — the review's
    own `4` -> `5` — fails here, in the file where the fabrication would live.
    """
    disagreeing = {
        descriptor: value_slot for descriptor, value_slot, agrees in cp34_rows() if not agrees
    }
    assert disagreeing, (
        "CP-34's table now says `last` is the value on every constructor. If a kafka-clients "
        "release really removed both `Iterable<Header>` overloads, the discriminated rows in "
        "the catalogs are dead and should go with this assertion; re-read the probe first."
    )
    declaring = catalogs_declaring("record_wrappers", PRODUCER_RECORD)
    assert declaring, "no shipped catalog declares a `ProducerRecord` `record_wrappers` entry"
    wrong: list[str] = []
    for catalog_id in declaring:
        declared = {
            str(entry["descriptor"]): entry
            for entry in _record_wrappers(catalog_id, PRODUCER_RECORD)
            if isinstance(entry.get("descriptor"), str)
        }
        for descriptor, value_slot in disagreeing.items():
            entry = declared.get(descriptor)
            if entry is None:
                wrong.append(f"{catalog_id}: no entry names `{descriptor}`")
            elif entry.get("payload_ctor_arg") != value_slot:
                wrong.append(
                    f"{catalog_id}: `{descriptor}` declares "
                    f"`payload_ctor_arg: {entry.get('payload_ctor_arg')!r}`, and CP-34 measured "
                    f"the value at {value_slot}"
                )
            elif entry.get("channel_ctor_arg") != 0:
                wrong.append(
                    f"{catalog_id}: `{descriptor}` declares "
                    f"`channel_ctor_arg: {entry.get('channel_ctor_arg')!r}`, and every "
                    f"`ProducerRecord` constructor CP-34 read takes the topic at 0"
                )
    assert wrong == [], (
        "these `record_wrappers` entries disagree with `scripts/probes/"
        "cp34_producer_record_ctors.md`:\n" + "\n".join(f"  - {line}" for line in wrong) + "\n\n"
        "On the two overloads whose final parameter is `Iterable<Header>`, the last argument "
        'is the record\'s HEADERS. `payload_ctor_arg: "last"` published those as the request '
        "payload — a fabricated payload on ordinary input, not a miss."
    )


def test_every_shipped_uri_constructor_form_carries_the_measured_arity():
    """The `arity` regression, pinned in the knowledge.

    a2t8 measured five `java.net.URI` constructors and marked exactly one encoded — four
    of the other four take a SCHEME at argument 0. A hop entry naming `URI.<init>` without
    the encoded one's arity matches all five, and `new URI("ws", host, "/path")` then
    publishes `ws` as the address. Reverting `arity: 1` on any of the five declaring
    catalogs fails here.
    """
    measured = uri_members()
    constructors = [(count, encoded) for name, count, encoded in measured if name == "<init>"]
    assert len(constructors) > 1, (
        "a2t8 now measures one `java.net.URI` constructor. If the platform really declares "
        "only one, the arity is no longer load-bearing and this rule should go with it."
    )
    [required_arity] = [count for count, encoded in constructors if encoded]
    declaring = catalogs_declaring("java.net.URI", "method: create")
    assert declaring, "no shipped catalog declares a `java.net.URI` hop entry"
    wrong: list[str] = []
    for catalog_id in declaring:
        for entry in _hop_entries(catalog_id, URI):
            if entry.get("method") != "<init>":
                continue
            if entry.get("arity") != required_arity:
                wrong.append(
                    f"{catalog_id}: a `java.net.URI` `<init>` entry declares "
                    f"`arity: {entry.get('arity')!r}` — a2t8 marks only the "
                    f"{required_arity}-argument constructor encoded"
                )
    assert wrong == [], (
        "these `java.net.URI` constructor forms carry no measured arity "
        "(`scripts/probes/a2t8_http_client_builders.md`, its `java.net.URI` table):\n"
        + "\n".join(f"  - {line}" for line in wrong)
        + "\n\nWithout it the form matches the four multi-argument constructors whose "
        "argument 0 is a SCHEME, and the address published is `https` or `ws`."
    )


def test_the_scan_finds_the_declarations_that_ship():
    """Both rules above agree with an empty scan of the catalogs, and a renamed key or a
    moved block would retire them silently rather than loudly. Two pins, one per rule, each
    naming the population it governs."""
    records = catalogs_declaring("record_wrappers", PRODUCER_RECORD)
    uris = catalogs_declaring("java.net.URI", "method: create")
    assert (len(records), len(uris)) == (3, 5), (
        "the shipped population these rules govern has changed — "
        f"`ProducerRecord` wrappers: {records}; `java.net.URI` hop declarations: {uris}. "
        "That is not a failure on its own; check the new file carries the measured values "
        "and update the counts."
    )
