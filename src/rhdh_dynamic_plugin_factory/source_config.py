"""
Source repository and workspace configuration for RHDH Plugin Factory.

Handles git repository cloning, workspace discovery, and worktree management.
"""

from logging import Logger
import os
from pathlib import Path
from typing import Optional, ClassVar
from dataclasses import dataclass
import json
import subprocess

from .constants import SOURCE_CONFIG_FILE
from .exceptions import PluginFactoryError, ConfigurationError, ExecutionError
from .logger import get_logger
from .utils import run_command_with_streaming, prompt_or_clean_directory, repo_dir_name


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
        logger.info(f"[cyan]Resolving default branch for {repo}[/cyan]")
        
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
                f"Please specify a branch or ref explicitly via 'repo-ref' in {SOURCE_CONFIG_FILE} "
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
            
            cmd = ["git", "checkout", str(self.repo_ref)]
            logger.info(f"[cyan]Checking out ref: {self.repo_ref}[/cyan]")
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
            
            logger.info("[green]Repository cloned successfully[/green]")

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
        
        source_file = entry / SOURCE_CONFIG_FILE
        if not source_file.exists():
            logger.debug(f"Skipping {entry.name}/ — no {SOURCE_CONFIG_FILE}")
            continue
        
        workspace_name = entry.name
        logger.debug(f"Discovered workspace: {workspace_name}")
        
        source_config = SourceConfig.from_file(source_file)
        
        workspaces.append(WorkspaceInfo(
            name=workspace_name,
            config_dir=entry,
            source_config=source_config,
        ))
    
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
                f"Please verify the 'repo' URL in the {SOURCE_CONFIG_FILE} for workspaces using this repository. "
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
            
            cmd = ["git", "worktree", "add", "--detach", str(worktree_path.resolve()), ref]
            returncode = run_command_with_streaming(
                cmd, logger, cwd=clone_path, stderr_log_func=logger.info
            )
            
            if returncode != 0:
                raise ExecutionError(
                    f"Failed to create worktree for workspace '{ws.name}' at ref '{ref}' (exit code {returncode}). "
                    f"Please verify the 'repo-ref' value in {ws.config_dir / SOURCE_CONFIG_FILE}. "
                    f"Ensure the branch, tag, or commit exists in the repository.",
                    step="git worktree add",
                    returncode=returncode,
                )
            
            logger.info(f"[green]  Worktree created for '{ws.name}' at {worktree_path}[/green]")
