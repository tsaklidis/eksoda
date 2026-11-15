"""Request body limits for the API (requirements §15.5).

Django's ``DATA_UPLOAD_MAX_MEMORY_SIZE`` applies only when ``request.body`` is read.
DRF reads the request stream directly, so its JSON parser enforces the limit itself.
"""

import io

from django.conf import settings
from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser


class LimitedJSONParser(JSONParser):
    """JSON with a body limit (``max_bytes``, by default the global 16 KB)."""

    max_bytes: int | None = None

    def parse(self, stream, media_type=None, parser_context=None):
        limit = self.max_bytes or settings.DATA_UPLOAD_MAX_MEMORY_SIZE
        # Read one byte past the limit: enough to detect an oversized body without
        # reading all of it. DRF never calls a parser for an empty body.
        body = stream.read(limit + 1)
        if len(body) > limit:
            raise ParseError("The request body is too large.")
        return super().parse(io.BytesIO(body), media_type, parser_context)
