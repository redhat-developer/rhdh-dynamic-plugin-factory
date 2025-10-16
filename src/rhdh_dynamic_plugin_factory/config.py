"""
Configuration management for RHDH Plugin Factory.
"""

import argparse
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv
import yaml
import json
from .logger import get_logger

@dataclass
class PluginFactoryConfig:
    """Main configuration for the plugin factory."""
    
    # Required fields loaded from default.env file (can be overridden by environment variables)
    node_version: str = field(default="")
    yarn_version: str = field(default="") 
    rhdh_cli_version: str = field(default="")
    
    # Directories
    repo_path: str = field(default="/workspace")  # Local path where plugin source code will be stored
    config_dir: Path = field(default_factory=lambda: Path("config"))
    workspace_path: Path = field(default_factory=lambda: Path("workspace"))
    
    # Registry configuration (loaded from environment variables, only required for push operations)
    registry_url: Optional[str] = field(default=None)
    registry_username: Optional[str] = field(default=None)
    registry_password: Optional[str] = field(default=None)
    registry_namespace: Optional[str] = field(default=None)
    registry_insecure: bool = field(default=False)

    # Logging
    log_level: str = field(default="INFO")

    logger = get_logger("config")
    @classmethod
    def load_from_env(cls, args: argparse.Namespace, env_file: Optional[Path] = None) -> "PluginFactoryConfig":
        """Load configuration from environment variables and .env files.
        
        Loads default.env first, then optionally loads additional env file to override defaults or provide additional values.
        Environment variables take precedence over .env file values.
        
        Args:
            env_file: Optional additional .env file to merge with defaults
        """
        
        # First, load default.env if it exists
        default_env_path = Path(__file__).parent.parent.parent / "default.env"
        if default_env_path.exists():
            load_dotenv(default_env_path)
        
        # Then load additional env file if specified and exists
        if env_file and env_file.exists():
            load_dotenv(env_file, override=True)
        elif Path(".env").exists():
            load_dotenv(override=True)
        
        # Create config with environment overrides
        config = cls()
        

        config.workspace_path = Path(os.getenv("WORKSPACE_PATH", args.workspace_path or config.workspace_path))
        config.config_dir = Path(os.getenv("CONFIG_DIR", args.config_dir))
        config.repo_path = Path(os.getenv("REPO_PATH", args.repo_path))
        
        # Load version defaults from environment (set by default.env)
        config.node_version = os.getenv("NODE_VERSION")
        config.yarn_version = os.getenv("YARN_VERSION")
        config.rhdh_cli_version = os.getenv("RHDH_CLI_VERSION")

        # Load registry configuration from environment variables
        config.registry_url = os.getenv("REGISTRY_URL")
        config.registry_username = os.getenv("REGISTRY_USERNAME")
        config.registry_password = os.getenv("REGISTRY_PASSWORD")
        config.registry_namespace = os.getenv("REGISTRY_NAMESPACE")
        config.registry_insecure = os.getenv("REGISTRY_INSECURE", "false").lower() == "true"

        config.log_level = os.getenv("LOG_LEVEL", config.log_level)
        
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

    def get_registry_info(self) -> Optional[dict]:
        """Get current registry configuration if available."""
        if not self.registry_url or not self.registry_namespace:
            return None
        return {
            "registry": self.registry_url,
            "namespace": self.registry_namespace,
            "insecure": self.registry_insecure
        }
    
    def validate(self) -> None:
        """Validate configuration."""
        # Ensure required directories exist or can be created
        dirs_to_create = [self.config_dir, self.repo_path]
        
        for dir_path in dirs_to_create:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # TODO: Validate `source.json` file if it exists
        # TODO: Validate `plugins-list.yaml` file if it exists
        
        # Validate required configuration
        if not self.node_version:
            raise ValueError("NODE_VERSION must be set (usually loaded from default.env)")
        if not self.yarn_version:
            raise ValueError("YARN_VERSION must be set (usually loaded from default.env)")
        if not self.rhdh_cli_version:
            raise ValueError("RHDH_CLI_VERSION must be set (usually loaded from default.env)")
            
        # Validate log level
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level.upper() not in valid_log_levels:
            raise ValueError(f"Invalid log level: {self.log_level}")


@dataclass
class SourceConfig:
    """Configuration for plugin source repository."""
    repo: str
    repo_backstage_version: str
    repo_ref: Optional[str] = None
    repo_flat: bool = False    
    
    logger = get_logger("source_config")

    @classmethod
    def from_file(cls, source_file: Path) -> "SourceConfig":
        """Load source configuration from JSON file."""
        try:
            with open(source_file, 'r') as f:
                data = json.load(f)
        
        except Exception as e:
            raise ValueError(f"Failed to load source configuration from {source_file}: {e}")

        config = cls(
            repo=data["repo"],
            repo_ref=data.get("repo-ref"),
            repo_flat=data.get("repo-flat", False),
            repo_backstage_version=data.get("repo-backstage-version")
        )

        # Validate all fields are set
        if not config.repo or not config.repo_backstage_version or not config.repo_ref:
            raise ValueError("repo, repo_backstage_version, and repo_ref are required")
        return config
    
    def get_repo_owner_and_name(self) -> str:
        """Extract owner/repo format from GitHub URL."""
        if self.repo.startswith("https://github.com/"):
            return self.repo.replace("https://github.com/", "")
        elif self.repo.startswith("http://github.com/"):
            return self.repo.replace("http://github.com/", "")
        elif self.repo.startswith("git@github.com:"):
            return self.repo.replace("git@github.com:", "").replace(".git", "")
        else:
            # Assume it's already in owner/repo format
            return self.repo
    
    def get_repo_url(self) -> str:
        """Get the full repository URL."""
        if self.repo.startswith("http"):
            return self.repo
        elif "/" in self.repo and not self.repo.startswith("git@"):
            # Convert owner/repo to GitHub URL
            return f"https://github.com/{self.repo}"
        else:
            return self.repo
    
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
        
        plugin_list_file.parent.mkdir(parents=True, exist_ok=True)
        with open(plugin_list_file, 'w') as f:
            # Write header comment
            f.write("# Plugin list for RHDH Dynamic Plugin Factory\n")
            f.write("# Format: plugin_path: [additional_args]\n")
            f.write("# Example:\n")
            f.write("# plugins/my-plugin:\n")
            f.write("# plugins/my-backend: --embed-package @some/package\n\n")
            
            # Convert to YAML format
            yaml_data = {}
            for plugin_path, args in self.plugins.items():
                if args.strip():
                    yaml_data[plugin_path] = args
                else:
                    yaml_data[plugin_path] = None
            
            yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=True)
    
    def get_plugins(self) -> Dict[str, str]:
        return self.plugins.copy()
    
    def add_plugin(self, plugin_path: str, build_args: str = "") -> None:
        self.plugins[plugin_path] = build_args
    
    def remove_plugin(self, plugin_path: str) -> None:
        self.plugins.pop(plugin_path, None)
    
    @classmethod
    def create_default(cls, workspace_dir: Path) -> "PluginListConfig":
        """Create a default plugin list by scanning workspace."""
        raise NotImplementedError("TODO: This function is not implemented")

        plugins = {}
        
        # Look for common plugin patterns
        if workspace_dir.exists():
            # Look for plugins/ directory
            plugins_dir = workspace_dir / "plugins"
            if plugins_dir.exists():
                for plugin_dir in plugins_dir.iterdir():
                    if plugin_dir.is_dir() and (plugin_dir / "package.json").exists():
                        plugins[f"plugins/{plugin_dir.name}"] = ""
            
            # Look for workspaces in package.json
            package_json = workspace_dir / "package.json"
            if package_json.exists():
                try:
                    with open(package_json, 'r') as f:
                        package_data = json.load(f)
                    
                    workspaces = package_data.get("workspaces", [])
                    for workspace in workspaces:
                        # Handle glob patterns (simplified)
                        if "*" in workspace:
                            workspace_base = workspace.replace("/*", "")
                            workspace_path = workspace_dir / workspace_base
                            if workspace_path.exists():
                                for plugin_dir in workspace_path.iterdir():
                                    if plugin_dir.is_dir() and (plugin_dir / "package.json").exists():
                                        plugins[f"{workspace_base}/{plugin_dir.name}"] = ""
                        else:
                            workspace_path = workspace_dir / workspace
                            if workspace_path.exists() and (workspace_path / "package.json").exists():
                                plugins[workspace] = ""
                                
                except Exception:
                    pass  # Ignore errors in package.json parsing
        
        return cls(plugins)

