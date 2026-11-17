"""Small helpers so route bodies can return `(payload, status)` pairs."""

from functools import wraps
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response


class Json:
    """A JSON payload waiting for a status code."""

    def __init__(self, payload: Any):
        self.payload = payload


def jsonify(payload: Any) -> Json:
    return Json(payload)


def to_response(result):
    if isinstance(result, tuple):
        body, status = result[0], result[1]
        if isinstance(body, Json):
            return JSONResponse(body.payload, status_code=status)
        if isinstance(body, Response):
            body.status_code = status
            return body
        return JSONResponse(body, status_code=status)
    if isinstance(result, Json):
        return JSONResponse(result.payload)
    return result


class JsonRouter(APIRouter):
    """APIRouter whose endpoints may return Json / (Json, status) tuples."""

    def add_api_route(self, path, endpoint, **kwargs):
        @wraps(endpoint)
        def wrapper(*args, **kw):
            return to_response(endpoint(*args, **kw))

        kwargs.setdefault("response_model", None)
        return super().add_api_route(path, wrapper, **kwargs)


def json_body(payload) -> dict:
    return payload if isinstance(payload, dict) else {}
