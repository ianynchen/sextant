from fastapi import APIRouter

# Included only under `if flags.SUPPORT_ROUTES:` (`app/main.py`), a repository constant
# (`app/flags.py`) that Sextant does not evaluate.
router = APIRouter()


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "up"}
