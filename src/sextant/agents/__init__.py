"""The `agents` outer group (2K design §8): a new sibling of `ingress`,
`storage`, and `egress` in the layering `cli -> ingress | storage | egress |
agents -> application -> domain`. It imports `application`/`domain` inward
like any outer group, and nothing else outward — never `ingress`,
`storage`, or `egress`.

Its one member, `claude_api.py`, is the one place in Sextant permitted to
import the `anthropic` SDK (import-confined, enforced by
`tests/architecture/test_agents_confinement.py`) — DR-2's amendment names it
the one sanctioned model call in the codebase; the deterministic pipeline
never reaches this package.
"""
