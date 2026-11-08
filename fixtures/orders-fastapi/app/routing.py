"""The router factory: a class built from a route class, as a real service writes it."""

from fastapi import APIRouter as FastAPIRouter
from fastapi.routing import APIRoute


def router_class(route: type[APIRoute]) -> type[FastAPIRouter]:
    class Router(FastAPIRouter):
        def __init__(self, *args, **kwargs) -> None:
            kwargs.setdefault("route_class", route)
            super().__init__(*args, **kwargs)

    return Router


APIRouter = router_class(APIRoute)
