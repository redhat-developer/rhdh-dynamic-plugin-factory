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
import subprocess

from .constants import PLUGIN_LIST_FILE, SOURCE_CONFIG_FILE
from .exceptions import PluginFactoryError, ConfigurationError, ExecutionError
from .logger import get_logger
from .utils import run_command_with_streaming, display_export_results

from .source_config import SourceConfig
from .plugin_list_config import PluginListConfig

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
            self.logger.debug(f"Using --source-repo CLI argument, skipping {SOURCE_CONFIG_FILE} validation")
            return
        
        source_file = os.path.join(self.config_dir, SOURCE_CONFIG_FILE)
        
        if not os.path.exists(source_file):
            if not os.path.exists(self.repo_path) or not os.listdir(self.repo_path):
                raise ConfigurationError(
                    f"{SOURCE_CONFIG_FILE} not found at {source_file} and {self.repo_path} is empty. "
                    "Please provide {SOURCE_CONFIG_FILE} to clone a repository, use --source-repo to specify a repository via CLI, "
                    "or use --use-local with a locally mounted repository."
                )
            else:
                self.logger.warning(
                    f"{SOURCE_CONFIG_FILE} not found at {source_file}. Will attempt to use local repository content at {self.repo_path}"
                )
        else:
            self.logger.debug(f"Using source configuration from: {source_file}")
    
    def _validate_plugins_list(self) -> None:
        """Validate plugins-list.yaml file existence."""
        plugins_file = os.path.join(self.config_dir, PLUGIN_LIST_FILE)
        
        if not os.path.exists(plugins_file):
            self.logger.warning(
                f"{PLUGIN_LIST_FILE} not found at {plugins_file}. Will attempt to auto-generate after repository is available."
            )
        else:
            self.logger.debug(f"Using {PLUGIN_LIST_FILE} from: {plugins_file}")
    
    def auto_generate_plugins_list(self, config_dir: Optional[str] = None,
                                    repo_path: Optional[str] = None,
                                    workspace_path: Optional[str] = None,
                                    generate_build_args: bool = False) -> None:
        """Auto-generate plugins-list.yaml, or populate build args for an existing one.

        When the file does not exist, a full scan is performed (all plugins
        in the workspace are discovered).

        When the file already exists and ``generate_build_args``*`` is ``True``,
        build arguments are (re)computed for every plugin listed in the file.

        Args:
            config_dir: Config directory containing plugins-list.yaml. Defaults to self.config_dir.
            repo_path: Repository path. Defaults to self.repo_path.
            workspace_path: Workspace path relative to repo. Defaults to self.workspace_path.
            generate_build_args: If True, recompute build args for an existing plugins-list.yaml.

        Raises:
            PluginFactoryError: If auto-generation or build-arg population fails.
        """
        config_dir = config_dir or self.config_dir
        repo_path = repo_path or self.repo_path
        workspace_path = workspace_path or self.workspace_path
        
        plugins_file = os.path.join(config_dir, PLUGIN_LIST_FILE)
        
        if os.path.exists(plugins_file):
            if generate_build_args:
                self._populate_build_args_for_existing(plugins_file, repo_path, workspace_path)
            else:
                self.logger.debug(f"[green]{PLUGIN_LIST_FILE} already exists at {plugins_file}. Skipping auto-generation.[/green]")
            return
        
        self.logger.info(f"[bold blue]Auto-generating {PLUGIN_LIST_FILE}[/bold blue]")
        
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
                self.logger.info(f"Generated {PLUGIN_LIST_FILE} with {len(plugins)} plugin(s)")
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

    def _populate_build_args_for_existing(
        self, plugins_file: str, repo_path: str, workspace_path: str,
    ) -> None:
        """Load an existing plugins-list.yaml, recompute build args, and write it back.

        Args:
            plugins_file: Absolute path to the plugins-list.yaml file.
            repo_path: Repository root path.
            workspace_path: Workspace path relative to repo_path.

        Raises:
            PluginFactoryError: If the workspace cannot be found or population fails.
        """
        self.logger.warning(
            f"[yellow]--generate-build-args: Modifying existing {PLUGIN_LIST_FILE} "
            f"to (re)compute build arguments. Your file will be overwritten.[/yellow]"
        )

        workspace_full_path = os.path.abspath(os.path.join(repo_path, workspace_path))
        if not os.path.exists(workspace_full_path):
            raise PluginFactoryError(f"Plugin workspace does not exist at {workspace_full_path}")

        try:
            plugin_cfg = PluginListConfig.from_file(Path(plugins_file))
            plugin_cfg.populate_build_args(Path(workspace_full_path))
            plugin_cfg.to_file(Path(plugins_file))
        except PluginFactoryError:
            raise
        except Exception as e:
            raise PluginFactoryError(
                f"Failed to populate build args for {PLUGIN_LIST_FILE}: {e}"
            ) from e
    
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
        
        source_file = os.path.join(self.config_dir, SOURCE_CONFIG_FILE)

        if os.path.exists(source_file) and not self.use_local:
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
        
        plugins_list_file = os.path.join(self.config_dir, PLUGIN_LIST_FILE)
        
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
        
        plugins_list_file = os.path.join(config_dir, PLUGIN_LIST_FILE)
        
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
