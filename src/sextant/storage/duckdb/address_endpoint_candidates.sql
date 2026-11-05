-- `made_by` (D02 §2's `annotation_driven`, Android outbound spec M8): one catalog's
-- candidate rows, each with the server address of the object that made its client.
--
-- Nothing is decided here. Which address each row gets, and how sure it is, is decided in
-- `resolve/shapes/made_by.py`; this file is handed the answer per candidate and applies it.
--
-- **Before the rows go into `endpoints`**, between `derive_endpoints.sql` and
-- `insert_endpoints.sql`, so the earlier-catalog-wins rule compares the address the row
-- really has: an outbound row is per caller and peer there.
--
-- **One candidate becomes one row per address.** A client interface made by two objects with
-- two addresses calls both, so the candidate is copied once per `$rows` entry that names it,
-- each copy with its own peer, path and resolution. Every candidate of the catalog has at
-- least one entry (an address not read is an entry too), and the other catalogs' candidates
-- are kept as they are.
--
-- Parameters:
--   $catalog_id -- the catalog whose candidates are addressed.
--   $rows       -- {handler, served_by, caller, method, was, serving, peer, path,
--                  resolution}: `handler`, `served_by`, `caller`, `method` and `was` (the
--                  candidate's own path) name the candidate; the other four replace its
--                  columns, `serving` its `served_by`. `served_by` is part of the name because
--                  one inherited method may be one candidate per interface that inherits it;
--                  `serving` is the interface a copy is called through, which differs from
--                  the candidate's where a client is made for an interface that inherits
--                  the method (fix round 2).
CREATE OR REPLACE TEMP TABLE endpoint_candidates AS
SELECT c.* FROM endpoint_candidates c WHERE c.catalog_id IS DISTINCT FROM $catalog_id
UNION ALL BY NAME
SELECT c.* REPLACE (
    a.serving AS served_by, a.peer AS peer, a.path AS path, a.resolution AS resolution
)
FROM endpoint_candidates c
JOIN (
    SELECT UNNEST(
        $rows::STRUCT(
            handler VARCHAR, served_by VARCHAR, caller VARCHAR, method VARCHAR, was VARCHAR,
            serving VARCHAR, peer VARCHAR, path VARCHAR, resolution VARCHAR
        )[],
        recursive := true
    )
) a
  ON c.catalog_id = $catalog_id
 AND c.handler IS NOT DISTINCT FROM a.handler
 AND c.served_by IS NOT DISTINCT FROM a.served_by
 AND c.caller IS NOT DISTINCT FROM a.caller
 AND c.method IS NOT DISTINCT FROM a.method
 AND c.path IS NOT DISTINCT FROM a.was;
