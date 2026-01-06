"""
Utility functions for RHDH Plugin Factory.
"""

import subprocess
import threading
from pathlib import Path
from typing import Optional, Callable


def _stream_output(pipe, log_func: Callable[[str], None]) -> None:
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
    logger_instance,
    cwd: Optional[Path] = None,
    env: Optional[dict] = None,
    stderr_log_func: Optional[Callable[[str], None]] = None
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
        env=env
    )
    
    # Create threads to read stdout and stderr concurrently
    stdout_thread = threading.Thread(
        target=_stream_output,
        args=(process.stdout, logger_instance.info)
    )
    stderr_thread = threading.Thread(
        target=_stream_output,
        args=(process.stderr, stderr_log_func)
    )
    
    stdout_thread.start()
    stderr_thread.start()
    
    stdout_thread.join()
    stderr_thread.join()
    
    process.wait()
    
    return process.returncode


def display_export_results(workspace_path: Path, logger) -> bool:
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

