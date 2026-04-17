"""
RHDH Dynamic Plugin Factory.

A tool for building and managing Red Hat Developer Hub (RHDH) dynamic plugins.
This package provides configuration management, plugin list handling, and
automated build orchestration for Backstage plugins.
"""

from .__version__ import __version__
from .cli import create_parser, main
from .config import PluginFactoryConfig
from .exceptions import (
    ConfigurationError,
    ExecutionError,
    PluginFactoryError,
)
from .logger import (
    LEVELS,
    get_logger,
    setup_logging,
)
from .plugin_list_config import PluginListConfig
from .source_config import (
    SourceConfig,
    WorkspaceInfo,
    clone_workspaces_with_worktrees,
    discover_workspaces,
)
from .utils import (
    clean_directory,
    display_export_results,
    prompt_or_clean_directory,
    repo_dir_name,
    run_command_with_streaming,
)

__all__ = [
    # CLI
    "main",
    "create_parser",
    # Configuration
    "PluginFactoryConfig",
    "SourceConfig",
    "WorkspaceInfo",
    "PluginListConfig",
    "discover_workspaces",
    "clone_workspaces_with_worktrees",
    # Exceptions
    "PluginFactoryError",
    "ConfigurationError",
    "ExecutionError",
    # Logging
    "setup_logging",
    "get_logger",
    "LEVELS",
    # Utilities
    "run_command_with_streaming",
    "display_export_results",
    "clean_directory",
    "prompt_or_clean_directory",
    "repo_dir_name",
    # Version
    "__version__",
]
