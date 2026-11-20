from flask import Blueprint, request

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.route("/daily", methods=["GET"])
def daily() -> dict[str, str]:
    return {"day": request.args.get("day", "today")}
