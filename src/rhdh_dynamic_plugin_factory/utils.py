"""
Utility functions for RHDH Plugin Factory.
"""

import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable
from logging import Logger
from pathlib import Path
from typing import IO

from .exceptions import ExecutionError, PluginFactoryError


def _stream_output(pipe: IO[str], log_func: Callable[[str], None]) -> None:
    """
    Stream output from a pipe to a logging function.

    Args:
        pipe: A file-like object to read from (e.g., process.stdout or process.stderr)
        log_func: A callable that logs each line (e.g., logger.info or logger.error)
    """
    try:
        for line in pipe:
            log_func(line.rstrip())
    finally:
        pipe.close()


def run_command_with_streaming(
    cmd: list[str],
    logger_instance: Logger,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    stderr_log_func: Callable[[str], None] | None = None,
) -> int:
    """
    Run a command with real-time streaming of both stdout and stderr.

    Args:
        cmd: Command and arguments to run
        logger_instance: Logger instance to use for output
        cwd: Working directory for the command
        env: Environment variables for the command
        stderr_log_func: Optional custom logging function for stderr.
                        Defaults to logger_instance.warning if not provided.
                        Use logger_instance.info for commands that write
                        informational output to stderr (like git).

    Returns:
        The return code of the process
    """
    # Default to warning logging for stderr if not specified
    # (many tools write both warnings and errors to stderr)
    if stderr_log_func is None:
        stderr_log_func = logger_instance.warning

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=cwd,
        env=env,
    )

    # Create threads to read stdout and stderr concurrently
    stdout_thread = threading.Thread(target=_stream_output, args=(process.stdout, logger_instance.info))
    stderr_thread = threading.Thread(target=_stream_output, args=(process.stderr, stderr_log_func))

    stdout_thread.start()
    stderr_thread.start()

    stdout_thread.join()
    stderr_thread.join()

    process.wait()

    return process.returncode


def collect_build_logs(logger: Logger, tmp_dir: Path | None = None) -> None:
    """Find and display build log files left by failed native package builds.

    Scans a temp directory for build.log files (typically created by yarn when
    native dependencies fail to compile) and logs their full contents.

    Args:
        logger: Logger instance to use for output.
        tmp_dir: Directory to scan for build.log files. Defaults to the
                 system temp directory (usually /tmp).
    """
    search_dir = tmp_dir or Path(tempfile.gettempdir())

    try:
        build_logs = sorted(search_dir.rglob("build.log"))
    except OSError as e:
        logger.warning(f"[yellow]Could not find build logs in {search_dir}: {e}[/yellow]")
        return

    if not build_logs:
        logger.warning(f"[yellow]No build logs found in {search_dir}[/yellow]")
        return

    logger.warning(f"[yellow]Found {len(build_logs)} build log(s) that may contain details about the failure:[/yellow]")

    for log_path in build_logs:
        try:
            contents = log_path.read_text().strip()
        except OSError:
            logger.warning(f"[yellow]Could not read build log: {log_path}[/yellow]")
            continue

        if not contents:
            logger.warning(f"[yellow]Empty build log: {log_path}[/yellow]")
            continue

        logger.warning(f"[yellow]Build log: {log_path}[/yellow]")
        for line in contents.splitlines():
            logger.warning(f"  {line}")


def display_export_results(workspace_path: Path, logger: Logger) -> bool:
    """Display results from export script output files.

    Args:
        workspace_path: Path to the workspace where the output files are located.
        logger: Logger instance to use for output.

    Returns:
        True if there were any failed exports, False otherwise.
    """
    failed_file = workspace_path / "failed-exports-output"
    published_file = workspace_path / "published-exports-output"
    has_failures = False

    if failed_file.exists():
        failed_exports = failed_file.read_text().strip().split("\n") if failed_file.stat().st_size > 0 else []
        if failed_exports and failed_exports[0]:
            has_failures = True
            logger.error(f"Failed exports ({len(failed_exports)}): {', '.join(failed_exports)}")

    if published_file.exists():
        published_exports = published_file.read_text().strip().split("\n") if published_file.stat().st_size > 0 else []
        if published_exports and published_exports[0]:
            logger.info(f"[green]Published images ({len(published_exports)}):[/green]")
            for image in published_exports:
                logger.info(f"  - {image}")

    return has_failures


def clean_directory(directory: Path) -> None:
    """Clean the directory by removing all contents but keeping the directory itself.
    This is to handle cleaning volume mounted directories.

    Args:
        directory: Path to the directory to clean.
    Raises:
        ExecutionError: If the directory or files cannot be removed.
    """
    try:
        for item in directory.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    except Exception as e:
        raise ExecutionError(
            f"Failed to clean directory '{directory}': {e}",
            step="clean directory",
            returncode=1,
        ) from e


def prompt_or_clean_directory(path: Path, clean: bool, logger: Logger) -> None:
    """Clears contents of a non-empty directory by automatically or by prompting the user.

    If the directory is empty or does not exist, this is a no-op.

    Args:
        path: Directory to clean
        clean: If True, auto-clean without prompting.
        logger: Logger instance.

    Raises:
        PluginFactoryError: If the user declines to clean.
        ExecutionError: If the directory or files cannot be removed. (Thrown from clean_directory)
    """
    if not path.exists() or not any(path.iterdir()):
        return

    logger.warning(f"[yellow]Source directory {path} is not empty[/yellow]")
    if clean:
        logger.warning(f"[yellow]`--clean` argument set, automatically cleaning {path}[/yellow]")
        clean_directory(path)
    else:
        logger.warning(f"[yellow]WARNING: Are you sure you want to remove the contents of {path}/? \\[y/N][/yellow]")
        confirm = input()
        if confirm.lower() != "y":
            logger.warning("[yellow]Aborted[/yellow]")
            raise PluginFactoryError("Directory clean aborted by user")
        else:
            logger.warning(
                f"[yellow]`y` selected. Cleaning {path}. Note: you can use the `--clean` argument to automatically clean the directory and skip this prompt next time.[/yellow]"
            )
            clean_directory(path)


def repo_dir_name(repo_url: str) -> str:
    """Derive a directory name from a git repository URL.

    Examples:
        https://github.com/backstage/community-plugins.git -> community-plugins
        https://github.com/awslabs/backstage-plugins-for-aws -> backstage-plugins-for-aws
    """
    name = repo_url.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name
