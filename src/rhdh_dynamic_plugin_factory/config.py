"""
Configuration management for RHDH Plugin Factory.
"""

import argparse
import os
from pathlib import Path
import sys
from typing import Dict, Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv
import yaml
import json
from .logger import get_logger
from .utils import run_command_with_streaming, display_export_results

@dataclass
class PluginFactoryConfig:
    """Main configuration for the plugin factory."""
    
    # Required fields loaded from default.env file (can be overridden by environment variables)
    rhdh_cli_version: str = field(default="")
    
    # Directories
    repo_path: str = field(default="/workspace")  # Local path where plugin source code will be stored
    config_dir: str = field(default="/config")
    
    # Registry configuration (loaded from environment variables, only required for push operations)
    registry_url: Optional[str] = field(default=None)
    registry_username: Optional[str] = field(default=None)
    registry_password: Optional[str] = field(default=None)
    registry_namespace: Optional[str] = field(default=None)
    registry_insecure: bool = field(default=False)

    # Logging
    log_level: str = field(default="INFO")
    
    # Local repository flag
    use_local: bool = field(default=False)

    logger = get_logger("config")
    @classmethod
    def load_from_env(cls, args: argparse.Namespace, env_file: Optional[Path] = None) -> "PluginFactoryConfig":
        """Load configuration from environment variables and .env files.
        
        Loads default.env first, then optionally loads additional env file to override defaults or provide additional values.
        Environment variables take precedence over .env file values.
        
        Args:
            env_file: Optional additional .env file to merge with defaults
        """
        
        # Create config with environment overrides
        config = cls()
        
        # First, load default.env if it exists
        default_env_path = Path(__file__).parent.parent.parent / "default.env"
        
        config.logger.debug(f'[bold blue]Loading environment variables from {default_env_path}[/bold blue]')

        if default_env_path.exists():
            load_dotenv(default_env_path)
            config.logger.debug(f'[green]✓ Loaded {default_env_path}[/green]')
            
        # Then load additional env file if specified and exists
        if env_file and env_file.exists():
            load_dotenv(env_file, override=True)
            config.logger.debug(f'[green]✓ Loaded {env_file}[/green]')

        config.logger.debug(f'[bold blue]Loading configuration from environment variables and CLI arguments[/bold blue]')
        
        try:
            config.workspace_path = Path(os.getenv("WORKSPACE_PATH", args.workspace_path))
            config.logger.debug(f'[green]✓ Relative workspace path set to {config.workspace_path}[/green]')
        except Exception as e:
            config.logger.error(f"[red]Failed to set workspace path, please set WORKSPACE_PATH environment variable or use the --workspace-path argument: {e}[/red]")
            sys.exit(1)
        
        config.config_dir = Path(args.config_dir)
        config.repo_path = Path(args.repo_path)
        
        # Load version defaults from environment (set by default.env)
        config.rhdh_cli_version = os.getenv("RHDH_CLI_VERSION")

        # Load registry configuration from environment variables
        config.registry_url = os.getenv("REGISTRY_URL")
        config.registry_username = os.getenv("REGISTRY_USERNAME")
        config.registry_password = os.getenv("REGISTRY_PASSWORD")
        config.registry_namespace = os.getenv("REGISTRY_NAMESPACE")
        config.registry_insecure = os.getenv("REGISTRY_INSECURE", "false").lower() == "true"

        config.log_level = os.getenv("LOG_LEVEL", args.log_level)
        
        # Load use_local flag from args
        config.use_local = args.use_local
        
        # Validate and create required directories
        dirs_to_create = [config.config_dir, config.repo_path]
        for dir_path in dirs_to_create:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # Validate required version fields
        if not config.rhdh_cli_version:
            raise ValueError("RHDH_CLI_VERSION must be set (usually loaded from default.env)")
        
        # Validate log level
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if config.log_level.upper() not in valid_log_levels:
            raise ValueError(f"Invalid log level: {config.log_level}")
        
        # Validate source.json and plugins-list.yaml
        config._validate_source_json()
        config._validate_plugins_list()
        
        return config
    
    def load_registry_config(self, push_images: bool = False) -> None:
        """
        Load registry configuration from environment variables and attempt buildah login.
        Only validates required registry fields if `push_images` is True.
        """
        import subprocess
        # Only validate registry configuration if we're pushing images
        if not push_images:
            self.logger.info("Skipping registry configuration (not pushing images)")
            return
            
        # Validate required registry configuration for push operations
        if not self.registry_url:
            raise ValueError("REGISTRY_URL environment variable is required when --push-images is enabled")
        
        if not self.registry_namespace:
            raise ValueError("REGISTRY_NAMESPACE environment variable is required when --push-images is enabled")
        
        # Attempt buildah login if credentials are available
        if self.registry_username and self.registry_password:
            try:
                cmd = [
                    "buildah", "login",
                    "--username", str(self.registry_username),
                    "--password", str(self.registry_password)
                ]
                
                # Add insecure flag if needed
                if self.registry_insecure:
                    cmd.extend(["--tls-verify=false"])
                    
                cmd.append(str(self.registry_url))
                
                subprocess.run(
                    cmd,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                self.logger.info(f"Logged in to registry {self.registry_url} with buildah.")
            except subprocess.CalledProcessError as e:
                self.logger.warning(
                    f"Failed to login to registry {self.registry_url} with buildah: {e.stderr.decode().strip()}"
                )
        ## TODO: Add support for token logins for ghcr.io registry as well
        else:
            self.logger.info("Registry credentials not provided, skipping buildah login.")
    
    def _validate_source_json(self) -> None:
        """Validate source.json file existence and repo_path state."""
        source_file = self.config_dir / "source.json"
        
        if not source_file.exists():
            # Check if repo_path is empty
            if not self.repo_path.exists() or not any(self.repo_path.iterdir()):
                raise ValueError(
                    f"source.json not found at {source_file} and {self.repo_path} is empty. "
                    "Please provide source.json to clone a repository or use --use-local with a locally mounted repository."
                )
            else:
                self.logger.warning(
                    f"source.json not found at {source_file}. Attempting to use local repository content at {self.repo_path}"
                )
    
    def _validate_plugins_list(self) -> None:
        """Validate plugins-list.yaml file existence."""
        plugins_file = self.config_dir / "plugins-list.yaml"
        
        if not plugins_file.exists():
            self.logger.warning(
                f"plugins-list.yaml not found at {plugins_file}. Will attempt to auto-generate after repository is available."
            )
    
    def auto_generate_plugins_list(self) -> bool:
        """
        Auto-generate plugins-list.yaml
        Assumes the following:
        - The repository is cloned to the `repo_path`
        - The plugins are located in the plugins/* directory
        - `workspace_path` is the path to the workspace from the root of the repository
        """
        plugins_file = self.config_dir / "plugins-list.yaml"
        
        if plugins_file.exists():
            self.logger.info(f"[green]✓ plugins-list.yaml already exists at {plugins_file}[/green]")
            return True
        
        self.logger.info("[bold blue]Auto-generating plugins-list.yaml[/bold blue]")
        
        try:
            if not self.repo_path.exists():
                self.logger.error(f"[red]Repository does not exist at {self.repo_path}[/red]")
                return False
            workspace_path = self.repo_path.joinpath(self.workspace_path).absolute()
            if not workspace_path.exists():
                self.logger.error(f"[red]Workspace does not exist at {workspace_path}[/red]")
                return False
            
            plugin_cfg = PluginListConfig.create_default(workspace_path=workspace_path)
            plugin_cfg.to_file(plugins_file)
            
            plugins = plugin_cfg.get_plugins()
            if plugins:
                self.logger.info(f"Generated plugins-list.yaml with {len(plugins)} plugins")
                for plugin_path in plugins.keys():
                    self.logger.info(f"  - {plugin_path}")
            else:
                self.logger.warning("No plugins found in workspace")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to auto-generate plugins list: {e}")
            return False
    
    def discover_source_config(self) -> Optional["SourceConfig"]:
        """Discovers and loads source configuration from config_dir/source.json."""
        source_file = self.config_dir / "source.json"

        if source_file.exists() and not self.use_local:
            try:
                source_config = SourceConfig.from_file(source_file)
                self.logger.info(f"Using source config from: {source_config}")
                return source_config
            except Exception as e:
                self.logger.error(f"[red]Failed to load {source_file}: {e}[/red]")
                sys.exit(1)
        elif self.repo_path and self.repo_path.exists():
            self.logger.info("Source configuration not found, will attempt to use locally stored plugin source code")
        else:
            self.logger.error(
                f"[red]No valid source configuration found and {self.repo_path} is empty or does not exist[/red]"
                f"Either provide a valid {source_file} or ensure locally stored plugin source code exists at {self.repo_path}"
            )
            sys.exit(1)
    
    def setup_config_directory(self) -> "SourceConfig":
        """Setup and validate configuration directory structure."""
        self.logger.info("[bold blue]Setting up configuration directory[/bold blue]")
        
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        env_file = self.config_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=True)
            self.logger.debug(f"Loaded .env file: {env_file}")
        
        # Check for source configuration
        source_config = self.discover_source_config()
        if source_config:
            self.logger.info(f"Found source configuration")
            self.logger.info(f"  Repository: {source_config.repo}")
            self.logger.info(f"  Reference: {source_config.repo_ref}")
        
        # Check for plugins-list.yaml
        plugins_list_file = self.config_dir / "plugins-list.yaml"
        
        if plugins_list_file.exists():
            self.logger.debug(f"Using plugin list file: {plugins_list_file}")
        else:
            self.logger.debug(f"plugins-list.yaml not found, will auto-generate after repository is available")
        return source_config
    
    def apply_patches_and_overlays(self) -> bool:
        """Apply patches and overlays using override-sources.sh script."""
        script_dir = Path(__file__).parent.parent.parent / "scripts"
        script_path = script_dir / "override-sources.sh"
        
        if not script_path.exists():
            self.logger.error(f"[red]Script not found: {script_path}[/red]")
            return False
        
        workspace_path = self.repo_path.joinpath(self.workspace_path).absolute()
        self.logger.debug(f"Applying patches and overlays to workspace: {workspace_path}")
        # Run override-sources.sh script
        cmd = [
            str(script_path),
            str(self.config_dir.absolute()),  # Overlay root directory
            str(workspace_path),     # Target directory 
        ]

        try:
            # Stream output in real-time
            # Use error logging for commands that patches and overlays
            returncode = run_command_with_streaming(
                cmd,
                self.logger,
                cwd=workspace_path,
                stderr_log_func=self.logger.error
            )
            
            if returncode == 0:
                self.logger.info("[green]Patches and overlays applied successfully[/green]")
                return True
            else:
                self.logger.error(f"[red]Patches/overlays failed with exit code {returncode}[/red]")
                return False
                
        except Exception as e:
            self.logger.error(f"[red]Failed to run patch script: {e}[/red]")
            return False
    
    def export_plugins(self, output_dir: Path, push_images: bool) -> bool:
        """Export plugins using export-workspace.sh script."""
        self.logger.info("[bold blue]Exporting plugins using RHDH CLI[/bold blue]")
        
        script_dir = Path(__file__).parent.parent.parent / "scripts"
        script_path = script_dir / "export-workspace.sh"
        
        if not script_path.exists():
            self.logger.error(f"[red]Script not found: {script_path}[/red]")
            return False
        
        plugins_list_file = self.config_dir / "plugins-list.yaml"
        
        if not plugins_list_file.exists():
            self.logger.error("[red]No plugins file found[/red]")
            return False    

        # Load config directory .env file for script variables
        config_env_file = self.config_dir / ".env"
        default_env_file = Path(__file__).parent.parent.parent / "default.env"
        load_dotenv(default_env_file)
        env = dict(os.environ)
        
        if config_env_file.exists():
            self.logger.debug(f"Loading script configuration from: {config_env_file}")
            load_dotenv(config_env_file, override=True)
            # Reload env after loading .env
            env = dict(os.environ)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        env["INPUTS_DESTINATION"] = str(output_dir)
        # Set required environment variables for the script
        env.update({
            "INPUTS_SCALPRUM_CONFIG_FILE_NAME": "scalprum-config.json",
            "INPUTS_SOURCE_OVERLAY_FOLDER_NAME": "overlay",
            "INPUTS_SOURCE_PATCH_FILE_NAME": "patch",
            "INPUTS_APP_CONFIG_FILE_NAME": "app-config.dynamic.yaml",
            "INPUTS_PLUGINS_FILE": str(plugins_list_file.absolute()),
            "INPUTS_CLI_PACKAGE": "@red-hat-developer-hub/cli",
            "INPUTS_PUSH_CONTAINER_IMAGE": "true" if push_images else "false",
            "INPUTS_JANUS_CLI_VERSION": self.rhdh_cli_version,
            "INPUTS_IMAGE_REPOSITORY_PREFIX": f"{self.registry_url or 'localhost'}/{self.registry_namespace or 'default'}",
            "INPUTS_DESTINATION": str(output_dir.absolute()),
            "INPUTS_CONTAINER_BUILD_TOOL": "buildah",
        })
        
        # Run export-workspace.sh script in the workspace directory
        workspace_path = self.repo_path.joinpath(self.workspace_path).absolute()
        try:
            # Stream output in real-time
            # Use error logging for export-workspace.sh script
            returncode = run_command_with_streaming(
                [str(script_path.absolute())],
                self.logger,
                cwd=workspace_path,
                env=env,
                stderr_log_func=self.logger.error
            )
            
            if returncode != 0:
                self.logger.error(f"[red]Plugin export script failed with exit code {returncode}[/red]")
                return False
            
            # Check if any plugins failed to export
            has_failures = display_export_results(workspace_path, self.logger)
            
            if has_failures:
                self.logger.error("[red]Plugin export completed with failures[/red]")
                return False
            else:
                self.logger.info("[green]Plugin export completed successfully[/green]")
                return True

        except Exception as e:
            self.logger.error(f"[red]Failed to run export script: {e}[/red]")
            return False


@dataclass
class SourceConfig:
    """Configuration for plugin source repository."""
    repo: str
    repo_ref: str
    
    logger = get_logger("source_config")

    @classmethod
    def from_file(cls, source_file: Path) -> "SourceConfig":
        """Load source configuration from JSON file."""
        # Load and parse JSON file
        try:
            with open(source_file, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            raise ValueError(f"Source configuration file not found: {source_file}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {source_file}: {e}")
        except Exception as e:
            raise ValueError(f"Failed to read {source_file}: {e}")

        # Extract and validate required fields
        try:
            repo = data["repo"]
            repo_ref = data.get("repo-ref")
        except KeyError as e:
            raise ValueError(f"Missing required field {e} in {source_file}")
        
        # Create config instance
        config = cls(
            repo=repo,
            repo_ref=repo_ref,
        )

        # Validate all required fields are set
        if not config.repo:
            raise ValueError("repo is required")
        if not config.repo_ref:
            raise ValueError("repo_ref is required")
        
        return config
    
    def clone_to_path(self, repo_path: Path) -> bool:
        """Clone the source repository to the specified path."""
        logger = get_logger("cli")
        
        if not repo_path.exists():
            self.logger.error(f"[red]Workspace does not exist: {repo_path}[/red]")
            return True
        
        self.logger.info(f"[bold blue]Cloning repository[/bold blue]")
        self.logger.info(f"Repository: {self.repo}")
        self.logger.info(f"Reference: {self.repo_ref}")
        self.logger.info(f"Workspace: {repo_path}")
            
        try:
            cmd = ["git", "clone", self.repo, str(repo_path)]
            # Git writes progress to stderr, so log it as info instead of error
            returncode = run_command_with_streaming(
                cmd,
                logger,
                stderr_log_func=logger.info
            )
            
            if returncode != 0:
                logger.error(f"Failed to clone repository (exit code {returncode})")
                return False
            
            # Checkout specific ref if provided
            if self.repo_ref:
                cmd = ["git", "checkout", self.repo_ref]
                logger.info(f"[cyan]Checking out ref: {self.repo_ref}[/cyan]")
                # Git writes informational messages to stderr
                returncode = run_command_with_streaming(
                    cmd,
                    logger,
                    cwd=repo_path,
                    stderr_log_func=logger.info
                )
                
                if returncode != 0:
                    logger.error(f"Failed to checkout ref {self.repo_ref} (exit code {returncode})")
                    return False
            
            logger.info("[green]Repository cloned successfully[/green]")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clone repository: {e}")
            return False

class PluginListConfig:
    """Configuration for plugin list (YAML format)."""
    
    def __init__(self, plugins: Dict[str, str]):
        """
        Initialize plugin list configuration.
        
        Args:
            plugins: Dictionary mapping plugin paths to build arguments
        """
        self.plugins = plugins
    
    @classmethod
    def from_file(cls, plugin_list_file: Path) -> "PluginListConfig":
        """Load plugin list from YAML file."""
        
        with open(plugin_list_file, 'r') as f:
            data = yaml.safe_load(f) or {}
            
        plugins = {}
        for key, value in data.items():
            if value is None:
                plugins[key] = ""
            else:
                plugins[key] = str(value)
        
        return cls(plugins)
    
    def to_file(self, plugin_list_file: Path) -> None:
        """Save plugin list to YAML file."""
        # TODO: Implement this function
        raise NotImplementedError("TODO: Saving plugin list to file is not supported yet")
    
    def get_plugins(self) -> Dict[str, str]:
        return self.plugins.copy()
    
    def add_plugin(self, plugin_path: str, build_args: str = "") -> None:
        self.plugins[plugin_path] = build_args
    
    def remove_plugin(self, plugin_path: str) -> None:
        self.plugins.pop(plugin_path, None)
    
    @classmethod
    def create_default(cls, workspace_path: Path) -> "PluginListConfig":
        """Create a default plugin list by scanning workspace."""
        # TODO: Implement this function
        raise NotImplementedError("TODO: default plugin list creation is not supported yet")

