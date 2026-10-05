"""Finding files to send, and refusing ones that must never leave the machine."""
from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

# Never sent to a backend, even if named explicitly.
SENSITIVE = [".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "id_ed25519*",
             "id_ecdsa*", "*.keychain*", ".netrc", ".npmrc", ".pypirc", "credentials*",
             "*secret*", "*.tfstate*", ".git-credentials"]
# Skipped when walking directories outside git.
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build", ".next",
             ".mypy_cache", ".pytest_cache", ".ruff_cache", "target", ".tox", "site-packages"}
MAX_FILE_BYTES = 2_000_000


def is_sensitive(path: Path) -> bool:
    return any(fnmatch.fnmatch(path.name, pat) for pat in SENSITIVE)


def _git_files(directory: Path) -> list[Path] | None:
    """Tracked + untracked-but-not-ignored files, or None outside a git repo."""
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             cwd=directory, capture_output=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return [directory / p for p in out.decode().split("\0") if p]


def _walk(directory: Path) -> list[Path]:
    found = []
    for path in directory.iterdir():
        if path.is_dir():
            if path.name not in SKIP_DIRS and not path.name.startswith("."):
                found += _walk(path)
        elif path.is_file():
            found.append(path)
    return found


def _is_text(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            head = f.read(8192)
        head.decode("utf-8")
        return b"\0" not in head
    except (OSError, UnicodeDecodeError):
        return False


def discover(paths: list[str], globs: list[str] | None = None) -> tuple[list[Path], list[tuple[Path, str]]]:
    """Expand files/directories into readable text files.

    Returns (files, skipped) where skipped holds (path, reason).
    """
    candidates: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            tracked = _git_files(p)
            candidates += tracked if tracked is not None else _walk(p)
        else:
            candidates.append(p)

    files, skipped, seen = [], [], set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if globs and not any(fnmatch.fnmatch(path.name, g) for g in globs):
            continue
        if is_sensitive(path):
            skipped.append((path, "sensitive file, never sent"))
        elif not path.is_file():
            skipped.append((path, "not a file"))
        elif path.stat().st_size > MAX_FILE_BYTES:
            skipped.append((path, f"larger than {MAX_FILE_BYTES // 1_000_000} MB"))
        elif path.stat().st_size == 0:
            skipped.append((path, "empty"))
        elif not _is_text(path):
            skipped.append((path, "binary"))
        else:
            files.append(path)
    return sorted(files), skipped
