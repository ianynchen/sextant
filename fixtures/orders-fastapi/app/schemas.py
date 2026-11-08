from datetime import datetime
from decimal import Decimal
from uuid import UUID

from humps import camelize
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
from pydantic.alias_generators import to_camel


class Base(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class OrderIn(Base):
    note: str | None = None
    total: Decimal = Field(alias="grandTotal")
    customer_id: int


class OrderOut(Base):
    order_id: UUID
    created_at: datetime
    status: str = Field(serialization_alias="state")
    _secret: str = PrivateAttr()


class Legacy(BaseModel):
    model_config = ConfigDict(alias_generator=camelize)

    legacy_id: int
    display_name: str
