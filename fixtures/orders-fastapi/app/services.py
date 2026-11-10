from uuid import UUID, uuid4


class OrderService:
    def create(self, customer_id: int, note: str | None = None) -> UUID:
        return uuid4()


orders = OrderService()


def get_service() -> OrderService:
    return orders
