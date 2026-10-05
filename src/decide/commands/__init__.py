"""Subcommands are discovered automatically.

To add one, create a module in this package that defines:

    HELP = "one-line description"
    def configure(parser: argparse.ArgumentParser) -> None   # add arguments
    def run(args: argparse.Namespace, ctx: decide.cli.Context) -> int  # exit code

The module's name becomes the subcommand name (underscores -> dashes).
"""
from __future__ import annotations

import importlib
import pkgutil


def discover():
    """Yield (name, module) for every subcommand module in this package."""
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        yield info.name.replace("_", "-"), module
