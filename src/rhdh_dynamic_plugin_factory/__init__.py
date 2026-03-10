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
    WorkspaceInfo,
    PluginListConfig,
    discover_workspaces,
    clone_workspaces_with_worktrees,
)
from .exceptions import (
    PluginFactoryError,
    ConfigurationError,
    ExecutionError,
)
from .logger import (
    setup_logging,
    get_logger,
    LEVELS,
)
from .utils import (
    run_command_with_streaming,
    display_export_results,
    clean_directory,
    prompt_or_clean_directory,
    repo_dir_name,
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

