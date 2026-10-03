"""Run the standalone SoloBiz admin portal with Gunicorn or locally."""

import os

from .admin_app import admin_app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    admin_app.run(host="0.0.0.0", port=port, debug=False)
