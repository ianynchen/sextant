"""Version and integrity pin for the one vendored front-end asset (2K design
§6b).

`architecture.html` is self-contained and offline: mermaid's own JS ships
inside the emitted file rather than being fetched from a CDN at view time, so
the document still opens on a machine with no network. That trades a
hand-written mermaid renderer — not something Sextant is in the business of —
for a vendored copy, downloaded once at dev time from the official npm/jsDelivr
artifact and committed verbatim (`assets/mermaid.min.js`,
`assets/LICENSE-mermaid`).

Pinned like a dependency, upgraded deliberately: `test_render_html.py` hashes
the committed file against `MERMAID_SHA256` and fails loudly the day the asset
is swapped for a different version — or a different library — under the same
file name. Bumping either constant here without also replacing the file, or
replacing the file without bumping these, is exactly the drift this pin
exists to catch.
"""

MERMAID_VERSION = "11.17.2"
MERMAID_SHA256 = "581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8"
