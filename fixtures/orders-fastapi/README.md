# orders-fastapi

Sextant's own FastAPI test project. Each file holds the shapes of one row of the Python reader's
FastAPI catalog, written as a service would write them. FastAPI itself is the oracle for what it
serves (`tests/e2e/fastapi_oracle.py`).

`app/support.py` is included only under `if flags.SUPPORT_ROUTES:` (`app/flags.py`, a plain
class whose repository value is True). FastAPI run with that value serves it; Sextant publishes
the route as existing "not evaluated", since it decides no such test (OI-368). Plan 3 moves the
switch to a settings read once settings fields are linked to configuration keys.

Left for plan 3, listed here and not written: `app/clients.py` (outbound calls with f-string
URLs) and `app/settings.py` (a pydantic-settings class with `env_file`).
