"""
Command-line interface for RHDH Plugin Factory - Setup and orchestration tool.
"""

import sys
import os
import argparse
from pathlib import Path

# Handle both direct script execution and module execution
try:
    from .__version__ import __version__
    from .logger import setup_logging, get_logger
    from .config import PluginFactoryConfig
    from .utils import run_command_with_streaming
except ImportError:
    # For direct script execution, add parent directory to path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from rhdh_dynamic_plugin_factory.__version__ import __version__
    from rhdh_dynamic_plugin_factory.logger import setup_logging, get_logger
    from rhdh_dynamic_plugin_factory.config import PluginFactoryConfig
    from rhdh_dynamic_plugin_factory.utils import run_command_with_streaming

logger = get_logger("cli")

def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        description="RHDH Dynamic Plugin Factory - Setup and orchestrate plugin building",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
        # Build plugins for the todo workspace in backstage/community-plugins w/o pushing to a registry
        # This assumes that ./config is populated with the required source.json and plugins-list.yaml files
        python src/rhdh_dynamic_plugin_factory --config-dir ./config --repo-path ./workspace --workspace-path workspaces/todo --log-level DEBUG --output-dir ./outputs
        """
    )
    
    # Version flag
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=__version__
    )
    
    # Global options
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level"
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path("/config"),
        help="Configuration directory path containing plugin-list.yaml, .env, patches/ and overlays/ directories"
    )
    parser.add_argument(
        "--repo-path",
        type=Path,
        default=Path("/workspace"),
        help="Path to store the plugin source code"
    )
    parser.add_argument(
        "--workspace-path",
        type=Path,
        help="Path to the workspace from root of the repository"
    )

    parser.add_argument(
        "--push-images",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Push images to registry (default: false)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/output"),
        help="Path to the output directory"
    )
    parser.add_argument(
        "--use-local",
        action="store_true",
        default=False,
        help="Use local repository content instead of cloning from source.json"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show verbose output (show file and line number)"
    )
    return parser

def install_dependencies(workspace_path: Path) -> bool:
    """Install dependencies in the workspace using yarn install with corepack."""
    logger.info("[bold blue]Installing workspace dependencies[/bold blue]")

    # Commands to run in sequence
    commands = [
        (["pwd"], "Checking workspace path"),
        (["corepack", "enable"], "Enabling corepack"),
        (["yarn", "--version"], "Checking yarn version"),
        (["yarn", "install", "--immutable"], "Installing dependencies"),
        (["yarn", "tsc"], "Running TypeScript compilation"),
    ]
        
    try:
        # Set up environment for non-interactive corepack
        env = os.environ.copy()
        env['COREPACK_ENABLE_DOWNLOAD_PROMPT'] = '0'  # Disable download prompts
        
        for cmd, description in commands:
            logger.info(f"[cyan]{description}...[/cyan]")
            
            # Stream output in real-time
            returncode = run_command_with_streaming(
                cmd,
                logger,
                cwd=workspace_path,
                env=env
            )
            
            if returncode != 0:
                logger.error(f"{description} failed with exit code {returncode}")
                return False
            
            logger.info(f"[green]✓ {description} completed[/green]")
        
        return True
    except Exception as e:
        logger.error(f"Failed to install dependencies: {e}")
        return False

def main():
    """Main entry point for the RHDH Dynamic Plugin Factory."""
    parser = create_parser()
    args = parser.parse_args()
    # Set up logging
    setup_logging(level=args.log_level, verbose=args.verbose)
    logger.info("[bold blue]Setting up configuration directory[/bold blue]")

    # Load configuration
    config = PluginFactoryConfig.load_from_env(args=args, env_file=args.config_dir / ".env")

    try:
        config.load_registry_config(push_images=args.push_images)
        source_config = config.setup_config_directory()
    except Exception as e:
        config.logger.error(f"[red]Configuration error: {e}[/red]")
        sys.exit(1)
    
    # Clone repository if needed
    if source_config and not config.use_local:
        logger.info("[bold blue]Repository Setup[/bold blue]")
        if not source_config.clone_to_path(config.repo_path):
            logger.error("Failed to clone repository")
            sys.exit(1)
    elif config.use_local or not source_config:
        if config.use_local:
            logger.info("[bold blue]--use-local flag is set, using local repository[/bold blue]")
        else:
            logger.info("[bold blue]No source configuration found, using local repository[/bold blue]")
        # Use local repository (either --use-local flag or no source_config)
        if not config.repo_path.exists():
            logger.error(f"Local repository does not exist at: {config.repo_path}")
            logger.error("Either provide source.json to clone the repository, or ensure workspace exists at directory specified by --repo-path")
            sys.exit(1)
        logger.info(f"Using local repository at: {config.repo_path}")
    
    # Auto-generate plugins-list.yaml if needed (after repository is available)
    if not config.auto_generate_plugins_list():
        logger.error("Failed to generate plugins list")
        sys.exit(1)
    # Apply patches and overlays
    logger.info("[bold blue]Applying Patches and Overlays[/bold blue]")
    if not config.apply_patches_and_overlays():
        logger.error("Failed to apply patches and overlays")
        sys.exit(1)

    
    # Install Dependencies
    logger.info("[bold blue]Installing Dependencies[/bold blue]")
    
    workspace_path = config.repo_path.joinpath(config.workspace_path).absolute()
    if not install_dependencies(workspace_path):
        logger.error("Failed to install dependencies")
        sys.exit(1)
    
    # Export plugins
    logger.info("[bold blue]Exporting plugins using RHDH CLI[/bold blue]")
    if not config.export_plugins(args.output_dir, args.push_images):
        logger.error("Plugin export failed")
        sys.exit(1)
    
    logger.info("[green]✓ All operations completed successfully[/green]")


if __name__ == "__main__":
    main()