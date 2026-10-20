"""The system document (M07, system scope): what one reactor's modules call in each other.

**The document is the result, not the table** (user ruling, 2026-10-17). A green `links` table
with a blank document is a failed delivery, so every row this tier writes has a section here,
and so does every row it refused to write — `M06`'s honesty obligations are sections, not
footnotes:

* unmatched outbound endpoints and uncalled inbound endpoints, **separately**;
* unmatched calls into an ABSENT participant, kept apart from real findings;
* every `narrowed` link with all its candidates.

Markdown only. The module document's HTML emitter serializes an assembled list; this tier has
one section set and no diagram, so it writes markdown directly rather than borrowing that
machinery for a shape it does not have yet.
"""

from collections.abc import Sequence

from sextant.application.stitch import Link, Participant, Refusal, Uncalled, Unmatched
from sextant.domain.closed_sets import Resolution


def render_system_document(
    participants: "Sequence[Participant]",
    links: "Sequence[Link]",
    unmatched: "Sequence[Unmatched]",
    uncalled_endpoints: "Sequence[Uncalled]",
    route_refusals: "Sequence[Refusal]",
    *,
    environment: str,
) -> str:
    """`system.md` — the markdown document for one reactor's participant set."""
    absent = {p.name for p in participants if not p.present}
    lines: list[str] = [
        "# System",
        "",
        (
            f"Linked across **{len(participants)} participants** of one build, "
            f"resolving configuration for the `{environment}` environment."
        ),
        "",
    ]
    lines += _participants(participants)
    lines += _links(links)
    lines += _unmatched(unmatched, absent)
    lines += _uncalled(uncalled_endpoints)
    lines += _refusals(route_refusals)
    return "\n".join(lines).rstrip() + "\n"


def _participants(participants: "Sequence[Participant]") -> list[str]:
    lines = ["## Participants", ""]
    if not participants:
        lines += ["None found.", ""]
        return lines
    lines += ["| Participant | Also called | Read |", "|---|---|---|"]
    for p in participants:
        also = ", ".join(f"`{a}`" for a in p.aliases) if p.aliases else "—"
        # The REASON, not a bare "no": a reader does something different about a module
        # skip-listed on purpose, one never analyzed, and one whose workspace has gone.
        read = "yes" if p.present else f"**no** — {p.absent_reason}"
        lines.append(f"| `{p.name}` | {also} | {read} |")
    lines.append("")
    return lines


def _links(links: "Sequence[Link]") -> list[str]:
    lines = ["## Links", ""]
    if not links:
        lines += [
            (
                "None. Every outbound endpoint is listed below with the reason it "
                "matched nothing — which is a finding about this system, not a failure "
                "of the scan."
            ),
            "",
        ]
        return lines
    lines += ["| From | Calls | Endpoint | Resolution |", "|---|---|---|---|"]
    for link in sorted(links, key=_link_order):
        verb = link.from_method or ""
        source = f"`{link.from_participant}` {verb} `{link.from_path}`".replace("  ", " ")
        # A participant-level link states WHO and no route, and the column says so in
        # words rather than by being empty — an empty cell reads as missing data.
        endpoint = (
            "*the participant, no route*"
            if link.to_path is None
            else f"{link.to_method or ''} `{link.to_path}`".strip()
        )
        resolution = f"{link.resolution} · {link.evidence}"
        if link.resolution == str(Resolution.NARROWED):
            # `M06`'s honesty obligation: every narrowed link with all its candidates. It
            # goes in the row because a reader comparing two links must not have to find a
            # footnote to learn that one of them did not choose.
            candidates = ", ".join(f"`{c}`" for c in link.candidates)
            resolution = f"**{resolution}** — one of {candidates}"
        lines.append(f"| {source} | `{link.to_participant}` | {endpoint} | {resolution} |")
    lines.append("")
    return lines


def _unmatched(unmatched: "Sequence[Unmatched]", absent: "set[str]") -> list[str]:
    """Unmatched outbound endpoints, with the absent-participant ones kept APART.

    `M06`: "an unmatched call into a participant M05 marked absent is attributed to the gap,
    not reported as an architectural finding". Mixing the two would have a reader chasing a
    missing dependency that is really a missing analysis.
    """
    lines = ["## Outbound endpoints that matched nothing", ""]
    if not unmatched:
        lines += ["None — every outbound endpoint in this system reached a participant.", ""]
        return lines
    gap = [u for u in unmatched if u.participant in absent]
    real = [u for u in unmatched if u.participant not in absent]
    if real:
        lines += [
            (
                "Each is one of three things, and this analysis cannot tell them apart: "
                "a service outside this system, a participant nobody added, or a "
                "dependency nobody documented."
            ),
            "",
            "| Participant | Call | Why it matched nothing |",
            "|---|---|---|",
        ]
        for u in sorted(real, key=lambda u: (u.participant, u.path or "", u.method or "")):
            call = f"{u.method or ''} `{u.path}`".strip() if u.path else "*address unread*"
            lines.append(f"| `{u.participant}` | {call} | {u.reason} |")
        lines.append("")
    if gap:
        lines += [
            "### Attributed to a participant that could not be read",
            "",
            (
                "**Not architectural findings.** The call may well reach a participant "
                "of this system; its graph was not available to say so, and the "
                "Participants table above gives the reason per module."
            ),
            "",
            "| Participant | Call |",
            "|---|---|",
        ]
        for u in sorted(gap, key=lambda u: (u.participant, u.path or "")):
            call = f"{u.method or ''} `{u.path}`".strip() if u.path else "*address unread*"
            lines.append(f"| `{u.participant}` | {call} |")
        lines.append("")
    return lines


def _uncalled(uncalled_endpoints: "Sequence[Uncalled]") -> list[str]:
    lines = ["## Inbound endpoints nothing in this system calls", ""]
    if not uncalled_endpoints:
        lines += ["None — every inbound endpoint is reached by a link above.", ""]
        return lines
    lines += [
        (
            "Either dead, or called from outside this system. Both readings are useful "
            "and neither is asserted here."
        ),
        "",
        "| Participant | Endpoint |",
        "|---|---|",
    ]
    for u in uncalled_endpoints:
        lines.append(f"| `{u.participant}` | {u.method or ''} `{u.path}` |".replace("|  ", "| "))
    lines.append("")
    return lines


def _link_order(link: "Link") -> tuple[str, str, str, str]:
    """Deterministic ordering (NFR-1): a document whose rows can swap between runs is a
    document whose diff is noise."""
    return (
        link.from_participant,
        link.from_path or "",
        link.from_method or "",
        link.to_path or "",
    )


def _refusals(route_refusals: "Sequence[Refusal]") -> list[str]:
    """Gateway routes whose prefix could not be composed with the service's paths.

    A SECTION rather than a silence, because the route still produced a participant-level
    link above: the dependency is stated and only the claim about which endpoints it reaches
    is withheld. Without this a reader comparing the two sections would see one gateway route
    with endpoint links and another with none, and have nothing to explain the difference.
    """
    if not route_refusals:
        return []
    lines = [
        "## Gateway routes whose prefix was not composed",
        "",
        (
            "Each of these names its destination above and keeps that link; what is "
            "withheld is which of that service's endpoints the route reaches."
        ),
        "",
        "| Participant | Route | Why |",
        "|---|---|---|",
    ]
    for refusal in sorted(route_refusals, key=lambda r: (r.participant, r.route)):
        lines.append(f"| `{refusal.participant}` | `{refusal.route}` | {refusal.reason} |")
    lines.append("")
    return lines
