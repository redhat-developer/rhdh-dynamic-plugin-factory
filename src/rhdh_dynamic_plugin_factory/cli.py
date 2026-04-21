"""
Command-line interface for RHDH Plugin Factory - Setup and orchestration tool.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Handle both direct script execution and module execution
try:
    from .__version__ import __version__
    from .config import PluginFactoryConfig
    from .exceptions import ConfigurationError, ExecutionError, PluginFactoryError
    from .logger import get_logger, setup_logging
    from .source_config import (
        WorkspaceInfo,
        clone_workspaces_with_worktrees,
        discover_workspaces,
    )
    from .utils import (
        collect_build_logs,
        prompt_or_clean_directory,
        run_command_with_streaming,
    )
except ImportError:
    # For direct script execution, add parent directory to path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from rhdh_dynamic_plugin_factory.__version__ import __version__
    from rhdh_dynamic_plugin_factory.config import PluginFactoryConfig
    from rhdh_dynamic_plugin_factory.exceptions import (
        ConfigurationError,
        ExecutionError,
        PluginFactoryError,
    )
    from rhdh_dynamic_plugin_factory.logger import get_logger, setup_logging
    from rhdh_dynamic_plugin_factory.source_config import (
        WorkspaceInfo,
        clone_workspaces_with_worktrees,
        discover_workspaces,
    )
    from rhdh_dynamic_plugin_factory.utils import (
        collect_build_logs,
        prompt_or_clean_directory,
        run_command_with_streaming,
    )

logger = get_logger("cli")

_PROJECT_ROOT = Path(__file__).parent.parent.parent


def _build_version_string() -> str:
    """Build version string including external resource metadata."""
    lines = [f"rhdh-dynamic-plugin-factory:  {__version__}"]
    try:
        metadata_path = _PROJECT_ROOT / "resources" / "metadata.json"
        metadata = json.loads(metadata_path.read_text())
        lines.append(f"RHDH commit:                  {metadata['rhdh-hash']}")
        lines.append(f"export-util script commit:    {metadata['export-util-script-hash']}")
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        pass
    return "\n".join(lines)


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        description="RHDH Dynamic Plugin Factory - Setup and orchestrate plugin building",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
        # Build plugins for the todo workspace in backstage/community-plugins w/o pushing to a registry
        # This assumes that ./config is populated with the source.json and plugins-list.yaml files
        python src/rhdh_dynamic_plugin_factory --config-dir ./config --repo-path ./source --log-level DEBUG --output-dir ./outputs

        # Build a single workspace of plugins using CLI args instead of source.json
        python src/rhdh_dynamic_plugin_factory --source-repo https://github.com/backstage/community-plugins --source-ref main --workspace-path workspaces/todo --config-dir ./config --repo-path ./source --output-dir ./outputs
        """,
    )
    parser.add_argument("-v", "--version", action="version", version=_build_version_string())
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path("/config"),
        help="Configuration directory path containing plugin-list.yaml, .env, patches/ and overlays/ directories",
    )
    parser.add_argument(
        "--repo-path",
        type=Path,
        default=Path("/source"),
        help="Path to store the plugin source code",
    )
    parser.add_argument(
        "--workspace-path",
        type=Path,
        help="Path to the workspace from root of the repository. Can also be provided via the source.json workspace-path field.",
    )
    parser.add_argument(
        "--source-repo",
        type=str,
        default=None,
        help="Git repository URL. When provided, source.json is ignored and the repository is cloned from this URL.",
    )
    parser.add_argument(
        "--source-ref",
        type=str,
        default=None,
        help="Git ref (branch/tag/commit) to check out. Optional: defaults to the repository's default branch. Requires --source-repo.",
    )
    parser.add_argument(
        "--push-images",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Push images to registry (default: false)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/outputs"),
        help="Path to the output directory",
    )
    parser.add_argument(
        "--use-local",
        action="store_true",
        default=False,
        help="Use local repository content instead of cloning from source.json",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show verbose output (show file and line number)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        default=False,
        help="Clean the source directory before cloning source repository. WARNING: This will remove all the contents of the source directory.",
    )
    parser.add_argument(
        "--generate-build-args",
        action="store_true",
        default=False,
        help="When plugins-list.yaml exists, (re)compute build arguments for all "
        "listed plugins using dependency analysis. WARNING: This overwrites "
        "your plugins-list.yaml with updated build args.",
    )
    return parser


def install_dependencies(workspace_path: Path) -> None:
    """Install dependencies in the workspace using yarn install with corepack.

    Raises:
        ExecutionError: If any dependency installation step fails.
    """
    logger.info("[bold blue]Installing workspace dependencies[/bold blue]")
    STEP_NAME = "install dependencies"

    commands = [
        (["pwd"], "Checking workspace path"),
        (["corepack", "enable"], "Enabling corepack"),
        (["yarn", "--version"], "Checking yarn version"),
        (["yarn", "install", "--immutable"], "Installing dependencies"),
        (["yarn", "tsc"], "Running TypeScript compilation"),
    ]

    try:
        env = os.environ.copy()
        env["COREPACK_ENABLE_DOWNLOAD_PROMPT"] = "0"  # Disable download prompts

        for cmd, description in commands:
            logger.info(f"[cyan]{description}[/cyan]")

            returncode = run_command_with_streaming(cmd, logger, cwd=workspace_path, env=env)

            if cmd[:2] == ["yarn", "install"]:
                collect_build_logs(logger, has_errors=returncode != 0)

            if returncode != 0:
                raise ExecutionError(
                    f"{description} failed with exit code {returncode}",
                    step=STEP_NAME,
                    returncode=returncode,
                )

            logger.info(f"[green]{description} completed successfully[/green]")
    except ExecutionError:
        raise
    except Exception as e:
        raise ExecutionError(
            f"Failed to install dependencies: {e}",
            step=STEP_NAME,
        ) from e


def _process_workspace(
    config: PluginFactoryConfig,
    workspace_config_dir: str,
    repo_path: str,
    workspace_path: str,
    output_dir: str,
    generate_build_args: bool = False,
) -> None:
    """Execute the plugin factory pipeline for a single workspace.

    Args:
        config: Global factory configuration.
        workspace_config_dir: Config directory for this workspace (patches, overlays, plugins-list).
        repo_path: Path to the repository checkout for this workspace.
        workspace_path: Relative path from repo_path to the workspace.
        output_dir: Output directory for build artifacts.
        generate_build_args: If True, (re)compute build args for a user-provided plugins-list.yaml.
    """
    was_auto_generated = config.discover_plugins_list(
        config_dir=workspace_config_dir,
        repo_path=repo_path,
        workspace_path=workspace_path,
    )

    logger.info("[bold blue]Applying Patches and Overlays[/bold blue]")
    config.apply_patches_and_overlays(
        config_dir=workspace_config_dir,
        repo_path=repo_path,
        workspace_path=workspace_path,
    )

    logger.info("[bold blue]Installing Dependencies[/bold blue]")
    full_workspace_path = Path(repo_path).joinpath(workspace_path).absolute()
    install_dependencies(full_workspace_path)

    if was_auto_generated or generate_build_args:
        config.populate_plugins_build_args(
            config_dir=workspace_config_dir,
            repo_path=repo_path,
            workspace_path=workspace_path,
        )

    logger.info("[bold blue]Exporting plugins using RHDH CLI[/bold blue]")
    config.export_plugins(
        output_dir=output_dir,
        config_dir=workspace_config_dir,
        repo_path=repo_path,
        workspace_path=workspace_path,
    )


def _load_env_for_workspace(
    base_env: dict[str, str],
    workspace_env_path: Path,
) -> None:
    """Apply workspace-specific .env overrides on top of the base environment.

    Precedence (highest to lowest):
        workspace .env  >  root .env  >  Podman/system env vars  >  default.env

    base_env already contains Podman + default.env + root .env (captured once
    after load_from_env in _run_multi_workspace). This function restores that
    baseline and layers only the workspace-specific .env on top.
    """
    from dotenv import load_dotenv

    os.environ.clear()
    os.environ.update(base_env)

    if workspace_env_path.exists():
        load_dotenv(workspace_env_path, override=True)


def _run(args: argparse.Namespace) -> None:
    """Execute the main plugin factory workflow.

    Detects multi-workspace vs single-workspace mode and dispatches accordingly.
    All steps either succeed silently or raise an exception,
    which is caught by the centralized handler in main().
    """
    config_dir = Path(str(args.config_dir))

    workspaces = discover_workspaces(config_dir)

    if workspaces:
        _run_multi_workspace(args, workspaces)
    else:
        _run_single_workspace(args)


def _run_multi_workspace(args: argparse.Namespace, workspaces: list[WorkspaceInfo]) -> None:
    """Execute multi-workspace mode."""
    # Reject single-workspace-only CLI args
    if getattr(args, "source_repo", None):
        raise ConfigurationError(
            "--source-repo cannot be used in multi-workspace mode. "
            "Each workspace must define its source in its own source.json."
        )
    if getattr(args, "source_ref", None):
        raise ConfigurationError(
            "--source-ref cannot be used in multi-workspace mode. "
            "Each workspace must define its source in its own source.json."
        )
    if getattr(args, "workspace_path", None):
        raise ConfigurationError(
            "--workspace-path cannot be used in multi-workspace mode. "
            "Each workspace defines its workspace-path in its own source.json."
        )

    config_dir = Path(str(args.config_dir))
    base_repo_path = Path(str(args.repo_path))
    base_output_dir = Path(str(args.output_dir))

    logger.info(f"[bold blue]Multi-workspace mode: discovered {len(workspaces)} workspace(s)[/bold blue]")

    # Warn about any root-level content that is not a workspace or the root .env
    workspace_names = {ws.name for ws in workspaces}
    ignored_items: list[str] = []
    for entry in sorted(config_dir.iterdir()):
        if entry.name == ".env":
            continue
        if entry.name in workspace_names:
            continue
        suffix = "directory — not a workspace, missing source.json" if entry.is_dir() else "file"
        ignored_items.append(f"  - {entry.name}{'/' if entry.is_dir() else ''} ({suffix})")
    if ignored_items:
        items_str = "\n".join(ignored_items)
        logger.warning(
            f"[yellow]The following items in the config directory will be ignored in multi-workspace mode\n"
            f"and should be moved into a workspace subdirectory or removed:\n"
            f"{items_str}[/yellow]"
        )

    logger.info("[bold blue]Workspaces to be processed:[/bold blue]")
    for ws in workspaces:
        logger.info(f"  - {ws.name}: {ws.source_config.repo} @ {ws.source_config.repo_ref}")
        # Resolve per-workspace source and output paths to avoid conflicts between workspaces
        ws.resolve_paths(base_repo_path, base_output_dir)

    # Load global config (uses root .env for global settings like registry credentials)
    config = PluginFactoryConfig.load_from_env(
        args=args,
        env_file=config_dir / ".env",
        push_images=args.push_images,
        multi_workspace=True,
    )

    # base_env now contains Podman + default.env + root .env — everything that is
    # constant across workspaces. Per-workspace loop only layers workspace .env on top.
    base_env = dict(os.environ)

    # Clone repositories / create worktrees (unless --use-local)
    if not config.use_local:
        logger.info("[bold blue]Setting up repositories with git worktrees[/bold blue]")
        prompt_or_clean_directory(base_repo_path, args.clean, logger)
        clone_workspaces_with_worktrees(workspaces, base_repo_path)
    else:
        logger.info("[bold blue]--use-local flag is set, expecting repositories pre-placed[/bold blue]")
        for ws in workspaces:
            if ws.repo_path and not ws.repo_path.exists():
                raise ConfigurationError(
                    f"Local repository for workspace '{ws.name}' not found at {ws.repo_path}. "
                    f"When using --use-local in multi-workspace mode, place repos at <repo-path>/<workspace-name>/."
                )

    errors: list[tuple[str, Exception]] = []
    successes: list[str] = []

    for ws in workspaces:
        logger.info(f"\n[bold blue]{'=' * 60}[/bold blue]")
        logger.info(f"[bold blue]Processing workspace: {ws.name}[/bold blue]")
        logger.info(f"[bold blue]{'=' * 60}[/bold blue]")

        # Restore base env and layer workspace-specific .env on top
        _load_env_for_workspace(base_env, ws.config_dir / ".env")
        config.refresh_registry_config()

        try:
            _process_workspace(
                config=config,
                workspace_config_dir=str(ws.config_dir),
                repo_path=str(ws.repo_path),
                workspace_path=ws.source_config.workspace_path,
                output_dir=str(ws.output_dir),
                generate_build_args=args.generate_build_args,
            )
            successes.append(ws.name)
            logger.info(f"[green]Workspace '{ws.name}' export completed successfully[/green]")
        except PluginFactoryError as e:
            errors.append((ws.name, e))
            logger.error(f"[red]Workspace '{ws.name}' export failed: {e}[/red]")

    # Report summary
    logger.info(f"\n[bold blue]{'=' * 60}[/bold blue]")
    logger.info("[bold blue]Multi-workspace Summary[/bold blue]")
    logger.info(f"[bold blue]{'=' * 60}[/bold blue]")
    logger.info(f"  Total: {len(workspaces)} | Succeeded: {len(successes)} | Failed: {len(errors)}")

    for name in successes:
        logger.info(f"  [green]{name} completed successfully[/green]")
    for name, error in errors:
        logger.error(f"  [red]{name} failed: {error}[/red]")

    if errors:
        raise ExecutionError(
            f"{len(errors)} of {len(workspaces)} workspace(s) failed",
            step="multi-workspace processing",
        )


def _run_single_workspace(args: argparse.Namespace) -> None:
    """Execute single-workspace mode"""
    config = PluginFactoryConfig.load_from_env(
        args=args,
        env_file=args.config_dir / ".env",
        push_images=args.push_images,
    )

    source_config = config.setup_config_directory()

    # Resolve workspace_path from source_config if not set via CLI/env
    if not config.workspace_path and source_config:
        config.workspace_path = source_config.workspace_path

    # Validate workspace_path is set (may come from CLI, env var, or source.json)
    if not config.workspace_path:
        raise ConfigurationError(
            "workspace-path must be set via --workspace-path argument or source.json workspace-path field"
        )

    if source_config and not config.use_local:
        logger.info("[bold blue]Repository Setup[/bold blue]")
        source_config.clone_to_path(Path(config.repo_path), clean=args.clean)
    elif config.use_local or not source_config:
        if config.use_local:
            logger.info("[bold blue]--use-local flag is set, using local repository[/bold blue]")
        else:
            logger.info("[bold blue]No source configuration found, using local repository[/bold blue]")
        repo_path = Path(str(config.repo_path))
        if not repo_path.exists():
            raise ConfigurationError(
                f"Local repository does not exist at: {config.repo_path}. "
                "Either provide source.json to clone the repository, "
                "use --source-repo to specify a repository via CLI, "
                "or ensure workspace exists at directory specified by --repo-path"
            )
        logger.info(f"Using local repository at: {config.repo_path}")

    if config.push_images:
        config._validate_registry_fields()
        config._buildah_login()

    _process_workspace(
        config=config,
        workspace_config_dir=str(config.config_dir),
        repo_path=str(config.repo_path),
        workspace_path=str(config.workspace_path),
        output_dir=str(args.output_dir),
        generate_build_args=args.generate_build_args,
    )


def main() -> None:
    """Main entry point for the RHDH Dynamic Plugin Factory."""
    parser = create_parser()
    args = parser.parse_args()
    setup_logging(level=args.log_level, verbose=args.verbose)

    try:
        _run(args)
    except ConfigurationError as e:
        logger.error(f"[red]Configuration error: {e}[/red]")
        sys.exit(1)
    except ExecutionError as e:
        step_info = f"{e.step}: " if e.step else ""
        logger.error(f"[red]{step_info}{e}[/red]")
        sys.exit(e.returncode or 1)
    except PluginFactoryError as e:
        logger.error(f"[red]{e}[/red]")
        sys.exit(1)

    logger.info("[green]All operations completed successfully[/green]")


if __name__ == "__main__":
    main()
