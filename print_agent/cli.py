"""CLI entrypoint for the print agent."""

from __future__ import annotations

import argparse
import logging
import sys

from print_agent.config import Config, ConfigError
from print_agent.orchestrator import Orchestrator


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Local print agent — polls Odoo for pending receipt print jobs."
    )
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Path to YAML config file (default: config.yaml)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single poll cycle then exit (for testing)",
    )
    parser.add_argument(
        "--job-delay",
        type=float,
        default=2.0,
        help="Seconds to wait between print jobs (default: 2.0)",
    )

    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    logger = logging.getLogger("print_agent")

    try:
        config = Config.from_file(args.config)
    except ConfigError as e:
        logger.error("Configuration error: %s", e)
        return 1

    logger.info("Print agent starting with %d printer(s)", len(config.printers))
    for printer in config.printers:
        logger.info(
            "  Printer '%s' (%s)", printer.name, printer.connection_type
        )
    logger.info("Job delay: %.1f seconds", args.job_delay)

    orch = Orchestrator(config, job_delay=args.job_delay)

    if args.once:
        orch._poll_once()
        return 0

    try:
        orch.run()
    except KeyboardInterrupt:
        logger.info("Shutting down")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
