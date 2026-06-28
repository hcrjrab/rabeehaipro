"""Command-line entrypoint.

Exposes a tiny CLI for local development:

    rabeeh serve                 -> run the API with uvicorn
    rabeeh run "do something"    -> run a one-shot goal through the orchestrator
    rabeeh info                  -> print masked settings

Kept dependency-light: ``serve`` shells out to uvicorn programmatically
rather than depending on Click/Typer, so the base install stays minimal.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Sequence

from .config.logging import configure_logging
from .config.settings import get_settings

_log = logging.getLogger("rabeeh.cli")


def _cmd_serve(args: argparse.Namespace) -> int:
    """Start the FastAPI app via uvicorn."""
    import uvicorn  # imported lazily so the CLI works without uvicorn for `info`

    settings = get_settings()
    configure_logging()
    uvicorn.run(
        "rabeeh_core.infra.server:app",
        host=args.host or settings.host,
        port=args.port or settings.port,
        reload=args.reload,
        log_level=settings.log_level.lower(),
    )
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """Run a single goal through the orchestrator and print the result."""
    from .orchestration.runner import get_orchestrator

    configure_logging()
    state = asyncio.run(get_orchestrator().run(args.goal))
    print(json.dumps(state.snapshot(), indent=2, default=str))
    return 0 if state.status.value == "completed" else 1


def _cmd_info(_args: argparse.Namespace) -> int:
    """Print masked settings as JSON."""
    settings = get_settings()
    print(json.dumps(settings.log_safe(), indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI parser (separate for testability)."""
    parser = argparse.ArgumentParser(prog="rabeeh", description="Rabeeh AI Agent Pro CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="Run the FastAPI API server.")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.add_argument("--reload", action="store_true", help="Auto-reload on code changes (dev).")
    p_serve.set_defaults(func=_cmd_serve)

    p_run = sub.add_parser("run", help="Run a one-shot goal.")
    p_run.add_argument("goal", help="The goal to accomplish.")
    p_run.set_defaults(func=_cmd_run)

    p_info = sub.add_parser("info", help="Print masked configuration.")
    p_info.set_defaults(func=_cmd_info)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint used by the ``rabeeh`` console script."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        _log.info("Interrupted by user.")
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
