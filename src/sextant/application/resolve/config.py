"""M04 pass 2 (D01 §"resolved_config", D02 §2i): a generic interpreter over
one catalog-declared `config_model` per framework family. Nothing here names
Spring — the source-pattern grammar, the profile mechanisms and the
placeholder delimiters all arrive as catalog data (D02 §2i), the same
generic-engine-over-catalog-data discipline every other style in
`resolve/engines/` keeps.

**Layering, generally.** Every config_model source is precedence-ordered,
lowest first (D02 §2i). A file matching a source pattern names a profile —
the empty match naming the base file, a `-profile` suffix naming a variant —
and, independently, a multi-document YAML file's own documents may each
carry a `from_document_key` activation (`spring.config.activate.on-profile`)
that scopes just that document to one profile. Both mechanisms answer the
same question — "which profile does this slice of config apply to?" — so
they are normalized here into one `effective_profile` per (document,
doc_index): `None` for a base slice that applies to every profile, or a
profile name for a slice locked to just that one. Resolving one profile
means picking every slice whose `effective_profile` is `None` or that
profile, ordering them, and merging their keys forward — later overwrites
earlier.

**Ordering, precisely (fix round 1, controller ruling I-1).** Source
precedence comes first. WITHIN one source, Spring's own real resource order
is three tiers, not two: an unlocked base document, THEN a document of that
SAME base file activated by `from_document_key`, THEN a separate variant
FILE named by the filename marker — a profile-variant FILE always outranks
an inline profile-activated document of the base file it varies, at the
same source, regardless of either one's own `doc_index`. Declaration order
(`doc_index`) only breaks a tie within one tier.

**Placeholders.** A winning raw value is substituted recursively against
that SAME layered map for its own profile, `:default` (D02 §2i's
`default_separator`) taken literally when the referenced key cannot be
resolved, and a key already on the substitution stack reported as
`placeholder_cycle` rather than looped forever. A key entirely absent from a
profile's own layering — never a placeholder failure, just genuinely
undeclared for that profile — resolves `missing_key` too: D01's own
"unresolved for prod, resolved for dev" example is exactly this case, not a
degraded placeholder.

**`key_matching` is scoped to LOOKUPS, never the merge (fix round 1,
controller ruling I-2).** The layering merge above always keys on a
`config_entry`'s own exact `key_path` — two different spellings in config
files are two different keys at merge time, full stop, because relaxed
binding is Spring's own BINDING-time concept, not a file-reading one.
`key_matching: relaxed` only widens how a `${...}` REFERENCE is looked up
against that already-merged, exact-keyed map (and, later, how a catalog's
own key template is compared against one — D02 §2i, Task 8's field ladder).
A model declaring `billing.url` and `billing.URL` as separate keys keeps
BOTH as separate rows, unconditionally.

**What this pass does not do.** `environment` and `remote_source` both need
a model to declare something pass 2 has nothing to interpret otherwise: an
env-var import, or a `spring.config.import`-shaped prefix list. Spring's own
2F model declares the latter (`remote_prefixes`) and none of the former, so
`environment` is unreachable this phase — one comment marks it rather than
one un-exercised branch. `multi_placeholder` is never emitted here at all;
it is reserved for the peer-resolution join (D01), which substitutes into an
ENDPOINT expression, not a config value.
"""

from typing import Any

from sextant.application.ports.catalogs import Catalog, CatalogError
from sextant.application.ports.workspace import Workspace

# The relaxed-binding rule this pass has always used, now in `domain` because
# 2K's redactor needs the same one and cannot import this module — see
# `domain/config_keys.py`. Moved, not copied.
from sextant.domain.config_keys import normalize_key

# D01's closed five-value unresolved-reason set. `multi_placeholder` is
# listed for completeness only — this pass, by design, never emits it.
UNRESOLVED_REASONS = (
    "missing_key",
    "environment",
    "remote_source",
    "placeholder_cycle",
    "multi_placeholder",
)

_DEFAULT_PLACEHOLDERS = {"open": "${", "close": "}", "default_separator": ":"}


def resolve_config(workspace: Workspace, catalogs: list[Catalog]) -> None:
    """M04 pass 2 (2F design §2): one row per key per environment, for every
    catalog-declared `config_model` — collected from every catalog carrying
    one, since D02 §2i's model is "a new top-level, optional catalog block,
    one per framework family" (the family's base catalog carries it; most
    catalogs carry none, `Catalog.config_model` defaulting to `{}`).

    Runs unconditionally: emptying `resolved_config` happens once, here,
    regardless of whether any catalog declares a model or any config file
    was read, so a config-less run leaves an empty table rather than a
    stale previous run's rows — the same `endpoints`/`shapes` degrade-
    visibly discipline `reset_endpoints.sql`/`reset_shapes.sql` already
    keep."""
    workspace.derive("resolved_config_reset")
    declared = [catalog for catalog in catalogs if catalog.config_model]
    if not declared:
        return
    # Every declared model is checked BEFORE anything is resolved — the same
    # "broken file, not a half-empty table" discipline `derive_endpoints`
    # keeps for an unrecognised style (`endpoints.py::_engine_for`).
    for catalog in declared:
        _validate_model(catalog)
    entries = workspace.query("config_entries")
    documents = {str(row["document_id"]): row for row in workspace.query("documents")}
    for catalog in declared:
        rows = _resolve_model(catalog.config_model, entries, documents)
        if rows:
            workspace.derive("resolved_config_insert", rows=rows)


def _validate_model(catalog: Catalog) -> None:
    """Refuses a `config_model` naming a profile mechanism this pass does
    not implement (M-a, fix round 1) — `from_key_prefix` is reserved for a
    future Quarkus-style catalog (D02 §2i names it, unimplemented, "now").
    A catalog declaring it must be refused loudly, the same
    `CatalogError`-names-the-file discipline `yaml_source.py`'s own loader
    checks keep, rather than silently doing nothing with it."""
    profiles_cfg = catalog.config_model.get("profiles", {})
    if "from_key_prefix" in profiles_cfg:
        raise CatalogError(
            f"loading catalog {catalog.source}: config_model.profiles.from_key_prefix is "
            f"reserved for a future model (D02 §2i) — not yet implemented, and never "
            f"silently ignored"
        )


def _resolve_model(
    model: dict[str, Any],
    entries: list[dict[str, object]],
    documents: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    sources = list(model.get("sources", []))
    profiles_cfg = model.get("profiles", {})
    from_document_key = profiles_cfg.get("from_document_key")
    # M-a (fix round 1): filename splitting is one of D02 §2i's THREE
    # declared mechanisms — a model that never declares `from_filename`
    # never gets it, even where a source pattern happens to spell
    # `{-profile}`/`{profile}`. `_match_source` falls back to a literal,
    # whole-string match when this is False.
    allow_filename_profile = bool(profiles_cfg.get("from_filename"))
    default_profile = str(profiles_cfg.get("default_profile", "default"))
    key_matching = model.get("key_matching", "exact")
    placeholders = model.get("placeholders", _DEFAULT_PLACEHOLDERS)
    remote_prefixes = tuple(model.get("remote_prefixes", []))

    by_doc: dict[tuple[str, int], list[dict[str, object]]] = {}
    for entry in entries:
        doc_index = int(str(entry["doc_index"]))
        by_doc.setdefault((str(entry["document_id"]), doc_index), []).append(entry)

    # (source_index, document_id, doc_index, effective_profile, variant_tier)
    # for every (source pattern, document) pair that matches at all —
    # `effective_profile` is `None` for a slice that applies to every profile
    # (a base filename, a document carrying no `from_document_key`
    # activation), or the one profile name it is locked to (D02 §2i's two
    # mechanisms, normalized to one question). `variant_tier` keeps the TWO
    # ways a slice can be locked apart for `_layer`'s own sort (fix round 1,
    # I-1): 0 = unlocked base, 1 = locked via `from_document_key` (still the
    # base FILE), 2 = locked via the filename marker (a variant FILE).
    matches: list[tuple[int, str, int, str | None, int]] = []
    for source_index, source in enumerate(sources):
        pattern = str(source["pattern"])
        for document_id, document in documents.items():
            relative_path = str(document["relative_path"])
            filename_profile = _match_source(pattern, relative_path, allow_filename_profile)
            if filename_profile is None:
                continue
            doc_indices = sorted({index for (doc, index) in by_doc if doc == document_id})
            # A matched file with zero config_entry facts (an empty document)
            # still counts as present, contributing nothing to any profile.
            for doc_index in doc_indices or [0]:
                if filename_profile != "":
                    effective_profile: str | None = filename_profile
                    variant_tier = 2
                else:
                    effective_profile = _document_key_profile(
                        by_doc.get((document_id, doc_index), []), from_document_key
                    )
                    variant_tier = 0 if effective_profile is None else 1
                matches.append(
                    (source_index, document_id, doc_index, effective_profile, variant_tier)
                )

    if not matches:
        return []

    # `default_profile` "always present" (2F design §2) even when nothing
    # ever names it explicitly — resolving it then means "the base slices
    # alone", which the merge below already produces for free.
    profiles = {default_profile}
    for _, _, _, effective_profile, _ in matches:
        if effective_profile is not None:
            profiles.add(effective_profile)

    # The full key universe this model's sources ever declare, across every
    # profile — what lets a key present in `default` but absent from `prod`
    # still resolve a `missing_key` row FOR `prod`, rather than silently
    # having no row there at all (D01's "unresolved for prod, resolved for
    # dev" example). The activation key itself (`from_document_key`) is
    # excluded (M-c, fix round 1): it is a DIRECTIVE that says which profile
    # a document belongs to, never configuration a module reads, so it never
    # earns its own emitted row — it stays usable for `${...}` references
    # regardless, since it is left in `merged` below, only kept out of the
    # set that decides which rows get written.
    all_keys: set[str] = set()
    for _, document_id, doc_index, _, _ in matches:
        for entry in by_doc.get((document_id, doc_index), []):
            key_path = str(entry["key_path"])
            if key_path != from_document_key:
                all_keys.add(key_path)

    rows: list[dict[str, object]] = []
    for profile in sorted(profiles):
        merged = _layer(model, matches, by_doc, documents, profile)
        normalized_index = _normalized_index(merged, key_matching)
        for key in sorted(all_keys):
            rows.append(
                _resolve_row(
                    key,
                    profile,
                    merged,
                    normalized_index,
                    placeholders,
                    key_matching,
                    remote_prefixes,
                )
            )
    return rows


def _document_key_profile(
    doc_entries: list[dict[str, object]], from_document_key: str | None
) -> str | None:
    """The profile a document's own `from_document_key` activation names
    (`spring.config.activate.on-profile`), or `None` where it carries none —
    a base slice, applying to every profile. First matching entry wins;
    a real config file declares the activation key at most once per
    document (D02 §2i names no multi-value form)."""
    if from_document_key is None:
        return None
    for entry in doc_entries:
        if entry["key_path"] == from_document_key:
            return str(entry["value"])
    return None


def _layer(
    model: dict[str, Any],
    matches: list[tuple[int, str, int, str | None, int]],
    by_doc: dict[tuple[str, int], list[dict[str, object]]],
    documents: dict[str, dict[str, object]],
    profile: str,
) -> dict[str, tuple[str, str]]:
    """One profile's layered key -> (value, source file) map: every slice
    applying to `profile` (its own `effective_profile` `None` or exactly
    `profile`), ordered lowest-precedence first and merged forward so a
    later slice's key overwrites an earlier one's (D02 §2i: "a later source
    in the list, and a profile variant of any source, both win over what
    came before").

    Sort key: source precedence first (`source_index`); WITHIN one source,
    three precedence tiers, lowest first (fix round 1, I-1 — the controller
    ruling on Spring's own real resource order): 0 = an unlocked base
    document, 1 = a document of the BASE FILE activated by
    `from_document_key`, 2 = a whole variant FILE named by the filename
    marker — a profile-activated document never outranks a same-profile
    variant FILE, even when that document's own `doc_index` is numerically
    higher than the variant file's (which is always `0`, being its own,
    separate, single/multi-document file). `doc_index` only breaks a tie
    WITHIN one tier, so a later document in one multi-doc file still
    overrides an earlier one at the same tier. `document_id` breaks any
    remaining tie for total determinism (NFR-1)."""
    applicable = [
        (source_index, document_id, doc_index, variant_tier)
        for (source_index, document_id, doc_index, effective_profile, variant_tier) in matches
        if effective_profile is None or effective_profile == profile
    ]
    applicable.sort(key=lambda row: (row[0], row[3], row[2], row[1]))

    merged: dict[str, tuple[str, str]] = {}
    for _, document_id, doc_index, _ in applicable:
        relative_path = str(documents[document_id]["relative_path"])
        doc_entries = sorted(
            by_doc.get((document_id, doc_index), []), key=lambda entry: int(str(entry["seq"]))
        )
        for entry in doc_entries:
            merged[str(entry["key_path"])] = (str(entry["value"]), relative_path)
    return merged


def _normalized_index(merged: dict[str, tuple[str, str]], key_matching: str) -> dict[str, str]:
    """Maps a normalized key spelling back to the merged map's own key, for
    `${...}` reference lookups. `key_matching: exact` (D02 §2i) is the
    identity normalization — a catalog declaring it never gets the relaxed
    behaviour by accident. First-inserted wins a collision, which is
    `merged`'s own deterministic (layering) order, never dict-iteration
    happenstance."""
    index: dict[str, str] = {}
    for key in merged:
        normalized = normalize_key(key) if key_matching == "relaxed" else key
        index.setdefault(normalized, key)
    return index


def _resolve_row(
    key: str,
    profile: str,
    merged: dict[str, tuple[str, str]],
    normalized_index: dict[str, str],
    placeholders: dict[str, str],
    key_matching: str,
    remote_prefixes: tuple[str, ...],
) -> dict[str, object]:
    if key not in merged:
        # Genuinely undeclared for this profile — no file won precedence,
        # so there is no source to name (D01: an unresolved row carries
        # "the same key and environment"; `value` is NULL exactly when a
        # reason is set, `source` right along with it here since none ever
        # existed).
        return {
            "key": key,
            "value": None,
            "source": None,
            "environment": profile,
            "unresolved_reason": "missing_key",
        }
    raw_value, source_file = merged[key]
    if remote_prefixes and raw_value.startswith(remote_prefixes):
        # A `spring.config.import`-shaped URL (D02 §2i's `remote_prefixes`)
        # is checked on the WINNING raw value, before any placeholder
        # substitution — the config-server case is a literal import
        # string, never itself a placeholder reference.
        return {
            "key": key,
            "value": None,
            "source": source_file,
            "environment": profile,
            "unresolved_reason": "remote_source",
        }
    resolved, reason = _substitute(
        raw_value, merged, normalized_index, placeholders, key_matching, [key]
    )
    if resolved is None:
        return {
            "key": key,
            "value": None,
            "source": source_file,
            "environment": profile,
            "unresolved_reason": reason,
        }
    return {
        "key": key,
        "value": resolved,
        "source": source_file,
        "environment": profile,
        "unresolved_reason": None,
    }


def _substitute(
    raw: str,
    merged: dict[str, tuple[str, str]],
    normalized_index: dict[str, str],
    placeholders: dict[str, str],
    key_matching: str,
    stack: list[str],
) -> tuple[str | None, str | None]:
    """Recursive `${key:default}` substitution (D02 §2i's `placeholders`
    delimiters and `default_separator`) over a value already picked by
    `_layer` for one profile. `stack` carries the chain of merged-map keys
    currently being resolved, INCLUDING the top-level key this call is
    ultimately answering for — a self-reference is caught the same way a
    longer cycle is, on the very first lookup.

    Returns `(resolved_string, None)` on success or `(None, reason)` on
    failure — a single embedded failure fails the WHOLE value; this pass
    never emits a partially-substituted string, the same "unresolved is an
    answer" discipline every other engine keeps for a declared capture that
    could not be read."""
    open_ = placeholders.get("open", "${")
    close_ = placeholders.get("close", "}")
    separator = placeholders.get("default_separator", ":")
    parts: list[str] = []
    index = 0
    while True:
        start = raw.find(open_, index)
        if start == -1:
            parts.append(raw[index:])
            break
        parts.append(raw[index:start])
        content_start = start + len(open_)
        end = raw.find(close_, content_start)
        if end == -1:
            # No closing delimiter: not a placeholder after all, the rest
            # of the string is literal.
            parts.append(raw[start:])
            break
        inner = raw[content_start:end]
        index = end + len(close_)
        if separator and separator in inner:
            ref_key, default = inner.split(separator, 1)
        else:
            ref_key, default = inner, None
        resolved, reason = _resolve_reference(
            ref_key, merged, normalized_index, placeholders, key_matching, stack
        )
        if resolved is None:
            if default is not None:
                # A literal default (D02 §2i): taken as written, never
                # itself re-substituted — `${missing:fallback}` resolves to
                # exactly `fallback`.
                parts.append(default)
            else:
                return None, reason
        else:
            parts.append(resolved)
    return "".join(parts), None


def _resolve_reference(
    ref_key: str,
    merged: dict[str, tuple[str, str]],
    normalized_index: dict[str, str],
    placeholders: dict[str, str],
    key_matching: str,
    stack: list[str],
) -> tuple[str | None, str | None]:
    """One `${ref_key}` lookup: relaxed or exact per the model's own
    `key_matching` — `ref_key` itself is normalized here the same way
    `_normalized_index` normalized every merged key, so a relaxed model
    matches `${MY_KEY}` against a declared `my-key` from either direction.
    Looked up against the SAME layered map the top-level key came from — a
    placeholder always resolves within its own profile's own layering,
    never across profiles."""
    lookup = normalize_key(ref_key) if key_matching == "relaxed" else ref_key
    target = normalized_index.get(lookup)
    if target is None:
        # RULING (2F design §2): any unresolvable placeholder whose key is
        # simply absent resolves `missing_key` — `environment` is reserved
        # for a key the model's OWN sources declare as an environment
        # import, which Spring's 2F model declares none of. A `${}` default
        # chain ending in what looks like an env-var name (`${SOME_VAR}`)
        # is still `missing_key` here, not a finer, unimplemented split.
        return None, "missing_key"
    if target in stack:
        return None, "placeholder_cycle"
    raw_value, _source = merged[target]
    return _substitute(
        raw_value, merged, normalized_index, placeholders, key_matching, stack + [target]
    )


def _match_source(pattern: str, filename: str, allow_placeholder: bool) -> str | None:
    """Matches one `config_model.sources` pattern against a file's relative
    path (D02 §2i: "a `{profile}` (or `{-profile}`) placeholder may sit
    ANYWHERE in a source pattern... with the empty match naming the base
    file"). Returns the profile the file names — `""` for the base file, a
    profile name for a variant — or `None` when the file does not match
    this source at all.

    `allow_placeholder` is `profiles.from_filename` having been declared at
    all (M-a, fix round 1): filename splitting is one of D02 §2i's three
    named profile mechanisms, not an ambient behaviour of the pattern
    grammar, so a pattern spelling `{-profile}`/`{profile}` without a
    declared `from_filename` never splits on it — it falls straight to the
    literal, whole-string branch below, where such a pattern (containing a
    brace no real filename ever will) simply matches nothing.

    `{-profile}` is Spring's own dashed convention: nothing at all for the
    base file, `-{profile}` for a variant (`application-prod.yml`).
    `{profile}` (reserved for a layout like node-config's whole-filename
    `{profile}.json`) takes the bare match either way, base or not. A
    pattern with neither placeholder — or `allow_placeholder` False —
    matches only the literal filename, its own profile always the base
    (`""`) — a source with no variant mechanism of its own."""
    if allow_placeholder:
        for placeholder, dashed in (("{-profile}", True), ("{profile}", False)):
            if placeholder not in pattern:
                continue
            prefix, suffix = pattern.split(placeholder, 1)
            if not filename.startswith(prefix) or not filename.endswith(suffix):
                return None
            end = len(filename) - len(suffix) if suffix else len(filename)
            middle = filename[len(prefix) : end]
            if not dashed:
                return middle
            if middle == "":
                return ""
            if middle.startswith("-"):
                return middle[1:]
            return None
    return "" if pattern == filename else None
