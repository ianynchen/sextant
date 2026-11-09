"""How FastAPI reads a pydantic model marked `Query()`, `Header()` or `Cookie()` (plan 2, Task 9,
ruling R25: query models).

Run it inside a throwaway environment that has FastAPI installed, never inside the repository's
`.venv`, once per version compared:

    uv venv /tmp/probe && uv pip install -p /tmp/probe/bin/python fastapi==0.162.0 httpx
    /tmp/probe/bin/python scripts/probes/fastapi_param_models.py

It registers one route per model and prints, as one JSON document headed by the versions the
process itself reports: the parameters FastAPI's OpenAPI lists for each route (name, location,
required), and which request keys FastAPI reads into which field (`accept`). What the results
mean is in `fastapi_param_models.md`. The probe imports FastAPI and runs it on purpose. Sextant
itself never does that (spec 7).
"""

# ruff: noqa: UP045
# The probe writes `Optional[X]` and marker calls on purpose: they are the shapes under test.

from __future__ import annotations

import json
from typing import Annotated, Optional

import fastapi
import pydantic
from fastapi import Cookie, FastAPI, Header, Query
from fastapi.testclient import TestClient
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Plain(BaseModel):
    my_field: int
    opt_field: Optional[int] = None
    dflt: int = Field(3)
    _private: int = 0


class Aliased(BaseModel):
    a_field: int = Field(0, alias="Al")
    s_field: int = Field(0, serialization_alias="Ser")
    v_field: int = Field(0, validation_alias="Val")
    c_field: int = Field(0, validation_alias=AliasChoices("c1", "c2"))


class Gen(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)
    my_field: int = 0
    other_field: int = Field(0, alias="Explicit")


class GenByName(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    my_field: int = 0


class Hdr(BaseModel):
    x_trace_id: str = "-"


class HeaderAliased(BaseModel):
    x_a: str = Field("-", alias="X_Al")
    x_b: str = "-"


class HeaderGenerated(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)
    x_c: str = "-"


app = FastAPI()


@app.get("/h")
def h(h: Annotated[HeaderAliased, Header()]):
    return h.model_dump()


@app.get("/hn")
def hn(h: Annotated[HeaderAliased, Header(convert_underscores=False)]):
    return h.model_dump()


@app.get("/hg")
def hg(h: Annotated[HeaderGenerated, Header()]):
    return h.model_dump()


@app.get("/plain")
def plain(q: Annotated[Plain, Query()]):
    return q.model_dump()


@app.get("/aliased")
def aliased(q: Annotated[Aliased, Query()]):
    return q.model_dump()


@app.get("/gen")
def gen(q: Annotated[Gen, Query()]):
    return q.model_dump()


@app.get("/genbn")
def genbn(q: Annotated[GenByName, Query()]):
    return q.model_dump()


@app.get("/hdr")
def hdr(h: Annotated[Hdr, Header()]):
    return h.model_dump()


@app.get("/ck")
def ck(c: Annotated[Plain, Cookie()]):
    return c.model_dump()


out = {"fastapi": fastapi.__version__, "pydantic": pydantic.VERSION}
spec = TestClient(app).get("/openapi.json").json()
for path, item in spec["paths"].items():
    out[path] = [
        (p["name"], p["in"], p.get("required", False)) for p in item["get"].get("parameters", [])
    ]
c = TestClient(app)


def tryq(path, params=None, headers=None, cookies=None):
    r = c.get(path, params=params, headers=headers, cookies=cookies)
    return r.status_code, r.json()


out["accept"] = {
    "hdr X_Al": tryq("/h", headers={"X_Al": "v"}),
    "hdr X-Al": tryq("/h", headers={"X-Al": "v"}),
    "hdr x-b": tryq("/h", headers={"x-b": "v"}),
    "hdr no-convert x_b": tryq("/hn", headers={"x_b": "v"}),
    "hdr generator xC": tryq("/hg", headers={"xC": "v"}),
    "plain my_field": tryq("/plain", {"my_field": 1}),
    "aliased Al": tryq("/aliased", {"Al": 5}),
    "aliased a_field": tryq("/aliased", {"a_field": 5}),
    "aliased Ser": tryq("/aliased", {"Ser": 5}),
    "aliased s_field": tryq("/aliased", {"s_field": 5}),
    "aliased Val": tryq("/aliased", {"Val": 5}),
    "aliased v_field": tryq("/aliased", {"v_field": 5}),
    "aliased c1": tryq("/aliased", {"c1": 5}),
    "gen myField": tryq("/gen", {"myField": 5}),
    "gen my_field": tryq("/gen", {"my_field": 5}),
    "genbn my_field": tryq("/genbn", {"my_field": 5}),
    "hdr x-trace-id": tryq("/hdr", headers={"x-trace-id": "A"}),
    "hdr x_trace_id": tryq("/hdr", headers={"x_trace_id": "A"}),
}
print(json.dumps(out, indent=1))
