from fastapi import APIRouter, Depends, FastAPI

from app import admin, orders
from app.deps import audit, request_id

app = FastAPI(dependencies=[Depends(request_id)])
api = FastAPI()

v1 = APIRouter()
v1.include_router(orders.router)
v1.include_router(admin.admin, prefix="/admin", dependencies=[Depends(audit)])

api.include_router(v1, prefix="/v1")
app.mount("/api", app=api)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
