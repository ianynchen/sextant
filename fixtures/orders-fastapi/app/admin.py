from app.routing import APIRouter

admin = APIRouter()


@admin.get("/users")
def users() -> list[str]:
    return []


@admin.delete("/orders/{order_id}")
def purge(order_id: int) -> None:
    return None
