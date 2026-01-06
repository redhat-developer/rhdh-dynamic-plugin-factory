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
import subprocess

from .logger import get_logger
from .utils import run_command_with_streaming, display_export_results

@dataclass
class PluginFactoryConfig:
    """Main configuration for the plugin factory."""
    
    # Required fields loaded from default.env file (can be overridden by environment variables)
    rhdh_cli_version: str = field(default="")
    
    repo_path: str = field(default="/source")  # Local path where plugin source code will be stored
    config_dir: str = field(default="/config")
    workspace_path: str = field(default="")  # Relative path from repo_path to the workspace
    
    # Registry configuration (loaded from environment variables, only required for push operations)
    registry_url: Optional[str] = field(default=None)
    registry_username: Optional[str] = field(default=None)
    registry_password: Optional[str] = field(default=None)
    registry_namespace: Optional[str] = field(default=None)
    registry_insecure: bool = field(default=False)

    log_level: str = field(default="INFO")
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
        
        config = cls()
        
        default_env_path = Path(__file__).parent.parent.parent / "default.env"
        
        config.logger.debug(f'[bold blue]Loading environment variables from {default_env_path}[/bold blue]')

        if default_env_path.exists():
            load_dotenv(default_env_path)
            config.logger.debug(f'[green]✓ Loaded {default_env_path}[/green]')
            
        if env_file and env_file.exists():
            load_dotenv(env_file, override=True)
            config.logger.debug(f'[green]✓ Loaded {env_file}[/green]')

        config.logger.debug('[bold blue]Loading configuration from environment variables and CLI arguments[/bold blue]')
        
        config.workspace_path = os.getenv("WORKSPACE_PATH", args.workspace_path)
        config.config_dir = args.config_dir
        config.repo_path = args.repo_path
        
        config.rhdh_cli_version = os.getenv("RHDH_CLI_VERSION", "")

        config.registry_url = os.getenv("REGISTRY_URL")
        config.registry_username = os.getenv("REGISTRY_USERNAME")
        config.registry_password = os.getenv("REGISTRY_PASSWORD")
        config.registry_namespace = os.getenv("REGISTRY_NAMESPACE")
        config.registry_insecure = os.getenv("REGISTRY_INSECURE", "false").lower() == "true"

        config.log_level = os.getenv("LOG_LEVEL", args.log_level)
        
        config.use_local = args.use_local
        
        dirs_to_create = [config.config_dir, config.repo_path]
        for dir_path in dirs_to_create:
            os.makedirs(dir_path, exist_ok=True)
        
        if not config.rhdh_cli_version:
            raise ValueError("RHDH_CLI_VERSION must be set (usually loaded from default.env)")
        
        if not config.workspace_path:
            raise ValueError("WORKSPACE_PATH must be set via environment variable or --workspace-path argument")
        
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if config.log_level.upper() not in valid_log_levels:
            raise ValueError(f"Invalid log level: {config.log_level}")
        
        config._validate_source_json()
        config._validate_plugins_list()
        
        return config
    
    def load_registry_config(self, push_images: bool = False) -> None:
        """
        Load registry configuration from environment variables and attempt buildah login.
        Only validates required registry fields if `push_images` is True.
        """
        # Only validate registry configuration if we're pushing images
        if not push_images:
            self.logger.info("Skipping registry configuration (not pushing images)")
            return
            
        if not self.registry_url:
            raise ValueError("REGISTRY_URL environment variable is required when --push-images is enabled")
        
        if not self.registry_namespace:
            raise ValueError("REGISTRY_NAMESPACE environment variable is required when --push-images is enabled")
        
        if not self.registry_username or not self.registry_password:
            raise ValueError("REGISTRY_USERNAME and REGISTRY_PASSWORD environment variables are required when --push-images is enabled")
        ## TODO: Add support for token logins for ghcr.io registry as well

        try:
            cmd = [
                "buildah", "login",
                "--username", str(self.registry_username),
                "--password", str(self.registry_password)
            ]
            
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
    
    def _validate_source_json(self) -> None:
        """Validate source.json file existence and repo_path state."""
        source_file = os.path.join(self.config_dir, "source.json")
        
        if not os.path.exists(source_file):
            if not os.path.exists(self.repo_path) or not os.listdir(self.repo_path):
                raise ValueError(
                    f"source.json not found at {source_file} and {self.repo_path} is empty. "
                    "Please provide source.json to clone a repository or use --use-local with a locally mounted repository."
                )
            else:
                self.logger.warning(
                    f"source.json not found at {source_file}. Will attempt to use local repository content at {self.repo_path}"
                )
        else:
            self.logger.debug(f"Using source configuration from: {source_file}")
    
    def _validate_plugins_list(self) -> None:
        """Validate plugins-list.yaml file existence."""
        plugins_file = os.path.join(self.config_dir, "plugins-list.yaml")
        
        if not os.path.exists(plugins_file):
            self.logger.warning(
                f"plugins-list.yaml not found at {plugins_file}. Will attempt to auto-generate after repository is available."
            )
        else:
            self.logger.debug(f"Using plugins-list.yaml from: {plugins_file}")
    
    def auto_generate_plugins_list(self) -> bool:
        """
        Auto-generate plugins-list.yaml
        Assumes the following:
        - The repository is cloned to the `repo_path`
        - The plugins are located in the plugins/* directory
        - `workspace_path` is the path to the workspace from the root of the repository
        """
        plugins_file = os.path.join(self.config_dir, "plugins-list.yaml")
        
        if os.path.exists(plugins_file):
            self.logger.debug(f"[green]✓ plugins-list.yaml already exists at {plugins_file}. Skipping auto-generation.[/green]")
            return True
        
        self.logger.info("[bold blue]Auto-generating plugins-list.yaml[/bold blue]")
        
        try:
            if not os.path.exists(self.repo_path):
                self.logger.error(f"[red]Repository does not exist at {self.repo_path}[/red]")
                return False
            workspace_full_path = os.path.abspath(os.path.join(self.repo_path, self.workspace_path))
            if not os.path.exists(workspace_full_path):
                self.logger.error(f"[red]Workspace does not exist at {workspace_full_path}[/red]")
                return False
            
            # TODO: Implement PluginListConfig.create_default function
            plugin_cfg = PluginListConfig.create_default(workspace_path=Path(workspace_full_path))
            plugin_cfg.to_file(Path(plugins_file))
            
            plugins = plugin_cfg.get_plugins()
            if plugins:
                self.logger.info(f"Generated plugins-list.yaml with {len(plugins)} plugins")
                for plugin_path, build_args in plugins.items():
                    self.logger.info(f"  - {plugin_path}: {build_args}")
            else:
                self.logger.warning("No plugins found in workspace")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to auto-generate plugins list: {e}")
            return False
    
    def discover_source_config(self) -> Optional["SourceConfig"]:
        """Discovers and loads source configuration from config_dir/source.json."""
        source_file = os.path.join(self.config_dir, "source.json")

        if os.path.exists(source_file) and not self.use_local:
            try:
                source_config = SourceConfig.from_file(Path(source_file))
                self.logger.debug(f"Using source config from: {source_config}")
                return source_config
            except Exception as e:
                self.logger.error(f"[red]Failed to load {source_file}: {e}[/red]")
                sys.exit(1)
        elif self.repo_path and os.path.exists(self.repo_path):
            self.logger.warning("Source configuration not found, will attempt to use locally stored plugin source code")
        else:
            self.logger.error(
                f"[red]No valid source configuration found and {self.repo_path} is empty or does not exist[/red]"
                f"Either provide a valid {source_file} or ensure locally stored plugin source code exists at {self.repo_path}"
            )
            sys.exit(1)
        return None
    
    
    def setup_config_directory(self) -> Optional["SourceConfig"]:
        """Setup and validate configuration directory structure."""
        self.logger.info("[bold blue]Setting up configuration directory[/bold blue]")
        
        os.makedirs(self.config_dir, exist_ok=True)
        
        env_file = os.path.join(self.config_dir, ".env")
        if os.path.exists(env_file):
            load_dotenv(env_file, override=True)
            self.logger.debug(f"Loaded .env file: {env_file}")
        
        source_config = self.discover_source_config()
        if source_config:
            self.logger.info("Found source configuration")
            self.logger.info(f"  Repository: {source_config.repo}")
            self.logger.info(f"  Reference: {source_config.repo_ref}")
        
        plugins_list_file = os.path.join(self.config_dir, "plugins-list.yaml")
        
        if os.path.exists(plugins_list_file):
            self.logger.info(f"Using plugin list file: {plugins_list_file}")
            with open(plugins_list_file, 'r') as f:
                plugins_yaml = yaml.dump(yaml.safe_load(f), indent=2)
            indented_plugins_yaml = "\n".join("  " + line if line.strip() != "" else line for line in plugins_yaml.splitlines())
            self.logger.info(f"Plugins:\n{indented_plugins_yaml}")
        else:
            self.logger.warning(f"{plugins_list_file} not found, will auto-generate after repository is available")
        return source_config
    
    def apply_patches_and_overlays(self) -> bool:
        """Apply patches and overlays using override-sources.sh script."""
        script_dir = Path(__file__).parent.parent.parent / "scripts"
        script_path = script_dir / "override-sources.sh"
        
        if not script_path.exists():
            self.logger.error(f"[red]Script not found: {script_path}[/red]")
            return False
        
        workspace_full_path = os.path.abspath(os.path.join(self.repo_path, self.workspace_path))
        self.logger.debug(f"Applying patches and overlays to workspace: {workspace_full_path}")
        cmd = [
            str(script_path.absolute()),
            os.path.abspath(self.config_dir),  # Overlay root directory
            workspace_full_path,     # Target directory 
        ]

        try:
            returncode = run_command_with_streaming(
                cmd,
                self.logger,
                cwd=Path(workspace_full_path),
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
    
    def export_plugins(self, output_dir: str, push_images: bool) -> bool:
        """Export plugins using export-workspace.sh script."""        
        script_dir = Path(__file__).parent.parent.parent / "scripts"
        script_path = script_dir / "export-workspace.sh"
        
        if not script_path.exists():
            self.logger.error(f"[red]Script not found: {script_path}[/red]")
            return False
        
        plugins_list_file = os.path.join(self.config_dir, "plugins-list.yaml")
        
        if not os.path.exists(plugins_list_file):
            self.logger.error("[red]No plugins file found[/red]")
            return False    

        config_env_file = os.path.join(self.config_dir, ".env")
        default_env_file = Path(__file__).parent.parent.parent / "default.env"
        load_dotenv(default_env_file)
        env = dict(os.environ)
        
        if os.path.exists(config_env_file):
            self.logger.debug(f"Loading script configuration from: {config_env_file}")
            load_dotenv(config_env_file, override=True)
            # Reload env after loading .env
            env = dict(os.environ)
        
        os.makedirs(output_dir, exist_ok=True)
        env["INPUTS_DESTINATION"] = output_dir
        env.update({
            "INPUTS_SCALPRUM_CONFIG_FILE_NAME": "scalprum-config.json",
            "INPUTS_SOURCE_OVERLAY_FOLDER_NAME": "overlay",
            "INPUTS_SOURCE_PATCH_FILE_NAME": "patch",
            "INPUTS_APP_CONFIG_FILE_NAME": "app-config.dynamic.yaml",
            "INPUTS_PLUGINS_FILE": os.path.abspath(plugins_list_file),
            "INPUTS_CLI_PACKAGE": "@red-hat-developer-hub/cli",
            "INPUTS_PUSH_CONTAINER_IMAGE": "true" if push_images else "false",
            "INPUTS_JANUS_CLI_VERSION": self.rhdh_cli_version,
            "INPUTS_IMAGE_REPOSITORY_PREFIX": f"{self.registry_url or 'localhost'}/{self.registry_namespace or 'default'}",
            "INPUTS_DESTINATION": os.path.abspath(output_dir),
            "INPUTS_CONTAINER_BUILD_TOOL": "buildah",
        })
        
        workspace_full_path = os.path.abspath(os.path.join(self.repo_path, self.workspace_path))
        try:
            def conditional_stderr_log(line: str) -> None:
                if "Error" in line:
                    self.logger.error(line)
                if "npm warn" in line:
                    self.logger.warning(line)
                else:
                    self.logger.info(line)
            
            returncode = run_command_with_streaming(
                [str(script_path.absolute())],
                self.logger,
                cwd=Path(workspace_full_path),
                env=env,
                stderr_log_func=conditional_stderr_log
            )
            
            if returncode != 0:
                self.logger.error(f"[red]Plugin export script failed with exit code {returncode}[/red]")
                return False
            
            has_failures = display_export_results(Path(workspace_full_path), self.logger)
            
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
        try:
            with open(source_file, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            raise ValueError(f"Source configuration file not found: {source_file}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {source_file}: {e}")
        except Exception as e:
            raise ValueError(f"Failed to read {source_file}: {e}")

        try:
            repo = data["repo"]
            repo_ref = data.get("repo-ref")
        except KeyError as e:
            raise ValueError(f"Missing required field {e} in {source_file}")
        
        config = cls(
            repo=repo,
            repo_ref=repo_ref,
        )

        if not config.repo:
            raise ValueError("repo is required")
        if not config.repo_ref:
            raise ValueError("repo_ref is required")
        
        return config
    
    def clone_to_path(self, repo_path: Path) -> bool:
        """Clone the source repository to the specified path."""
        logger = get_logger("cli")
        
        if not repo_path.exists():
            self.logger.error(f"[red]Destination directory does not exist: {repo_path}[/red]")
            return True
        
        self.logger.info(f"[bold blue]Cloning repository[/bold blue]")
        self.logger.info(f"Repository: {self.repo}")
        self.logger.info(f"Reference: {self.repo_ref}")
        self.logger.info(f"Destination directory: {repo_path}")
            
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
            
            logger.info("[green]✓ Repository cloned successfully[/green]")
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

