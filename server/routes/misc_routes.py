"""Operational routes."""

import logging
import os

from flask import jsonify

from ..app import APP_VERSION, app, get_db


@app.route("/healthz")
def health_check():
    """Liveness and database check for the host's health checks and for
    smoke tests before traffic is switched to a new release."""
    try:
        with get_db() as db:
            db.execute("SELECT 1").fetchone()
    except Exception:
        logging.exception("Health check could not reach the database")
        return jsonify({"status": "error", "database": "unreachable"}), 503
    response = jsonify({
        "status": "ok",
        "version": APP_VERSION,
        "commit": (os.environ.get("RENDER_GIT_COMMIT") or "")[:7],
    })
    response.headers["Cache-Control"] = "no-store"
    return response
