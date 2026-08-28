"""DATS main entry point — service runner.

Config-driven system initialization, lifecycle management,
and graceful shutdown.

Usage:
    python -m src.main
    python -m src.main --config-prefix MYAPP_
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from system.bootstrap import SystemBootstrap
from system.lifecycle import SystemLifecycle
from system.registry import ComponentRegistry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


async def run_service(prefix: str = "DATS_") -> int:
    """Run the DATS trading service.

    Args:
        prefix: Environment variable prefix for config.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    from system.config_loader import ConfigLoader

    config = ConfigLoader(prefix=prefix)
    bootstrap = SystemBootstrap(config_loader=config)
    result = bootstrap.bootstrap()

    if not result.success:
        logger.error("Bootstrap failed: %s", result.errors)
        return 1

    lifecycle: SystemLifecycle = result.lifecycle
    registry: ComponentRegistry = result.registry

    # Install signal handlers for graceful shutdown
    lifecycle.install_signal_handlers()

    # Start the system
    startup_ok = await lifecycle.start()
    if not startup_ok:
        logger.error("Startup failed")
        return 1

    logger.info("DATS service running. Press Ctrl+C to stop.")

    # Wait for shutdown signal
    while lifecycle.is_running and not lifecycle.is_shutting_down:
        await asyncio.sleep(1.0)

    # Graceful shutdown
    await lifecycle.stop()
    logger.info("DATS service stopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Command line arguments.

    Returns:
        Exit code.
    """
    parser = argparse.ArgumentParser(description="DATS Trading Service")
    parser.add_argument(
        "--config-prefix",
        default="DATS_",
        help="Environment variable prefix (default: DATS_)",
    )
    args = parser.parse_args(argv)

    try:
        return asyncio.run(run_service(prefix=args.config_prefix))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 0
    except Exception:
        logger.exception("Service crashed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
