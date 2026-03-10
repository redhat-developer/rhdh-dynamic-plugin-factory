"""
Configuration management for RHDH Plugin Factory.
"""

import argparse
from logging import Logger
import os
from pathlib import Path
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
            self.logger.debug("Using --source-repo CLI argument, skipping source.json validation")
            return
        
        source_file = os.path.join(self.config_dir, "source.json")
        
        if not os.path.exists(source_file):
            if not os.path.exists(self.repo_path) or not os.listdir(self.repo_path):
                raise ConfigurationError(
                    f"source.json not found at {source_file} and {self.repo_path} is empty. "
                    "Please provide source.json to clone a repository, use --source-repo to specify a repository via CLI, "
                    "or use --use-local with a locally mounted repository."
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
        
        plugins_file = os.path.join(config_dir, "plugins-list.yaml")
        
        if os.path.exists(plugins_file):
            self.logger.debug(f"[green]plugins-list.yaml already exists at {plugins_file}. Skipping auto-generation.[/green]")
            return
        
        self.logger.info("[bold blue]Auto-generating plugins-list.yaml[/bold blue]")
        
        if not os.path.exists(repo_path):
            raise PluginFactoryError(f"Source code repository does not exist at {repo_path}")

        workspace_full_path = os.path.abspath(os.path.join(repo_path, workspace_path))
        if not os.path.exists(workspace_full_path):
            raise PluginFactoryError(f"Plugin workspace does not exist at {workspace_full_path}")
        
        try:
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
        
        source_file = os.path.join(self.config_dir, "source.json")

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
        
        plugins_list_file = os.path.join(config_dir, "plugins-list.yaml")
        
        if not os.path.exists(plugins_list_file):
            raise ConfigurationError("No plugins file found")

        config_env_file = os.path.join(config_dir, ".env")
        default_env_file = Path(__file__).parent.parent.parent / "default.env"
        load_dotenv(default_env_file)
        env = dict(os.environ)
        
        if os.path.exists(config_env_file):
            self.logger.debug(f"Loading script configuration from: {config_env_file}")
            load_dotenv(config_env_file, override=True)
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
                "Please specify a branch or ref explicitly via 'repo-ref' in source.json "
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
        
        source_file = entry / "source.json"
        if not source_file.exists():
            logger.debug(f"Skipping {entry.name}/ — no source.json")
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
        repo_name = repo_dir_name(repo_url)
        clone_path = clones_dir / repo_name
        
        logger.info(f"[bold blue]\nCloning base repository: {repo_url}[/bold blue]")
        logger.info(f"  Destination: {clone_path}")
        
        cmd = ["git", "clone", "--bare", repo_url, str(clone_path)]
        returncode = run_command_with_streaming(
            cmd, logger, stderr_log_func=logger.info
        )
        
        if returncode != 0:
            raise ExecutionError(
                f"Failed to clone repository '{repo_url}' (exit code {returncode}). "
                f"Please verify the 'repo' URL in the source.json for workspaces using this repository. "
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
                    f"Please verify the 'repo-ref' value in {ws.config_dir / 'source.json'}. "
                    f"Ensure the branch, tag, or commit exists in the repository.",
                    step="git worktree add",
                    returncode=returncode,
                )
            
            logger.info(f"[green]  Worktree created for '{ws.name}' at {worktree_path}[/green]")


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

