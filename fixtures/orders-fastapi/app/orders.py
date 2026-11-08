from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Cookie, Depends, Header, Query, Response

from app.deps import DbSession, Paging, Principal, audit
from app.routing import APIRouter
from app.schemas import OrderIn, OrderOut
from app.services import OrderService, get_service, orders

router = APIRouter(prefix="/orders", dependencies=[Depends(audit)])

STATS_VERSION = "/v2"


@router.get("/{order_id}", response_model=OrderOut)
def get(
    order_id: UUID,
    db: DbSession,
    who: Principal,
    verbose: bool = False,
    q: str | None = Query(None, alias="search"),
    x_trace_id: Annotated[str | None, Header()] = None,
    session_id: Annotated[str, Cookie()] = "",
):
    return OrderOut.model_construct(order_id=order_id, status="new")


@router.post("")
def create(body: OrderIn, svc: OrderService = Depends(get_service)) -> OrderOut:  # noqa: B008
    orders.create(body.customer_id, note=body.note)
    return OrderOut.model_construct(order_id=uuid4(), status="new")


@router.api_route("/{order_id}/cancel", methods=["post", "PUT"])
def cancel(order_id: UUID) -> dict[str, str]:
    return {"status": "cancelled"}


def export() -> list[str]:
    return []


router.add_api_route("/export", export, methods=["GET"])


@router.get(f"{STATS_VERSION}/stats")
def stats() -> dict[str, int]:
    return {}


@router.get("/raw", response_model=None)
def raw() -> Response:
    return Response(content="raw")


@router.get("/a")
@router.get("/b")
def either() -> dict[str, str]:
    return {}


@router.get("/paged")
def paged(p: Paging = Depends()) -> dict[str, int]:  # noqa: B008
    return {"limit": p.limit, "offset": p.offset}
