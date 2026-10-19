-- D01's system scope, second of the two native tables. One row per link M06's filter
-- chain produced — never a row for an unmatched outbound endpoint, which is a finding the
-- document states rather than a link with an empty other end.
--
-- A participant-level link leaves the `to_` endpoint columns NULL: a gateway forwarding to
-- `lb://customers-service` names the destination SERVICE and no route, and NULL is how
-- this table says "the participant, not one of its endpoints".
INSERT INTO links (
    from_participant, from_protocol, from_method, from_path, from_caller,
    to_participant, to_protocol, to_method, to_path,
    resolution, evidence, candidates
)
SELECT r.from_participant, r.from_protocol, r.from_method, r.from_path, r.from_caller,
       r.to_participant, r.to_protocol, r.to_method, r.to_path,
       r.resolution, r.evidence, r.candidates
FROM (SELECT UNNEST(
    $rows::STRUCT(
        from_participant VARCHAR, from_protocol VARCHAR, from_method VARCHAR,
        from_path VARCHAR, from_caller VARCHAR,
        to_participant VARCHAR, to_protocol VARCHAR, to_method VARCHAR, to_path VARCHAR,
        resolution VARCHAR, evidence VARCHAR, candidates VARCHAR
    )[]
) AS r);
