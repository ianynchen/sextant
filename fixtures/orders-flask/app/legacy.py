from flask import Blueprint

# Registered with `url_prefix=""`, which replaces this prefix: the routes are served at the root.
legacy_bp = Blueprint("legacy", __name__, url_prefix="/legacy")


@legacy_bp.route("/status", methods=["GET"])
def status() -> dict[str, str]:
    return {"status": "ok"}
