"""On-disk answer cache, keyed by model + questions + exact input text.

Re-asking the same question about an unchanged file costs nothing.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

DEFAULT_DIR = Path(os.environ.get("DECIDE_CACHE_DIR", Path.home() / ".cache" / "decide"))


class Cache:
    def __init__(self, directory: Path | None = DEFAULT_DIR):
        self.dir = directory  # None disables caching

    @staticmethod
    def key(model: str, state, questions: dict) -> str:
        blob = json.dumps([model, state, questions], sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()

    def _path(self, key: str) -> Path:
        return self.dir / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict | None:
        if self.dir is None:
            return None
        try:
            return json.loads(self._path(key).read_text())
        except (OSError, ValueError):
            return None

    def put(self, key: str, answers: dict) -> None:
        if self.dir is None:
            return
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(answers))
        tmp.replace(path)
