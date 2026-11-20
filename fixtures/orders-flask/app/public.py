from flask import Blueprint

# No prefix of its own: the app registers it twice, as two versions of one catalogue.
public_bp = Blueprint("public", __name__)


@public_bp.get("/catalog")
def catalog() -> dict[str, list[str]]:
    return {"items": ["widget", "gadget"]}
