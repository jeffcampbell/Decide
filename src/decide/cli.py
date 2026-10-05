"""Entry point: `decide <subcommand> ...`."""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from functools import cached_property

from . import commands
from .cache import Cache
from .config import BACKENDS, Backend, get_backend
from .engine import Engine


@dataclass
class Context:
    """Shared services handed to every subcommand."""
    backend_name: str | None
    model: str | None
    use_cache: bool

    @cached_property
    def backend(self) -> Backend:
        return get_backend(self.backend_name, self.model)

    @cached_property
    def engine(self) -> Engine:
        return Engine(self.backend, Cache() if self.use_cache else Cache(None))

    @staticmethod
    def log(message: str) -> None:
        print(message, file=sys.stderr, flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="decide", description="Typed decisions about files and text, "
                                     "via a System One decision model (Jev by default).")
    parser.add_argument("--backend", choices=sorted(BACKENDS), help="default: $DECIDE_BACKEND or jev")
    parser.add_argument("--model", help="override the backend's model name")
    parser.add_argument("--no-cache", action="store_true", help="ignore and don't write ~/.cache/decide")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")
    for name, module in commands.discover():
        p = sub.add_parser(name, help=module.HELP, description=module.__doc__,
                           formatter_class=argparse.RawDescriptionHelpFormatter)
        module.configure(p)
        p.set_defaults(_run=module.run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ctx = Context(args.backend, args.model, not args.no_cache)
    try:
        return args._run(args, ctx)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
