"""structlog JSON renderer to stdout (Constitution Workflow §3)."""

import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            timestamper,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(stream=sys.stdout, level=numeric_level, format="%(message)s")

    structlog.get_logger().info("logging.configured", level=level.upper())
