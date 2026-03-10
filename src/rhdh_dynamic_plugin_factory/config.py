"""
Configuration management for RHDH Plugin Factory.
"""

import argparse
from logging import Logger
import os
from pathlib import Path
import re
from typing import Dict, Optional, ClassVar
from dataclasses import dataclass, field
from dotenv import load_dotenv
import yaml
import json
import subprocess

from .exceptions import PluginFactoryError, ConfigurationError, ExecutionError
from .logger import get_logger
from .utils import run_command_with_streaming, display_export_results, prompt_or_clean_directory, repo_dir_name

@dataclass
class PluginFactoryConfig:
    """Main configuration for the plugin factory."""
    PLUGIN_LIST_FILE: ClassVar[str] = "plugins-list.yaml"
    SOURCE_CONFIG_FILE: ClassVar[str] = "source.json"
    
    # Required fields loaded from default.env file (can be overridden by environment variables)
    rhdh_cli_version: str = field(default="")
    
    repo_path: str = field(default="/source")  # Local path where plugin source code will be stored
    config_dir: str = field(default="/config")
    workspace_path: str = field(default="")  # Relative path from repo_path to the workspace
    
    # Source repository CLI overrides (take precedence over source.json)
    # Used for single workspace case
    source_repo: Optional[str] = field(default=None)
    source_ref: Optional[str] = field(default=None)
    
    # Registry configuration (loaded from environment variables, only required for push operations)
    registry_url: Optional[str] = field(default=None)
    registry_username: Optional[str] = field(default=None)
    registry_password: Optional[str] = field(default=None)
    registry_namespace: Optional[str] = field(default=None)
    registry_insecure: bool = field(default=False)

    use_local: bool = field(default=False)
    push_images: bool = field(default=False)

    logger: ClassVar[Logger] = get_logger("config")
    
    def __post_init__(self) -> None:
        """Validate configuration fields after initialization.
        
        Note: workspace_path is NOT validated here because it may be resolved
        later from source.json. Validation happens in cli._run() after source
        configuration discovery.
        """
        if not self.rhdh_cli_version:
            raise ConfigurationError("RHDH_CLI_VERSION must be set (usually loaded from default.env)")
        
        # Validate source arg constraints: --source-ref requires --source-repo
        if self.source_ref and not self.source_repo:
            raise ConfigurationError("--source-ref requires --source-repo to be provided")
        
        if self.push_images:
            self._validate_registry_fields()
    
    def _validate_registry_fields(self) -> None:
        """Validate that all required registry fields are present.
        
        Raises:
            ConfigurationError: If any required registry field is missing.
        """
        if not self.registry_url:
            raise ConfigurationError("REGISTRY_URL environment variable is required when --push-images is enabled")
        if not self.registry_namespace:
            raise ConfigurationError("REGISTRY_NAMESPACE environment variable is required when --push-images is enabled")
        if not self.registry_username or not self.registry_password:
            raise ConfigurationError("REGISTRY_USERNAME and REGISTRY_PASSWORD environment variables are required when --push-images is enabled")
    
    def refresh_registry_config(self) -> None:
        """Re-read registry fields from os.environ and re-login if credentials changed.
        
        Called per workspace in multi-workspace mode after loading workspace-specific
        .env files so that each workspace can target a different registry.
        
        Raises:
            ConfigurationError: If push_images is enabled and required registry fields are missing.
            ExecutionError: If buildah login fails after credential change.
        """
        new_url = os.getenv("REGISTRY_URL")
        new_username = os.getenv("REGISTRY_USERNAME")
        new_password = os.getenv("REGISTRY_PASSWORD")
        new_namespace = os.getenv("REGISTRY_NAMESPACE")
        new_insecure = os.getenv("REGISTRY_INSECURE", "false").lower() == "true"
        
        creds_changed = (
            new_url != self.registry_url
            or new_username != self.registry_username
            or new_password != self.registry_password
            or new_insecure != self.registry_insecure
        )
        
        self.registry_url = new_url
        self.registry_username = new_username
        self.registry_password = new_password
        self.registry_namespace = new_namespace
        self.registry_insecure = new_insecure
        
        if self.push_images and creds_changed:
            self._validate_registry_fields()
            self._buildah_login()

    @classmethod
    def load_from_env(cls, args: argparse.Namespace, env_file: Optional[Path] = None,
                      push_images: bool = False, multi_workspace: bool = False) -> "PluginFactoryConfig":
        """Load configuration from environment variables and .env files.
        
        Loads default.env first, then optionally loads additional env file to override defaults or provide additional values.
        Environment variables take precedence over .env file values.
        
        Args:
            args: Parsed CLI arguments.
            env_file: Optional additional .env file to merge with defaults.
            push_images: Whether to push images to a registry (triggers registry validation and login).
            multi_workspace: If True, skip root-level source.json and plugins-list.yaml
                validation since each workspace manages its own.
        """
        default_env_path = Path(__file__).parent.parent.parent / "default.env"
        
        cls.logger.debug(f'[bold blue]Loading environment variables from {default_env_path}[/bold blue]')

        if default_env_path.exists():
            load_dotenv(default_env_path)
            cls.logger.debug(f'[green]Loaded {default_env_path}[/green]')
            
        if env_file and env_file.exists():
            load_dotenv(env_file, override=True)
            cls.logger.debug(f'[green]Loaded {env_file}[/green]')

        cls.logger.debug('[bold blue]Loading configuration from environment variables and CLI arguments[/bold blue]')
        
        config_dir = args.config_dir
        repo_path = args.repo_path
        
        # Ensure required directories exist before constructing config
        for dir_path in [config_dir, repo_path]:
            os.makedirs(dir_path, exist_ok=True)
        
        workspace_path = getattr(args, 'workspace_path', None)
        
        source_repo = getattr(args, 'source_repo', None)
        source_ref = getattr(args, 'source_ref', None)
        
        config = cls(
            rhdh_cli_version=os.getenv("RHDH_CLI_VERSION", ""),
            repo_path=repo_path,
            config_dir=config_dir,
            workspace_path=workspace_path or "",
            source_repo=source_repo,
            source_ref=source_ref,
            registry_url=os.getenv("REGISTRY_URL"),
            registry_username=os.getenv("REGISTRY_USERNAME"),
            registry_password=os.getenv("REGISTRY_PASSWORD"),
            registry_namespace=os.getenv("REGISTRY_NAMESPACE"),
            registry_insecure=os.getenv("REGISTRY_INSECURE", "false").lower() == "true",
            use_local=args.use_local,
            push_images=push_images,
        )
        
        if not multi_workspace:
            config._validate_source_json()
            config._validate_plugins_list()
        
        if push_images:
            config._buildah_login()
        
        return config
    
    def _buildah_login(self) -> None:
        """Login to the container registry using buildah.
        
        Assumes registry fields have already been validated by __post_init__.
        
        Raises:
            ExecutionError: If the buildah login command fails.
        """
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
            raise ExecutionError(
                f"Failed to login to registry {self.registry_url} with buildah: {e.stderr.decode().strip()}",
                step="buildah login",
                returncode=e.returncode,
            ) from e
    
    def _validate_source_json(self) -> None:
        """Validate source.json file existence and repo_path state.
        
        Skips validation when --source-repo CLI arg is provided, since
        CLI args fully replace source.json.
        """
        if self.source_repo:
            self.logger.debug(f"Using --source-repo CLI argument, skipping {self.SOURCE_CONFIG_FILE} validation")
            return
        
        source_file = os.path.join(self.config_dir, self.SOURCE_CONFIG_FILE)
        
        if not os.path.exists(source_file):
            if not os.path.exists(self.repo_path) or not os.listdir(self.repo_path):
                raise ConfigurationError(
                    f"{self.SOURCE_CONFIG_FILE} not found at {source_file} and {self.repo_path} is empty. "
                    "Please provide {self.SOURCE_CONFIG_FILE} to clone a repository, use --source-repo to specify a repository via CLI, "
                    "or use --use-local with a locally mounted repository."
                )
            else:
                self.logger.warning(
                    f"{self.SOURCE_CONFIG_FILE} not found at {source_file}. Will attempt to use local repository content at {self.repo_path}"
                )
        else:
            self.logger.debug(f"Using source configuration from: {source_file}")
    
    def _validate_plugins_list(self) -> None:
        """Validate plugins-list.yaml file existence."""
        plugins_file = os.path.join(self.config_dir, self.PLUGIN_LIST_FILE)
        
        if not os.path.exists(plugins_file):
            self.logger.warning(
                f"{self.PLUGIN_LIST_FILE} not found at {plugins_file}. Will attempt to auto-generate after repository is available."
            )
        else:
            self.logger.debug(f"Using {self.PLUGIN_LIST_FILE} from: {plugins_file}")
    
    def auto_generate_plugins_list(self, config_dir: Optional[str] = None,
                                    repo_path: Optional[str] = None,
                                    workspace_path: Optional[str] = None) -> None:
        """Auto-generate plugins-list.yaml if it doesn't already exist.

        Args:
            config_dir: Config directory containing plugins-list.yaml. Defaults to self.config_dir.
            repo_path: Repository path. Defaults to self.repo_path.
            workspace_path: Workspace path relative to repo. Defaults to self.workspace_path.

        Raises:
            PluginFactoryError: If auto-generation fails.
        """
        config_dir = config_dir or self.config_dir
        repo_path = repo_path or self.repo_path
        workspace_path = workspace_path or self.workspace_path
        
        plugins_file = os.path.join(config_dir, self.PLUGIN_LIST_FILE)
        
        if os.path.exists(plugins_file):
            self.logger.debug(f"[green]{self.PLUGIN_LIST_FILE} already exists at {plugins_file}. Skipping auto-generation.[/green]")
            return
        
        self.logger.info(f"[bold blue]Auto-generating {self.PLUGIN_LIST_FILE}[/bold blue]")
        
        if not os.path.exists(repo_path):
            raise PluginFactoryError(f"Source code repository does not exist at {repo_path}")

        workspace_full_path = os.path.abspath(os.path.join(repo_path, workspace_path))
        if not os.path.exists(workspace_full_path):
            raise PluginFactoryError(f"Plugin workspace does not exist at {workspace_full_path}")
        
        try:
            plugin_cfg = PluginListConfig.create_default(workspace_path=Path(workspace_full_path))
            plugin_cfg.to_file(Path(plugins_file))
            
            plugins: Dict[str, str] = plugin_cfg.get_plugins()
            if plugins:
                self.logger.info(f"Generated {self.PLUGIN_LIST_FILE} with {len(plugins)} plugin(s)")
                for plugin_path, build_args in plugins.items():
                    if build_args:
                        self.logger.info(f"  - {plugin_path}: {build_args}")
                    else:
                        self.logger.info(f"  - {plugin_path}")
            else:
                self.logger.warning("No plugins found in workspace")
        except PluginFactoryError:
            raise
        except Exception as e:
            raise PluginFactoryError(f"Failed to auto-generate plugins list: {e}") from e
    
    def discover_source_config(self) -> Optional["SourceConfig"]:
        """Discovers and loads source configuration.

        CLI args (--source-repo/--source-ref) take precedence over source.json.
        Falls back to local repo if no source configuration is available.

        Returns:
            SourceConfig if source is configured, None if falling back to local repo.

        Raises:
            ConfigurationError: If source configuration is invalid or no valid source is available.
        """
        # CLI args take precedence over source.json
        if self.source_repo and not self.use_local:
            self.logger.info("Using source configuration from CLI arguments")
            source_config = SourceConfig.from_cli_args(
                repo=self.source_repo,
                repo_ref=self.source_ref,
                workspace_path=self.workspace_path,
            )
            self.logger.debug(f"Using source config from CLI: {source_config}")
            return source_config
        
        source_file = os.path.join(self.config_dir, self.SOURCE_CONFIG_FILE)

        if os.path.exists(source_file) and not self.use_local:
            # SourceConfig.from_file() raises ConfigurationError on failure, so let it propagate to cli.py
            source_config = SourceConfig.from_file(Path(source_file))
            self.logger.debug(f"Using source config from: {source_config}")
            return source_config
        elif self.repo_path and os.path.exists(self.repo_path):
            self.logger.warning("Source configuration not found, will attempt to use locally stored plugin source code")
        else:
            raise ConfigurationError(
                f"No valid source configuration found and {self.repo_path} is empty or does not exist. "
                f"Either provide a valid {source_file}, use --source-repo to specify a repository via CLI, "
                f"or ensure locally stored plugin source code exists at {self.repo_path}"
            )
        return None
    
    
    def setup_config_directory(self) -> Optional["SourceConfig"]:
        """Setup and validate configuration directory structure."""
        self.logger.info("[bold blue]Setting up configuration directory[/bold blue]")
        
        os.makedirs(self.config_dir, exist_ok=True)
        
        env_file = os.path.join(self.config_dir, ".env")
        if os.path.exists(env_file):
            load_dotenv(env_file, override=True)
            self.logger.debug(f"Loaded .env file: {env_file}")
        
        source_config: Optional["SourceConfig"] = self.discover_source_config()
        if source_config:
            self.logger.info("Found source configuration")
            self.logger.info(f"  Repository: {source_config.repo}")
            self.logger.info(f"  Reference: {source_config.repo_ref}")
        
        plugins_list_file = os.path.join(self.config_dir, self.PLUGIN_LIST_FILE)
        
        if os.path.exists(plugins_list_file):
            self.logger.info(f"Using plugin list file: {plugins_list_file}")
            with open(plugins_list_file, 'r') as f:
                plugins_yaml = yaml.dump(yaml.safe_load(f), indent=2)
            indented_plugins_yaml = "\n".join("  " + line if line.strip() != "" else line for line in plugins_yaml.splitlines())
            self.logger.info(f"Plugins:\n{indented_plugins_yaml}")
        else:
            self.logger.warning(f"{plugins_list_file} not found, will auto-generate after repository is available")
        return source_config
    
    def apply_patches_and_overlays(self, config_dir: Optional[str] = None,
                                    repo_path: Optional[str] = None,
                                    workspace_path: Optional[str] = None) -> None:
        """Apply patches and overlays using override-sources.sh script.

        Args:
            config_dir: Config directory containing patches/ and overlays. Defaults to self.config_dir.
            repo_path: Repository root path (worktree root in multi-workspace mode). Defaults to self.repo_path.
            workspace_path: Workspace path relative to repo_path. Defaults to self.workspace_path.

        Raises:
            ExecutionError: If the patch script is not found or fails.
        """
        config_dir = config_dir or self.config_dir
        repo_path = repo_path or self.repo_path
        workspace_path = workspace_path or self.workspace_path

        script_dir = Path(__file__).parent.parent.parent / "scripts"
        script_path = script_dir / "override-sources.sh"
        STEP_NAME = "apply patches and overlays"

        if not script_path.exists():
            raise ExecutionError(
                f"Script not found: {script_path}",
                step=STEP_NAME
            )

        repo_root = os.path.abspath(repo_path)
        workspace_full_path = os.path.abspath(os.path.join(repo_path, workspace_path))
        self.logger.debug(f"Applying patches at repo root: {repo_root}")
        self.logger.debug(f"Applying overlays to workspace: {workspace_full_path}")
        cmd = [
            str(script_path.absolute()),
            os.path.abspath(config_dir),
            workspace_full_path,
        ]

        try:
            returncode = run_command_with_streaming(
                cmd,
                self.logger,
                cwd=Path(repo_root),
                stderr_log_func=self.logger.error
            )

            if returncode == 0:
                self.logger.info("[green]Patches and overlays applied successfully[/green]")
            else:
                raise ExecutionError(
                    f"Patches/overlays failed with exit code {returncode}",
                    step=STEP_NAME,
                    returncode=returncode
                )
        except ExecutionError:
            raise
        except Exception as e:
            raise ExecutionError(
                f"Failed to run patch script: {e}",
                step=STEP_NAME
            ) from e
    
    def export_plugins(self, output_dir: str, config_dir: Optional[str] = None,
                        repo_path: Optional[str] = None,
                        workspace_path: Optional[str] = None) -> None:
        """Export plugins using export-workspace.sh script.

        Args:
            output_dir: Directory for build artifacts.
            config_dir: Config directory containing plugins-list.yaml and .env. Defaults to self.config_dir.
            repo_path: Repository path. Defaults to self.repo_path.
            workspace_path: Workspace path relative to repo. Defaults to self.workspace_path.

        Raises:
            ExecutionError: If the export script is not found or fails.
            ConfigurationError: If no plugins list file is found.
        """
        config_dir = config_dir or self.config_dir
        repo_path = repo_path or self.repo_path
        workspace_path = workspace_path or self.workspace_path
        
        script_dir = Path(__file__).parent.parent.parent / "scripts"
        script_path = script_dir / "export-workspace.sh"
        STEP_NAME = "export plugins"
        
        if not script_path.exists():
            raise ExecutionError(
                f"Script not found: {script_path}",
                step=STEP_NAME
            )
        
        plugins_list_file = os.path.join(config_dir, self.PLUGIN_LIST_FILE)
        
        if not os.path.exists(plugins_list_file):
            raise ConfigurationError("No plugins file found")

        config_env_file = os.path.join(config_dir, ".env")
        default_env_file = Path(__file__).parent.parent.parent / "default.env"
        load_dotenv(default_env_file)
        env = dict[str, str](os.environ)
        
        if os.path.exists(config_env_file):
            self.logger.debug(f"Loading script configuration from: {config_env_file}")
            load_dotenv(config_env_file, override=True)
            env = dict[str, str](os.environ)
        
        os.makedirs(output_dir, exist_ok=True)
        env["INPUTS_DESTINATION"] = output_dir
        env.update({
            "INPUTS_SCALPRUM_CONFIG_FILE_NAME": "scalprum-config.json",
            "INPUTS_SOURCE_OVERLAY_FOLDER_NAME": "overlay",
            "INPUTS_SOURCE_PATCH_FILE_NAME": "patch",
            "INPUTS_APP_CONFIG_FILE_NAME": "app-config.dynamic.yaml",
            "INPUTS_PLUGINS_FILE": os.path.abspath(plugins_list_file),
            "INPUTS_CLI_PACKAGE": "@red-hat-developer-hub/cli",
            "INPUTS_PUSH_CONTAINER_IMAGE": "true" if self.push_images else "false",
            "INPUTS_JANUS_CLI_VERSION": self.rhdh_cli_version,
            "INPUTS_IMAGE_REPOSITORY_PREFIX": f"{self.registry_url or 'localhost'}/{self.registry_namespace or 'default'}",
            "INPUTS_DESTINATION": os.path.abspath(output_dir),
            "INPUTS_CONTAINER_BUILD_TOOL": "buildah",
        })
        
        workspace_full_path = os.path.abspath(os.path.join(repo_path, workspace_path))
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
                raise ExecutionError(
                    f"Plugin export script failed with exit code {returncode}",
                    step=STEP_NAME,
                    returncode=returncode
                )
            
            has_failures = display_export_results(Path(workspace_full_path), self.logger)
            
            if has_failures:
                raise ExecutionError(
                    "Plugin export completed with failures",
                    step=STEP_NAME,
                )

            self.logger.info("[green]Plugin export completed successfully[/green]")

        except ExecutionError:
            raise
        except Exception as e:
            raise ExecutionError(
                f"Failed to run export script: {e}",
                step=STEP_NAME,
            ) from e


@dataclass
class SourceConfig:
    """Configuration for plugin source repository."""
    repo: str
    repo_ref: Optional[str]  # None triggers default branch resolution in __post_init__
    workspace_path: str
    logger: ClassVar[Logger] = get_logger("source_config")

    def __post_init__(self) -> None:
        if not self.repo:
            raise ConfigurationError("repo is required")
        if not self.workspace_path:
            raise ConfigurationError("workspace-path is required")
        
        # Resolve default branch at creation time if no ref was provided
        if not self.repo_ref:
            self.repo_ref = self.resolve_default_ref(self.repo)

    @classmethod
    def from_file(cls, source_file: Path) -> "SourceConfig":
        """Load source configuration from JSON file.

        repo-ref is optional. When omitted, the default branch is resolved
        automatically during construction via resolve_default_ref().

        Raises:
            ConfigurationError: If the file is missing, malformed, or has invalid data.
            ExecutionError: If default branch resolution fails (when repo-ref is omitted).
        """
        try:
            with open(source_file, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            raise ConfigurationError(f"Source configuration file not found: {source_file}")
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in {source_file}: {e}")
        except Exception as e:
            raise ConfigurationError(f"Failed to read {source_file}: {e}")

        try:
            repo = data["repo"]
            repo_ref = data.get("repo-ref") or None  # Treat empty string as None
            workspace_path = data.get("workspace-path")
        except KeyError as e:
            raise ConfigurationError(f"Missing required field {e} in {source_file}")
        
        config = cls(
            repo=repo,
            repo_ref=repo_ref,
            workspace_path=workspace_path,
        )

        return config
    
    @classmethod
    def from_cli_args(cls, repo: str, repo_ref: Optional[str], workspace_path: str) -> "SourceConfig":
        """Create source configuration from CLI arguments.
        
        Args:
            repo: Git repository URL (--source-repo).
            repo_ref: Git ref to check out (--source-ref). None means default branch
                (resolved automatically during construction via resolve_default_ref()).
            workspace_path: Path to workspace within the repository (--workspace-path).
        
        Returns:
            SourceConfig instance with repo_ref always resolved.
        
        Raises:
            ConfigurationError: If required fields are missing.
            ExecutionError: If default branch resolution fails (when repo_ref is None).
        """
        return cls(
            repo=repo,
            repo_ref=repo_ref,
            workspace_path=workspace_path,
        )
    
    @staticmethod
    def resolve_default_ref(repo: str) -> str:
        """Resolve the default branch ref for a repository using git ls-remote since repository is not cloned yet
        
        Args:
            repo: Git repository URL.
        
        Returns:
            The default branch ref (e.g., 'refs/heads/main').
        
        Raises:
            ExecutionError: If git ls-remote fails or the default branch cannot be determined.
        """
        logger = get_logger("source_config")
        logger.info(f"[cyan]Resolving default branch for {repo}cyan]")
        
        try:
            result = subprocess.run(
                ["git", "ls-remote", "--symref", repo, "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            
            for line in result.stdout.splitlines():
                if line.startswith("ref:"):
                    # Ex: Extract "refs/heads/main" from "ref: refs/heads/main\tHEAD"
                    ref_part = line.split("\t")[0].replace("ref: ", "").strip()
                    logger.info(f"[green]Resolved default branch: {ref_part} for {repo}[/green]")
                    return ref_part
            
            raise ConfigurationError(
                f"Could not resolve the default branch for '{repo}'. "
                f"Please specify a branch or ref explicitly via 'repo-ref' in {PluginFactoryConfig.SOURCE_CONFIG_FILE} "
                "or the --source-ref CLI argument."
            )
        except subprocess.CalledProcessError as e:
            raise ExecutionError(
                f"Failed to resolve default branch for {repo}: {e.stderr.strip()}",
                step="resolve default ref",
                returncode=e.returncode,
            ) from e
    
    def clone_to_path(self, repo_path: Path, clean: bool = False) -> None:
        """Clone the source repository to the specified path.

        Raises:
            ConfigurationError: If the destination directory does not exist.
            PluginFactoryError: If the user aborts the clone.
            ExecutionError: If git clone or checkout fails.
        """
        logger = get_logger("cli")
        
        if not repo_path.exists():
            raise ConfigurationError(f"Destination directory does not exist: {repo_path}")
                
        self.logger.info("[bold blue]Cloning repository[/bold blue]")
        self.logger.info(f"Repository: {self.repo}")
        self.logger.info(f"Reference: {self.repo_ref}")
        self.logger.info(f"Destination directory: {repo_path}")
        
        prompt_or_clean_directory(repo_path, clean, self.logger)
            
        try:
            cmd = ["git", "clone", self.repo, str(repo_path)]
            # Git writes progress to stderr, so log it as info instead of error
            returncode = run_command_with_streaming(
                cmd,
                logger,
                stderr_log_func=logger.info
            )
            
            if returncode != 0:
                raise ExecutionError(
                    f"Failed to clone repository (exit code {returncode})",
                    step="git clone",
                    returncode=returncode
                )
            
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
                raise ExecutionError(
                    f"Failed to checkout ref {self.repo_ref} (exit code {returncode})",
                    step="git checkout",
                    returncode=returncode
                )
            
            logger.info("[green]✓ Repository cloned successfully[/green]")

        except PluginFactoryError:
            raise
        except Exception as e:
            raise ExecutionError(
                f"Failed during repository clone/checkout: {e}",
                step="git clone/checkout"
            ) from e

@dataclass
class WorkspaceInfo:
    """Per-workspace configuration for multi-workspace mode.
    
    Represents a single workspace discovered from a config subdirectory.
    """
    name: str
    config_dir: Path
    source_config: SourceConfig
    repo_path: Optional[Path] = None
    output_dir: Optional[Path] = None

    def resolve_paths(self, base_repo_path: Path, base_output_dir: Path) -> None:
        """Set per-workspace source code repo and output paths from base directories."""
        self.repo_path = base_repo_path / self.name
        self.output_dir = base_output_dir / self.name


def discover_workspaces(config_dir: Path) -> list["WorkspaceInfo"]:
    """Scan config directory for workspace subdirectories.
    
    A subdirectory is considered a workspace if it contains a source.json file.
    Non-workspace entries are skipped silently; the caller is responsible for
    warning the user about ignored content.
    
    Args:
        config_dir: Root configuration directory to scan.
    
    Returns:
        List of WorkspaceInfo instances sorted by repo URL (primary) then name (secondary),
        making downstream groupby(repo) trivial.
    
    Raises:
        ConfigurationError: If a workspace's source.json is invalid.
    """
    logger = get_logger("config")
    workspaces: list[WorkspaceInfo] = []
    
    if not config_dir.is_dir():
        return workspaces
    
    for entry in sorted(config_dir.iterdir()):
        if not entry.is_dir():
            continue
        
        source_file = entry / PluginFactoryConfig.SOURCE_CONFIG_FILE
        if not source_file.exists():
            logger.debug(f"Skipping {entry.name}/ — no {PluginFactoryConfig.SOURCE_CONFIG_FILE}")
            continue
        
        workspace_name = entry.name
        logger.debug(f"Discovered workspace: {workspace_name}")
        
        source_config = SourceConfig.from_file(source_file)
        
        workspaces.append(WorkspaceInfo(
            name=workspace_name,
            config_dir=entry,
            source_config=source_config,
        ))
    
    # Sort by repo URL (primary) then workspace name (secondary)
    workspaces.sort(key=lambda w: (w.source_config.repo, w.name))
    
    return workspaces


def clone_workspaces_with_worktrees(
    workspaces: list["WorkspaceInfo"],
    base_repo_path: Path,
) -> None:
    """Clone repositories and create git worktrees for multi-workspace mode.
    
    Groups workspaces by repo URL, clones each unique repo once into
    <base_repo_path>/.clones/<repo-name>/, then creates a worktree per
    workspace at <base_repo_path>/<workspace-name>/.
    
    The caller is responsible for cleaning base_repo_path before calling
    this function (e.g. via prompt_or_clean_directory). This function
    assumes it can write freely into base_repo_path.
    
    Args:
        workspaces: List of WorkspaceInfo (must already have repo_path set via resolve_paths).
        base_repo_path: Base directory for repo clones and worktrees.
    
    Raises:
        PluginFactoryError: If a workspace has no repo_path resolved (internal error).
        ExecutionError: If any git operation fails.
    """
    from itertools import groupby
    
    logger = get_logger("config")
    clones_dir = base_repo_path / ".clones"
    os.makedirs(clones_dir, exist_ok=True)
    
    for repo_url, group in groupby(workspaces, key=lambda w: w.source_config.repo):
        workspace_list = list(group)
        repo_name: str = repo_dir_name(repo_url)
        clone_path: Path = clones_dir / repo_name
        
        logger.info(f"[bold blue]\nCloning base repository: {repo_url}[/bold blue]")
        logger.info(f"  Destination: {clone_path}")
        
        cmd = ["git", "clone", "--bare", repo_url, str(clone_path)]
        returncode = run_command_with_streaming(
            cmd, logger, stderr_log_func=logger.info
        )
        
        if returncode != 0:
            raise ExecutionError(
                f"Failed to clone repository '{repo_url}' (exit code {returncode}). "
                f"Please verify the 'repo' URL in the {PluginFactoryConfig.SOURCE_CONFIG_FILE} for workspaces using this repository. "
                f"Ensure the URL is correct and accessible from your environment.",
                step="git clone (bare)",
                returncode=returncode,
            )
        
        logger.info(f"[green]Cloned {repo_url} to {clone_path}[/green]")
        
        for ws in workspace_list:
            worktree_path = ws.repo_path
            if worktree_path is None:
                raise PluginFactoryError(
                    f"Internal error: workspace '{ws.name}' has no resolved repository path. "
                    f"This is a bug in the plugin factory. Please report this issue."
                )
            
            ref = ws.source_config.repo_ref
            logger.info(f"[cyan]\nCreating git worktree for '{ws.name}' at ref {ref}[/cyan]")
            
            # Must use absolute path: git worktree add runs with cwd=clone_path,
            # so a relative worktree_path would resolve against the clone directory.
            cmd = ["git", "worktree", "add", "--detach", str(worktree_path.resolve()), ref]
            returncode = run_command_with_streaming(
                cmd, logger, cwd=clone_path, stderr_log_func=logger.info
            )
            
            if returncode != 0:
                raise ExecutionError(
                    f"Failed to create worktree for workspace '{ws.name}' at ref '{ref}' (exit code {returncode}). "
                    f"Please verify the 'repo-ref' value in {ws.config_dir / PluginFactoryConfig.SOURCE_CONFIG_FILE}. "
                    f"Ensure the branch, tag, or commit exists in the repository.",
                    step="git worktree add",
                    returncode=returncode,
                )
            
            logger.info(f"[green]  Worktree created for '{ws.name}' at {worktree_path}[/green]")


class PluginListConfig:
    """Configuration for plugin list (YAML format)."""
    VALID_BACKSTAGE_PLUGIN_ROLES: ClassVar[set[str]] = {
        "frontend-plugin",
        "backend-plugin",
        "frontend-plugin-module",
        "backend-plugin-module",
    }

    BACKEND_ROLES: ClassVar[set[str]] = {
        "backend-plugin",
        "backend-plugin-module",
    }

    SKIP_DIRS: ClassVar[set[str]] = {
        "node_modules",
        "dist",
        "dist-dynamic",
        ".git",
        "__fixtures__",
    }

    _PKG_JSON: ClassVar[str] = "package.json"

    HOST_LOCKFILE: ClassVar[Path] = (
        Path(__file__).parent.parent.parent / "resources" / "rhdh" / "yarn.lock"
    )

    _LOCKFILE_BACKSTAGE_RE: ClassVar[re.Pattern] = re.compile(
        r'"(@backstage/[\w.-]+)@npm:'
    )

    _NATIVE_DEP_MARKERS: ClassVar[frozenset[str]] = frozenset[str]({
        "bindings", "prebuild", "nan", "node-pre-gyp", "node-gyp-build",
    })

    logger: ClassVar[Logger] = get_logger("plugin_list")

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
        """Save plugin list to YAML file.

        Writes manually rather than via yaml.dump so that entries with no
        build args appear as ``key:`` (YAML null) instead of ``key: ''``.

        Args:
            plugin_list_file: Destination path for the YAML file.
        """
        with open(plugin_list_file, 'w') as f:
            for path, args in self.plugins.items():
                if args:
                    f.write(f"{path}: {args}\n")
                else:
                    f.write(f"{path}:\n")
    
    def get_plugins(self) -> Dict[str, str]:
        return self.plugins.copy()
    
    def add_plugin(self, plugin_path: str, build_args: str = "") -> None:
        self.plugins[plugin_path] = build_args
    
    def remove_plugin(self, plugin_path: str) -> None:
        self.plugins.pop(plugin_path, None)

    @classmethod
    def create_default(cls, workspace_path: Path) -> "PluginListConfig":
        """Create a default plugin list by scanning workspace for Backstage plugins.

        Recursively walks *workspace_path* to find ``package.json`` files whose
        ``backstage.role`` matches one of :pyattr:`VALID_BACKSTAGE_PLUGIN_ROLES`.

        For backend plugins, dependency analysis is performed against the
        bundled RHDH host lockfile to determine ``--embed-package`` and
        ``--shared-package`` arguments.

        Args:
            workspace_path: Absolute path to the workspace root.

        Returns:
            A :class:`PluginListConfig` with discovered plugins and build arg(s) (if any).
        """
        plugins: Dict[str, str] = {}
        host_packages = cls._parse_host_backstage_packages(cls.HOST_LOCKFILE)

        for pkg_json_path in cls._find_package_jsons(workspace_path):
            role = cls._read_backstage_role(pkg_json_path)
            if role and role in cls.VALID_BACKSTAGE_PLUGIN_ROLES:
                plugin_dir = pkg_json_path.parent.relative_to(workspace_path).as_posix()

                if role in cls.BACKEND_ROLES:
                    build_args = cls._compute_backend_build_args(
                        workspace_path, plugin_dir, pkg_json_path, host_packages,
                    )
                    plugins[plugin_dir] = build_args
                else:
                    plugins[plugin_dir] = ""

        sorted_plugins = dict[str, str](sorted(plugins.items()))
        cls.logger.debug(f"Discovered {len(sorted_plugins)} plugin(s) in {workspace_path}")
        return cls(sorted_plugins)

    @classmethod
    def _find_package_jsons(cls, root: Path) -> list[Path]:
        """Recursively find package.json files, skipping non-plugin directories."""
        results: list[Path] = []

        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name in cls.SKIP_DIRS or entry.name.startswith("."):
                continue

            pkg_json = entry / cls._PKG_JSON
            if pkg_json.is_file():
                results.append(pkg_json)

            results.extend(cls._find_package_jsons(entry))

        return results

    @classmethod
    def _read_backstage_role(cls, pkg_json_path: Path) -> Optional[str]:
        """Read the ``backstage.role`` field from a package.json file.

        Returns:
            The role string, or *None* if the file cannot be parsed or has no role.
        """
        try:
            data = json.loads(pkg_json_path.read_text(encoding="utf-8"))
            cls.logger.debug(f"Read backstage role from {pkg_json_path}: {data.get('backstage', {}).get('role')}")
            return data.get("backstage", {}).get("role")
        except (json.JSONDecodeError, OSError) as e:
            cls.logger.warning(f"Failed to read {pkg_json_path}: {e}")
            return None

    @classmethod
    def _parse_host_backstage_packages(cls, lockfile_path: Path) -> set[str]:
        """Extract ``@backstage/*`` package names from a Yarn Berry lockfile (Yarn 2+).

        Scans top-level key lines (e.g.
        ``"@backstage/catalog-model@npm:^1.7.2, …":``) and collects distinct
        package names.

        Args:
            lockfile_path: Path to the host ``yarn.lock`` file.

        Returns:
            Set of ``@backstage/*`` package names found in the lockfile,
            or an empty set if the file does not exist.
        """
        if not lockfile_path.is_file():
            cls.logger.warning(f"Host lockfile not found at {lockfile_path}")
            return set[str]()

        packages: set[str] = set[str]()
        for line in lockfile_path.read_text(encoding="utf-8").splitlines():
            if not line.startswith('"@backstage/'):
                continue
            for match in cls._LOCKFILE_BACKSTAGE_RE.finditer(line):
                packages.add(match.group(1))

        cls.logger.debug(f"Parsed {len(packages)} @backstage/* packages from host lockfile")
        return packages

    @staticmethod
    def _get_sibling_names(plugin_name: str, role: str) -> set[str]:
        """Derive sibling package names that the RHDH CLI auto-embeds.

        Replicates the rhdh-cli logic: for backend plugins the CLI
        automatically embeds the ``-common`` and ``-node`` siblings.

        Args:
            plugin_name: The npm package name (e.g. ``@scope/my-plugin-backend``).
            role: The ``backstage.role`` value.

        Returns:
            Set of sibling package names, empty for non-backend roles.
        """
        if role == "backend-plugin":
            base = re.sub(r"-backend$", "", plugin_name)
        elif role == "backend-plugin-module":
            base = re.sub(r"-backend-module-.+$", "", plugin_name)
        else:
            return set[str]()

        if base == plugin_name:
            return set[str]()

        return {f"{base}-common", f"{base}-node"}

    @classmethod
    def _resolve_node_module_package_json(
        cls, workspace_path: Path, dep_name: str
    ) -> Optional[Path]:
        """Locate a dependency's ``package.json`` in the workspace root ``node_modules``.

        Yarn workspaces hoist all packages to the workspace root, so only that
        location is checked.

        Args:
            workspace_path: Absolute path to the workspace root.
            dep_name: npm package name (may be scoped, e.g. ``@aws/foo``).

        Returns:
            Path to the dependency's ``package.json``, or *None* if not found.
        """
        candidate = workspace_path / "node_modules" / dep_name / cls._PKG_JSON
        if candidate.is_file():
            return candidate
        return None

    @staticmethod
    def _is_native_module(pkg_data: dict) -> bool:
        """Check whether a ``package.json`` describes a native Node.js module.

        Replicates the logic of the ``is-native-module`` npm package used by RHDH CLI.
        """
        deps = pkg_data.get("dependencies", {})
        if any(marker in deps for marker in PluginListConfig._NATIVE_DEP_MARKERS):
            return True
        if pkg_data.get("gypfile"):
            return True
        if pkg_data.get("binary"):
            return True
        return False

    @classmethod
    def _gather_native_modules(
        cls,
        workspace_path: Path,
        private_dep_names: set[str],
    ) -> set[str]:
        """Find native modules in the transitive dependency tree of private deps.

        Recursively walks each dep's dependencies via ``node_modules``,
        checking :meth:`_is_native_module` on every package encountered.
        Tracks visited packages to avoid cycles.

        Args:
            workspace_path: Absolute workspace root.
            private_dep_names: Direct dep names to start the walk from.

        Returns:
            Set of native package names found.
        """
        native: set[str] = set[str]()
        visited: set[str] = set[str]()

        def _walk(dep_name: str) -> None:
            if dep_name in visited:
                return
            visited.add(dep_name)

            pkg_json = cls._resolve_node_module_package_json(workspace_path, dep_name)
            if pkg_json is None:
                return

            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return

            if cls._is_native_module(data):
                native.add(dep_name)

            for field in ("dependencies", "optionalDependencies"):
                for sub_dep in data.get(field, {}):
                    _walk(sub_dep)

        for dep in private_dep_names:
            _walk(dep)

        return native

    @classmethod
    def _check_third_party_dep(
        cls,
        workspace_path: Path,
        dep_name: str,
        host_packages: set[str],
        embed_packages: set[str],
        unshare_packages: set[str],
    ) -> None:
        """Check a non-``@backstage/*`` dep for transitive shared-package usage.

        If the dependency has any ``@backstage/*`` dependencies it is
        marked for embedding.  Dependencies absent from *host_packages* are
        additionally marked for unsharing.

        Results are collected directly into *embed_packages* / *unshare_packages*.
        """
        dep_pkg_json = cls._resolve_node_module_package_json(workspace_path, dep_name)
        if dep_pkg_json is None:
            cls.logger.debug(f"Could not resolve {dep_name} in node_modules")
            return

        try:
            dep_data = json.loads(dep_pkg_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            cls.logger.debug(f"Failed to read {dep_pkg_json}: {e}")
            return

        dep_deps = dep_data.get("dependencies", {})
        backstage_deps = [d for d in dep_deps if d.startswith("@backstage/")]

        if backstage_deps:
            embed_packages.add(dep_name)
            for dep in backstage_deps:
                if dep not in host_packages:
                    unshare_packages.add(dep)

    @classmethod
    def _compute_backend_build_args(
        cls,
        workspace_path: Path,
        plugin_dir: str,
        pkg_json_path: Path,
        host_packages: set[str],
    ) -> str:
        """Compute ``--embed-package`` / ``--shared-package`` args for a backend plugin.

        Analyses the plugin's direct dependencies:

        * ``@backstage/*`` deps missing from *host_packages* are unshared
          **and** embedded (the host won't provide them at runtime).
        * Non-``@backstage/*``, non-sibling deps whose own dependencies
          include ``@backstage/*`` packages are embedded.  Any of those
          sub-deps missing from *host_packages* are additionally unshared.

        Args:
            workspace_path: Absolute workspace root.
            plugin_dir: Plugin directory relative to *workspace_path*.
            pkg_json_path: Path to the plugin's ``package.json``.
            host_packages: ``@backstage/*`` names present in the host lockfile.

        Returns:
            CLI argument string, or ``""`` if no extra args are needed.
        """
        try:
            pkg_data = json.loads(pkg_json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return ""

        plugin_name: str = pkg_data.get("name", "")
        role: str = pkg_data.get("backstage", {}).get("role", "")
        dependencies: dict = pkg_data.get("dependencies", {})

        siblings = cls._get_sibling_names(plugin_name, role)

        embed_packages: set[str] = set[str]()
        unshare_packages: set[str] = set[str]()
        private_deps: set[str] = set[str]()

        for dep_name in dependencies:
            if dep_name in siblings:
                continue

            if dep_name.startswith("@backstage/"):
                if dep_name not in host_packages:
                    embed_packages.add(dep_name)
                    unshare_packages.add(dep_name)
                continue

            private_deps.add(dep_name)
            cls._check_third_party_dep(
                workspace_path, dep_name,
                host_packages, embed_packages, unshare_packages,
            )

        suppress_native = cls._gather_native_modules(
            workspace_path, private_deps | embed_packages | siblings,
        )

        parts = [f"--embed-package {pkg}" for pkg in sorted(embed_packages)]
        parts += [f"--shared-package !{pkg}" for pkg in sorted(unshare_packages)]
        parts += [f"--suppress-native-package {pkg}" for pkg in sorted(suppress_native)]
        return " ".join(parts)

