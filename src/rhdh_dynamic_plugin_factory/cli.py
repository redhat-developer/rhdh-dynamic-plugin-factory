"""
Command-line interface for RHDH Plugin Factory - Setup and orchestration tool.
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
# Handle both direct script execution and module execution
try:
    from .logger import setup_logging, get_logger
    from .config import PluginFactoryConfig, SourceConfig, PluginListConfig
except ImportError:
    # For direct script execution, add parent directory to path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from rhdh_dynamic_plugin_factory.logger import setup_logging, get_logger
    from rhdh_dynamic_plugin_factory.config import PluginFactoryConfig, SourceConfig, PluginListConfig

from dotenv import load_dotenv

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
        python src/rhdh_dynamic_plugin_factory --config-dir ./config --repo-path ./workspace --no-push-images --workspace-path workspaces/todo --log-level DEBUG --output-dir ./outputs
        """
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
        default=True,
        help="Push images to registry (default: true)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/output"),
        help="Path to the output directory"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show verbose output (show file and line number)"
    )
    return parser


def discover_source_config(config: PluginFactoryConfig, config_dir: Path, repo_path: Optional[Path]) -> Optional[SourceConfig]:
    source_file = config_dir / "source.json"

    if source_file.exists():
        try:
            return SourceConfig.from_file(source_file)
        except Exception as e:
            config.logger.error(f"[yellow]Warning: Failed to load {source_file}: {e}[/yellow]")
            if repo_path and repo_path.exists():
                config.logger.info("Attempting to use locally stored plugin source code")
            else:
                config.logger.error(f"[red]Failed to load {source_file} and locally stored plugin source code doesn't exist: {e}[/red]")
                sys.exit(1)
    return None


def setup_config_directory(config: PluginFactoryConfig, args: argparse.Namespace) -> None:
    """Setup and validate configuration directory structure."""
    logger.info("[bold blue]Setting up configuration directory[/bold blue]")
    
    config_dir = config.config_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    
    env_file = config_dir / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)
        config.logger.debug(f"Loaded .env file: {env_file}")
    
    # Check for source configuration
    source_config = discover_source_config(config, config_dir, args.repo_path)
    if source_config:
        config.logger.info(f"Found source configuration")
        config.logger.info(f"  Repository: {source_config.get_repo_owner_and_name()}")
        config.logger.info(f"  Reference: {source_config.repo_ref}")
        config.logger.info(f"  Backstage version: {source_config.repo_backstage_version}")
    
    # Setup or validate plugins-list.yaml
    plugins_list_file = config_dir / "plugins-list.yaml"
    
    if not plugins_list_file.exists():
        # Try to auto-generate from workspace - create plugins-list.yaml (preferred by scripts)
        config_dir = getattr(config, 'config_dir', Path('/config'))
        if config_dir.exists():
            config.logger.info(f"Attempting to auto-generate plugins-list.yaml: {plugins_list_file}")
            if not auto_generate_plugins_list(config_dir, args.repo_path):
                config.logger.error(f"[red]Failed to auto-generate plugins-list.yaml[/red]")
                exit(1)
        else:
            config.logger.error(f"[red]{config_dir} does not exist, please create it first[/red]")
            exit(1)
    else:
        config.logger.debug(f"Using plugin list file: {plugins_list_file}")



def validate_config_directory(config: PluginFactoryConfig, push_images: bool = False) -> bool:
    """Validate that configuration directory has all required files and optionally registry environment variables."""
    
    config_dir = config.config_dir
    validation_success = True
    
    # Check for plugin list file
    plugins_list_file = config_dir / "plugins-list.yaml"
    
    if plugins_list_file.exists():
        config.logger.debug(f"Plugin list file found: {plugins_list_file}")
    else:
        config.logger.warning(f"[yellow]Missing plugins-list.yaml, attempting to auto-generate[/yellow]")
        validation_success = False
    
    # Only validate registry configuration if we're pushing images
    if push_images:
        config.logger.debug("Validating registry configuration for push operations")
        
        if not config.registry_url:
            config.logger.error(f"[red]Missing REGISTRY_URL environment variable (required for --push-images)[/red]")
            validation_success = False
        else:
            config.logger.debug(f"Registry URL: {config.registry_url}")
            
        if not config.registry_namespace:
            config.logger.error(f"[red]Missing REGISTRY_NAMESPACE environment variable (required for --push-images)[/red]")
            validation_success = False
        else:
            config.logger.debug(f"Registry namespace: {config.registry_namespace}")
        
        # Registry credentials are optional (for public registries or pre-authenticated systems)
        if config.registry_username and config.registry_password:
            config.logger.debug("Registry credentials provided")
        else:
            config.logger.info("Registry credentials not provided - will skip podman login")
    else:
        config.logger.debug("Skipping registry validation (not pushing images)")

    return validation_success


def clone_source_repository(source_config: SourceConfig, repo_path: Path) -> bool:
    """Clone the source repository to the workspace path."""
    
    if not repo_path.exists():
        source_config.logger.error(f"[red]Workspace does not exist: {repo_path}[/red]")
        return True
    
    source_config.logger.info(f"[bold blue]Cloning repository[/bold blue]")
    source_config.logger.info(f"Repository: {source_config.get_repo_owner_and_name()}")
    source_config.logger.info(f"Reference: {source_config.repo_ref}")
    source_config.logger.info(f"Workspace: {repo_path}")
        
    try:
        cmd = ["git", "clone", source_config.get_repo_url(), str(repo_path)]
        with subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        ) as proc:
            for line in proc.stdout:
                logger.info(line.rstrip())
            proc.wait()
            if proc.returncode != 0:
                logger.error(f"Failed to clone repository (exit code {proc.returncode})")
                return False
        
        # Checkout specific ref if provided
        if source_config.repo_ref:
            cmd = ["git", "checkout", source_config.repo_ref]
            logger.info(f"[cyan]Checking out ref: {source_config.repo_ref}[/cyan]")
            with subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=repo_path,
                text=True,
                bufsize=1,
            ) as proc:
                for line in proc.stdout:
                    logger.info(line.rstrip())
                proc.wait()
                if proc.returncode != 0:
                    logger.error(f"Failed to checkout ref {source_config.repo_ref} (exit code {proc.returncode})")
                    return False
        logger.info("[green]Repository cloned successfully[/green]")
        return True
        
    except Exception as e:
        logger.error(f"Failed to clone repository: {e}")
        return False


def auto_generate_plugins_list(config_dir: Path, repo_path: Path) -> bool:
    """Auto-generate plugins-list.yaml from workspace structure."""
    
    plugins_file = config_dir / "plugins-list.yaml"
    
    if plugins_file.exists():
        logger.info(f"plugins-list.yaml already exists: {plugins_file}")
        return True
    
    logger.info("[bold blue]Auto-generating plugins-list.yaml[/bold blue]")
    
    try:
        plugin_cfg = PluginListConfig.create_default(repo_path)
        plugin_cfg.to_file(plugins_file)
        
        plugins = plugin_cfg.get_plugins()
        if plugins:
            logger.info(f"Generated plugins-list.yaml with {len(plugins)} plugins")
            for plugin_path in plugins.keys():
                logger.info(f"  - {plugin_path}")
        else:
            logger.warning("No plugins found in workspace")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to auto-generate plugins list: {e}")
        return False


def install_dependencies(yarn_version: str, workspace_path: Path) -> bool:
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
            process = subprocess.Popen(
                cmd,
                cwd=workspace_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,  # Pass environment with corepack settings
            )
            
            # Read output line by line
            for line in process.stdout:
                logger.info(line.rstrip())
            
            # Wait for completion
            process.wait()
            
            if process.returncode != 0:
                logger.error(f"{description} failed with exit code {process.returncode}")
                return False
            
            logger.info(f"[green]✓ {description} completed[/green]")
        
        return True
    except Exception as e:
        logger.error(f"Failed to install dependencies: {e}")
        return False


def apply_patches_and_overlays(config: PluginFactoryConfig) -> bool:
    """Apply patches and overlays using override-sources.sh script."""
    config.logger.info("[bold blue]Applying patches and overlays[/bold blue]")
    
    script_dir = Path(__file__).parent.parent.parent / "scripts"
    script_path = script_dir / "override-sources.sh"
    
    if not script_path.exists():
        config.logger.error(f"[red]Script not found: {script_path}[/red]")
        return False
    
    repo_path = getattr(config, 'repo_path', Path('/workspace'))
    workspace_path = repo_path.joinpath(config.workspace_path).absolute()
    # Run override-sources.sh script
    cmd = [
        str(script_path),
        str(config.config_dir.absolute()),  # Overlay root directory
        str(workspace_path),     # Target directory 
    ]

    try:
        # Stream output in real-time
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=workspace_path
        )
        
        # Read stdout and stderr line by line in real-time
        for line in process.stdout:
            config.logger.info(line.rstrip())
        
        # Wait for process to complete and get return code
        process.wait()
        
        # Capture any remaining stderr
        if process.returncode == 0:
            config.logger.info("[green]Patches and overlays applied successfully[/green]")
            return True
        else:
            config.logger.error(f"[red]Patches/overlays failed with exit code {process.returncode}[/red]")
            return False
            
    except Exception as e:
        config.logger.error(f"[red]Failed to run patch script: {e}[/red]")
        return False


def export_plugins(config: PluginFactoryConfig, args: argparse.Namespace) -> bool:
    """Export plugins using export-workspace.sh script."""
    config.logger.info("[bold blue]Exporting plugins using RHDH CLI[/bold blue]")
    
    script_dir = Path(__file__).parent.parent.parent / "scripts"
    script_path = script_dir / "export-workspace.sh"
    
    if not script_path.exists():
        config.logger.error(f"[red]Script not found: {script_path}[/red]")
        return False
    
    plugins_list_file = config.config_dir / "plugins-list.yaml"
    
    if not plugins_list_file.exists():
        config.logger.error("[red]No plugins file found[/red]")
        return False    

    # Load config directory .env file for script variables
    config_env_file = config.config_dir / ".env"
    default_env_file = Path(__file__).parent.parent.parent / "default.env"
    load_dotenv(default_env_file)
    env = dict(os.environ)
    
    if config_env_file.exists():
        config.logger.debug(f"Loading script configuration from: {config_env_file}")
        load_dotenv(config_env_file, override=True)
        # Reload env after loading .env
        env = dict(os.environ)
    destination = args.output_dir
    destination.mkdir(parents=True, exist_ok=True)
    env["INPUTS_DESTINATION"] = str(destination)
    # TODO: Figure out how to have users specify image repository prefix and tag prefix
    # Perhaps in the environmental variables?
    # Set required environment variables for the script
    env.update({
        "INPUTS_SCALPRUM_CONFIG_FILE_NAME": "scalprum-config.json",
        "INPUTS_SOURCE_OVERLAY_FOLDER_NAME": "overlay",
        "INPUTS_SOURCE_PATCH_FILE_NAME": "patch",
        "INPUTS_APP_CONFIG_FILE_NAME": "app-config.dynamic.yaml",
        "INPUTS_PLUGINS_FILE": str(plugins_list_file.absolute()),
        "INPUTS_CLI_PACKAGE": "@red-hat-developer-hub/cli",
        "INPUTS_PUSH_CONTAINER_IMAGE": "true" if args.push_images else "false",
        "INPUTS_JANUS_CLI_VERSION": config.rhdh_cli_version,
        "INPUTS_IMAGE_REPOSITORY_PREFIX": f"{config.registry_url or 'localhost'}/{config.registry_namespace or 'default'}",
        "INPUTS_DESTINATION": str(destination.absolute()),
        "INPUTS_CONTAINER_BUILD_TOOL": "buildah",
    })

  
    
    # Run export-workspace.sh script in the workspace directory
    repo_path = getattr(config, 'repo_path', Path('/workspace'))
    workspace_path = repo_path.joinpath(config.workspace_path).absolute()
    try:
        # Stream output in real-time
        process = subprocess.Popen(
            [str(script_path.absolute())],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
            cwd=workspace_path
        )
        
        # Read stdout and stderr line by line in real-time
        for line in process.stdout:
            config.logger.info(line.rstrip())
        
        # Wait for process to complete and get return code
        process.wait()
        
        # Capture any remaining stderr
        stderr_output = process.stderr.read()
        if stderr_output:
            config.logger.error(f"[red]{stderr_output.rstrip()}[/red]")
        
        if process.returncode != 0:
            config.logger.error(f"[red]Plugin export script failed with exit code {process.returncode}[/red]")
            return False
        
        # Check if any plugins failed to export
        has_failures = _display_export_results()
        
        if has_failures:
            config.logger.error("[red]Plugin export completed with failures[/red]")
            return False
        else:
            config.logger.info("[green]Plugin export completed successfully[/green]")
            return True

    except Exception as e:
        config.logger.error(f"[red]Failed to run export script: {e}[/red]")
        return False


def _display_export_results() -> bool:
    """Display results from export script output files.
    
    Returns:
        True if there were any failed exports, False otherwise.
    """
    failed_file = Path("failed-exports-output")
    published_file = Path("published-exports-output")
    has_failures = False
    
    if failed_file.exists():
        failed_exports = failed_file.read_text().strip().split('\n') if failed_file.stat().st_size > 0 else []
        if failed_exports and failed_exports[0]:
            has_failures = True
            logger.error(f"Failed exports ({len(failed_exports)}): {', '.join(failed_exports)}")
    
    if published_file.exists():
        published_exports = published_file.read_text().strip().split('\n') if published_file.stat().st_size > 0 else []
        if published_exports and published_exports[0]:
            logger.info(f"[green]Published images ({len(published_exports)}):[/green]")
            for image in published_exports:
                logger.info(f"  - {image}")
    
    return has_failures


def main():
    """Main entry point for the RHDH Dynamic Plugin Factory."""
    parser = create_parser()
    args = parser.parse_args()
    # Set up logging
    setup_logging(level=args.log_level)

    # Load configuration
    config = PluginFactoryConfig.load_from_env(args=args, env_file=args.config_dir / ".env")
    
    # Override with CLI options
    if args.config_dir:
        config.config_dir = args.config_dir
    if args.workspace_path:
        config.workspace_path = args.workspace_path
    if args.repo_path:
        config.repo_path = args.repo_path
    
    config.log_level = args.log_level
    
    try:
        # Validate basic configuration
        config.validate()
        config.load_registry_config(push_images=args.push_images)
    except Exception as e:
        config.logger.error(f"[red]Configuration error: {e}[/red]")
        sys.exit(1)
    
    # Phase 1: Setup configuration directory
    logger.info("[bold blue]Configuration Setup[/bold blue]")
    setup_config_directory(config, args)
    
    # Validate setup
    if not validate_config_directory(config, push_images=args.push_images):
        logger.error("Configuration validation failed")
        sys.exit(1)
    
    # Phase 2: Determine source configuration
    logger.info("[bold blue]Source Configuration[/bold blue]")
    source_config = args.config_dir / "source.json"
    repo_path = getattr(config, 'repo_path', Path('/workspace'))

    # Load source configuration from CLI args or auto-discovery
    if source_config.exists():
        source_config = SourceConfig.from_file(source_config)
        logger.info(f"Using source config from: {source_config}")
    else:
        # Try to auto-discover source config
        source_config = discover_source_config(config, args.config_dir, args.repo_path)
        if source_config:
            logger.info("Auto-discovered source configuration")
    
    # Phase 3: Clone repository if needed
    if source_config:
        # TODO: Add user config to use choose between local or remote repository. Currently remote is prioritized if `source.json` is found.
        logger.info("[bold blue]Repository Setup[/bold blue]")
        if not clone_source_repository(source_config, args.repo_path):
            logger.error("Failed to clone repository")
            sys.exit(1)
        
        # Auto-generate plugins-list.yaml if needed
        if not auto_generate_plugins_list(config.config_dir, repo_path):
            logger.error("Failed to generate plugins list")
            sys.exit(1)
    elif not repo_path.exists():
        logger.error("No source configuration found and workspace doesn't exist")
        logger.error("Either provide --source-config, --repo-url, or ensure workspace exists")
        sys.exit(1)
    
    # Phase 4: Apply patches and overlays
    logger.info("[bold blue]Applying Patches and Overlays[/bold blue]")
    if not apply_patches_and_overlays(config):
        logger.error("Failed to apply patches and overlays")
        sys.exit(1)

    
    # Phase 4.5: Install Dependencies
    logger.info("[bold blue]Installing Dependencies[/bold blue]")
    
    workspace_path = repo_path.joinpath(config.workspace_path).absolute()
    if not install_dependencies(config.yarn_version, workspace_path):
        logger.error("Failed to install dependencies")
        sys.exit(1)
    
    # Phase 5: Export plugins
    logger.info("[bold blue]Exporting Plugins[/bold blue]")
    if not export_plugins(config, args):
        logger.error("Plugin export failed")
        sys.exit(1)
    
    logger.info("[green]✓ All operations completed successfully[/green]")


if __name__ == "__main__":
    main()