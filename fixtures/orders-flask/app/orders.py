from flask import Blueprint, request

bp = Blueprint("orders", __name__, url_prefix="/orders")


@bp.route("/<int:order_id>")
def get_order(order_id: int) -> dict[str, object]:
    verbose = request.args.get("verbose")
    api_key = request.headers["X-Api-Key"]
    session = request.cookies.get("session_id")
    return {"id": order_id, "verbose": verbose, "key": bool(api_key), "session": session}


@bp.post("/")
def create_order() -> dict[str, str]:
    return {"source": request.values.get("source", "web"), "status": "created"}


@bp.route("/<int:order_id>/cancel", methods=["post", "PUT"])
def cancel_order(order_id: int) -> dict[str, str]:
    return {"reason": request.args["reason"], "status": "cancelled"}


def export_orders() -> dict[str, str]:
    return {"trace": request.headers.get("X-Trace-Id", "none"), "format": "csv"}


bp.add_url_rule("/export", view_func=export_orders)
