# Lets the existing Render start command (`gunicorn app:app`) run the ASGI app.
worker_class = "uvicorn_worker.UvicornWorker"
