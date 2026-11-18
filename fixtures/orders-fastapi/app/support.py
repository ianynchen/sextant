from fastapi import APIRouter

# Included only under `if settings.support_routes:` (`app/main.py`), a settings field the
# deployment sets, which Sextant does not evaluate.
router = APIRouter()


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "up"}
