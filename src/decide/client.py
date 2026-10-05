"""HTTP client for the System One decision API."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import Backend

RETRY_STATUS = {429, 500, 502, 503, 504}


class DecisionError(RuntimeError):
    pass


@dataclass
class Response:
    answers: dict  # question name -> answer object from the API
    input_tokens: int
    seconds: float
    cached: bool = False


class Client:
    def __init__(self, backend: Backend, retries: int = 4, timeout: float = 300):
        self.backend = backend
        self.retries = retries
        self.timeout = timeout

    def ask(self, state, questions: dict) -> Response:
        if not 1 <= len(questions) <= self.backend.max_questions:
            raise DecisionError(f"need 1-{self.backend.max_questions} questions, got {len(questions)}")
        body = {"model": self.backend.model, "state": state, "questions": questions, **dict(self.backend.extra)}
        headers = {"Content-Type": "application/json"}
        if self.backend.api_key:
            headers["Authorization"] = f"Bearer {self.backend.api_key}"
        request = urllib.request.Request(self.backend.url, json.dumps(body).encode(), headers)

        for attempt in range(self.retries + 1):
            start = time.monotonic()
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as r:
                    data = json.load(r)
                return Response(data["answers"], data.get("usage", {}).get("input_tokens", 0),
                                time.monotonic() - start)
            except urllib.error.HTTPError as e:
                detail = e.read()[:300].decode(errors="replace")
                if e.code not in RETRY_STATUS or attempt == self.retries:
                    raise DecisionError(f"{self.backend.name} HTTP {e.code}: {detail}") from None
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt == self.retries:
                    raise DecisionError(f"{self.backend.name} unreachable: {e}") from None
            time.sleep(min(2 ** attempt, 20))
        raise AssertionError("unreachable")
