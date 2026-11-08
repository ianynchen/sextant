from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header


class Session:
    def close(self) -> None:
        pass


class User:
    def __init__(self, scope: str) -> None:
        self.scope = scope


def get_db() -> Iterator[Session]:
    session = Session()
    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


class Authenticator:
    def __init__(self, scope: str) -> None:
        self.scope = scope

    def __call__(self, x_api_key: Annotated[str, Header()]) -> User:
        return User(self.scope)


Principal = Annotated[User, Depends(Authenticator("orders:read"))]


class Paging:
    def __init__(self, limit: int = 20, offset: int = 0) -> None:
        self.limit = limit
        self.offset = offset


def audit(x_audit_user: Annotated[str, Header()]) -> str:
    return x_audit_user


def request_id(x_request_id: Annotated[str, Header()]) -> str:
    return x_request_id
