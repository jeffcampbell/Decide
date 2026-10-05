"""Backend configuration.

A backend is anything that speaks the System One decision API
(POST /v1/systemone with {model, state, questions}). Jev (hosted) and
Ollama's clef models (local) both do, so adding a backend is one entry
in BACKENDS.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

DOTENV_PATHS = [Path.home() / "development" / ".env"]


@dataclass(frozen=True)
class Backend:
    name: str
    url: str
    model: str
    key_env: str | None = None  # env var holding the API key, if any
    max_chunk_chars: int = 48_000  # max characters of file text per request
    max_questions: int = 64
    concurrency: int = 4
    usd_per_mtok: float = 0.0  # input-token price, for cost estimates
    extra: tuple = ()  # extra (key, value) pairs merged into every request body

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.key_env) if self.key_env else None


BACKENDS = {
    # Jev accepts ~32K tokens of state; 80K chars of code stays well under that.
    "jev": Backend("jev", "https://api.typesafe.ai/v1/systemone", "jev-latest",
                   key_env="TYPESAFE_API_KEY", max_chunk_chars=80_000,
                   concurrency=8, usd_per_mtok=0.42),
    # Ollama rejects text-only bodies over 64 KiB and loads at 16K context.
    "ollama": Backend("ollama", "http://localhost:11434/v1/systemone", "clef-flash",
                      max_chunk_chars=48_000, concurrency=1,
                      extra=(("keep_alive", "30m"),)),
}
DEFAULT_BACKEND = "jev"


def load_dotenv(paths=DOTENV_PATHS) -> None:
    """Load KEY=VALUE lines into os.environ without overriding existing vars."""
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.removeprefix("export ").partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def get_backend(name: str | None = None, model: str | None = None) -> Backend:
    load_dotenv()
    name = name or os.environ.get("DECIDE_BACKEND", DEFAULT_BACKEND)
    if name not in BACKENDS:
        raise SystemExit(f"decide: unknown backend {name!r} (choose from {', '.join(BACKENDS)})")
    backend = BACKENDS[name]
    if model:
        backend = replace(backend, model=model)
    if backend.key_env and not backend.api_key:
        raise SystemExit(f"decide: backend {name!r} needs ${backend.key_env} (env or ~/development/.env)")
    return backend
