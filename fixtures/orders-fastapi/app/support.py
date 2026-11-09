from fastapi import APIRouter

# Served only where the deployment turns the support routes on (`app/flags.py`, `app/main.py`).
router = APIRouter()


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "up"}
