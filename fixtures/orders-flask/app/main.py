from flask import Flask, request

from app.admin import admin_bp
from app.legacy import legacy_bp
from app.orders import bp as orders_bp
from app.public import public_bp

app = Flask(__name__)


@app.route("/health")
def health() -> dict[str, str]:
    return {"status": "up", "request": request.headers.get("X-Request-Id", "none")}


@app.route("/webhooks/orders", methods=["POST", "PUT"])
def order_webhook() -> dict[str, str]:
    return {"source": request.headers.get("X-Webhook-Source", "unknown"), "status": "accepted"}


@app.get("/files/<path:rest>")
def download(rest: str) -> dict[str, str]:
    return {"path": rest, "inline": request.args.get("inline", "0")}


def ping() -> dict[str, str]:
    return {"ping": "pong"}


app.add_url_rule("/ping", view_func=ping)

app.register_blueprint(orders_bp)
app.register_blueprint(admin_bp, url_prefix="/admin/")
app.register_blueprint(public_bp, url_prefix="/v1")
app.register_blueprint(public_bp, url_prefix="/v2", name="public_v2")
app.register_blueprint(legacy_bp, url_prefix="")
