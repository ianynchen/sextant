"""The services an order talks to, called the ways a service calls them: `requests` at module
level and through a `Session`, `httpx` through clients holding a `base_url`, and one
`AsyncClient` handed to a route by a dependency, and addresses a deployment sets."""

import os
from collections.abc import AsyncIterator

import httpx
import requests

from app.schemas import OrderIn
from app.settings import settings

INVENTORY = "https://inventory.example"


def stock(sku: str) -> int:
    return requests.get(f"{INVENTORY}/stock/{sku}", timeout=5).json()["count"]


def reserve(sku: str, order: OrderIn) -> None:
    requests.put(
        f"{INVENTORY}/reservations/{sku}", json=order.model_dump(mode="json", by_alias=True)
    )


class Billing:
    def __init__(self) -> None:
        self.session = requests.Session()

    def charge(self, order: OrderIn) -> None:
        self.session.post(
            "https://billing.example/charges", json=order.model_dump(mode="json", by_alias=True)
        )

    def refund(self, charge_id: str) -> None:
        self.session.post("https://billing.example/refunds", data={"charge": charge_id})


billing = Billing()

shipping = httpx.Client(base_url="https://shipping.example/api")


def ship(order_id: str) -> None:
    shipping.post("/shipments", json={"order": order_id})


def carriers() -> None:
    shipping.request("get", "carriers")


def track(order_id: str, method: str) -> None:
    shipping.request(method, f"/shipments/{order_id}")


def ledger_client(
    base_url: str = "https://ledger.example/v2", timeout: float = 5.0
) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=timeout)


def record(order_id: str) -> None:
    ledger_client().delete(f"/entries/{order_id}")


def rates(currency: str) -> None:
    with httpx.Client(base_url=settings.rates_url) as client:
        client.get(f"/rates/{currency}")


def status(client: httpx.Client) -> int:
    return client.get("/status").status_code


async def notifier() -> AsyncIterator[httpx.AsyncClient]:
    client = httpx.AsyncClient(base_url="https://notify.example/v1/")
    try:
        yield client
    finally:
        await client.aclose()


async def notify(client: httpx.AsyncClient, order_id: str) -> None:
    await client.post("events", json={"order": order_id})


def audit() -> None:
    requests.get(f"http://{os.environ.get('AUDIT_HOST', 'audit.local')}/audit")


def webhook() -> None:
    requests.post(os.environ["WEBHOOK_URL"])
