"""Ask questions about documents of any size.

A document is split into chunks the backend accepts, each chunk is asked
every question in one request, and the per-chunk answers are merged with
questions.combine. Requests run in parallel and are cached.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .cache import Cache
from .client import Client, DecisionError, Response
from .config import Backend
from .questions import combine


@dataclass
class Document:
    label: str  # shown to the model as a header, and in output
    text: str


@dataclass
class Result:
    label: str
    answers: dict = field(default_factory=dict)  # question name -> merged answer
    chunks: int = 0
    input_tokens: int = 0  # billed tokens (0 for cache hits)
    cached_chunks: int = 0
    error: str | None = None


def chunk(text: str, limit: int) -> list[str]:
    """Split on line boundaries into pieces of at most `limit` characters.

    A single line longer than the limit is hard-split.
    """
    pieces, current = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            pieces.append(current)
            current = ""
        current += line
    if current or not pieces:
        pieces.append(current)
    return pieces


class Engine:
    def __init__(self, backend: Backend, cache: Cache | None = None, client: Client | None = None):
        self.backend = backend
        self.cache = cache or Cache(None)
        self.client = client or Client(backend)

    def plan(self, documents: list[Document]) -> list[tuple[int, str]]:
        """(document index, request text) for every chunk of every document."""
        jobs = []
        # leave room for the header line
        limit = self.backend.max_chunk_chars - 200
        for i, doc in enumerate(documents):
            parts = chunk(doc.text, limit)
            for n, part in enumerate(parts, 1):
                header = f"# {doc.label}" + (f" (part {n} of {len(parts)})" if len(parts) > 1 else "")
                jobs.append((i, f"{header}\n{part}"))
        return jobs

    def _ask(self, state: str, questions: dict) -> Response:
        key = Cache.key(self.backend.model, state, questions)
        if (hit := self.cache.get(key)) is not None:
            return Response(hit, 0, 0.0, cached=True)
        response = self.client.ask(state, questions)
        self.cache.put(key, response.answers)
        return response

    def run(self, documents: list[Document], questions: dict, on_done=None) -> list[Result]:
        jobs = self.plan(documents)
        results = [Result(doc.label) for doc in documents]
        per_doc: list[list[dict]] = [[] for _ in documents]

        def work(job):
            index, state = job
            try:
                return index, self._ask(state, questions), None
            except DecisionError as e:
                return index, None, str(e)

        with ThreadPoolExecutor(self.backend.concurrency) as pool:
            for index, response, error in pool.map(work, jobs):
                result = results[index]
                result.chunks += 1
                if error:
                    result.error = error
                    continue
                result.input_tokens += response.input_tokens
                result.cached_chunks += response.cached
                per_doc[index].append(response.answers)
                if on_done:
                    on_done(result)

        for result, chunk_answers in zip(results, per_doc):
            if result.error or not chunk_answers:
                continue
            result.answers = {name: combine([a[name] for a in chunk_answers]) for name in questions}
        return results
