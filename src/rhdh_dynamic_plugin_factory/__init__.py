"""
RHDH Dynamic Plugin Factory.

A tool for building and managing Red Hat Developer Hub (RHDH) dynamic plugins.
This package provides configuration management, plugin list handling, and
automated build orchestration for Backstage plugins.
"""

from .__version__ import __version__
from .cli import main, create_parser
from .config import (
    PluginFactoryConfig,
    SourceConfig,
    PluginListConfig,
)
from .logger import (
    setup_logging,
    get_logger,
    LEVELS,
)
from .utils import (
    run_command_with_streaming,
    display_export_results,
)

__all__ = [
    # CLI
    "main",
    "create_parser",
    
    # Configuration
    "PluginFactoryConfig",
    "SourceConfig",
    "PluginListConfig",
    
    # Logging
    "setup_logging",
    "get_logger",
    "LEVELS",
    
    # Utilities
    "run_command_with_streaming",
    "display_export_results",
    
    # Version
    "__version__",
]

