"""Cross-cutting Flask middleware: build-id injection and gzip compression."""
from __future__ import annotations

import gzip

from flask import Flask, Response, request

from . import config


def inject_build_id() -> dict[str, str]:
    """Expose BUILD_ID to templates for cache-busting static asset URLs."""
    return {"build_id": config.BUILD_ID}


def gzip_response(response: Response) -> Response:
    """Gzip eligible text responses (stdlib only) to cut bytes on the wire."""
    accept = request.headers.get("Accept-Encoding") or ""
    if (
        response.direct_passthrough
        or not (200 <= response.status_code < 300)
        or response.headers.get("Content-Encoding")
        or "gzip" not in accept
        or (response.content_length is not None and response.content_length < 500)
    ):
        return response
    data = gzip.compress(response.get_data(), compresslevel=6)
    response.set_data(data)
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = str(len(data))
    response.headers["Vary"] = "Accept-Encoding"
    return response


def register(app: Flask) -> None:
    """Attach the middleware to a Flask app."""
    app.context_processor(inject_build_id)
    app.after_request(gzip_response)
