# orders-fastapi

Sextant's own FastAPI test project. Each file holds the shapes of one row of the Python reader's
FastAPI catalog, written as a service would write them. FastAPI itself is the oracle for what it
serves (`tests/e2e/fastapi_oracle.py`).

Left for plan 3, listed here and not written: `app/clients.py` (outbound calls with f-string
URLs) and `app/settings.py` (a pydantic-settings class with `env_file`).
