from fastapi import APIRouter, Depends, FastAPI

from app import admin, orders, support
from app.deps import audit, request_id
from app.flags import flags

app = FastAPI(dependencies=[Depends(request_id)])
api = FastAPI()

v1 = APIRouter()
v1.include_router(orders.router)
v1.include_router(admin.admin, prefix="/admin", dependencies=[Depends(audit)])

api.include_router(v1, prefix="/v1")
app.mount("/api", app=api)

if flags.SUPPORT_ROUTES:
    app.include_router(support.router, prefix="/support")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
