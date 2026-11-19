from flask import Blueprint

from app.reports import reports_bp

# Its own prefix is overridden where the app registers it (`/admin/`, with a trailing slash).
admin_bp = Blueprint("admin", __name__, url_prefix="/internal")
admin_bp.register_blueprint(reports_bp)


@admin_bp.get("/users")
def list_users() -> dict[str, list[str]]:
    return {"users": ["ada", "grace"]}


@admin_bp.delete("/orders/<int:order_id>")
def purge_order(order_id: int) -> dict[str, int]:
    return {"purged": order_id}
