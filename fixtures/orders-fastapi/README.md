# orders-fastapi

Sextant's own FastAPI test project. Each file holds the shapes of one row of the Python reader's
FastAPI catalog, written as a service would write them. FastAPI itself is the oracle for what it
serves (`tests/e2e/fastapi_oracle.py`).

`app/support.py` is included only under `if settings.support_routes:` (`app/settings.py`, whose
field defaults to True). FastAPI run with that value serves it; Sextant publishes the route as
existing "not evaluated", a property condition on the field's key `ORDERS_SUPPORT_ROUTES` with the
default as evidence, since the deployment sets that key (OI-368).

`app/clients.py` holds the outbound calls (`requests`, `httpx`, addresses read from the
environment). `app/settings.py` is a pydantic-settings class with `env_prefix`, one alias and
`env_file=".env"`; the `.env` beside this file sets two of its keys, and the rates client's
`base_url` is one of its fields.
