"""
Logging utilities for RHDH Plugin Factory.
"""

import logging
from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install

LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

def setup_logging(
    level: str = "INFO",
    verbose: bool = False,
) -> logging.Logger:
    """
    Set up logging configuration.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        verbose: Whether to show verbose output (show file and line number)
    Returns:
        Configured logger instance
    """
    
    install(show_locals=True)
    
    logger = logging.getLogger("rhdh_dynamic_plugin_factory")
    logger.setLevel(getattr(logging, level.upper() if level.upper() in LEVELS else "INFO"))
    console = Console(stderr=True)
    handler = RichHandler(
        console=console,
        show_time=False,
        show_path=verbose,
        markup=True,
        rich_tracebacks=True,
    )
    handler.setLevel(getattr(logging, level.upper() if level.upper() in LEVELS else "INFO"))

    logger.addHandler(handler)

    # Prevent duplicate logs
    logger.propagate = False
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given name."""
    return logging.getLogger(f"rhdh_dynamic_plugin_factory.{name}")

