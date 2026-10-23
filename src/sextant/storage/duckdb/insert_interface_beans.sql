-- The conditions pass's interface beans (`resolve/bean_conditions.py`, CP-46): each interface
-- the framework implements, once per type it is assignable to — a SET, as `bean_conditions`.
INSERT INTO interface_beans (bean, type)
SELECT DISTINCT r.bean, r.type
FROM (SELECT UNNEST($rows::STRUCT(bean VARCHAR, type VARCHAR)[]) AS r);
