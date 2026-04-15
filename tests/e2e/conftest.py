"""
E2E test fixtures for RHDH Dynamic Plugin Factory container tests.

These tests run the actual container image against known config fixtures
and validate that builds succeed without errors and produce expected outputs.

Required environment variables:
    E2E_IMAGE: Container image to test (e.g. quay.io/.../dynamic-plugins-factory:pr-42)

Optional environment variables:
    E2E_CONTAINER_RUNTIME: Container runtime binary (default: podman)
    E2E_LOG_DIR:           Directory to save container logs (default: tests/e2e/logs/)
"""

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest
import yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures"
DEFAULT_LOG_DIR = Path(__file__).parent / "logs"
CONTAINER_TIMEOUT = 1800  # 30 minutes (allows headroom for parallel runs)


@dataclass
class ContainerResult:
    """Structured result from running the factory container.

    ``output`` contains the merged stdout+stderr stream in chronological order.
    ``log_file`` is the path to the persisted log file on disk.
    """

    returncode: int
    output: str
    output_dir: Path
    log_file: Path


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

_FAILED_EXPORTS_MARKER = "Plugins with failed exports:"

_ERROR_PATTERNS: list[str] = [
    "Error running CLI",
    "Error pushing container",
    "Error building container",
]


def parse_plugins_from_config(config_dir: Path) -> list[str]:
    """Read plugins-list.yaml from *config_dir* and return plugin paths.

    Handles both valued and empty YAML keys, comments, and blank lines.
    """
    plugins_file = config_dir / "plugins-list.yaml"
    data = yaml.safe_load(plugins_file.read_text())
    if not data or not isinstance(data, dict):
        return []
    return list(data.keys())


def plugin_path_to_output_pattern(plugin_path: str) -> re.Pattern:
    """Build a regex that matches the npm-pack tarball for *plugin_path*.

    For flat paths like ``plugins/todo`` the last component (``todo``) appears
    directly in the tarball name, e.g. ``backstage-community-plugin-todo-0.12.0.tgz``.

    For nested paths like ``plugins/ecs/frontend`` the last component is a
    generic role name that may not appear in the tarball at all.  In that case
    we match on the **parent** directory (``ecs``) and distinguish frontend
    from backend via the presence/absence of ``-backend`` in the filename.
    """
    parts = Path(plugin_path).parts
    plugin_name = parts[-1]

    suffix = r"\.tgz(\.integrity)?$"

    if len(parts) >= 2 and plugin_name in ("frontend", "backend"):
        parent_name = re.escape(parts[-2])
        if plugin_name == "backend":
            return re.compile(rf"{parent_name}.*-backend(-dynamic)?-\d.*{suffix}")
        return re.compile(rf"{parent_name}(?!.*-backend).*(-dynamic)?-\d.*{suffix}")

    return re.compile(rf"-{re.escape(plugin_name)}(-dynamic)?-\d.*{suffix}")


def get_output_tgz_files(output_dir: Path) -> list[Path]:
    """Return all ``.tgz`` files in ``output_dir`` (sorted)."""
    return sorted(output_dir.glob("*.tgz"))


def get_output_integrity_files(output_dir: Path) -> list[Path]:
    """Return all ``.tgz.integrity`` files in ``output_dir`` (sorted)."""
    return sorted(output_dir.glob("*.tgz.integrity"))


def find_outputs_for_plugin(
    plugin_path: str,
    output_files: list[Path],
) -> list[Path]:
    """Return files from *output_files* whose names match *plugin_path*.

    Works for both ``.tgz`` and ``.tgz.integrity`` files.
    """
    pattern = plugin_path_to_output_pattern(plugin_path)
    return [f for f in output_files if pattern.search(f.name)]


def _collect_log_errors(output: str) -> list[str]:
    """Scan combined container output for known error indicators."""
    errors: list[str] = []

    for pattern in _ERROR_PATTERNS:
        if pattern in output:
            errors.append(f"Found error pattern: '{pattern}'")

    if _FAILED_EXPORTS_MARKER not in output:
        return errors

    for line in output.splitlines():
        if _FAILED_EXPORTS_MARKER not in line:
            continue
        exports_part = line.split(_FAILED_EXPORTS_MARKER)[-1].strip()
        if exports_part:
            errors.append(f"Failed plugin exports: {exports_part}")
        break

    return errors


def assert_no_errors_in_logs(result: ContainerResult) -> None:
    """Fail the test if the container logs contain error indicators."""
    errors = _collect_log_errors(result.output)
    if not errors:
        return

    max_tail = 3000
    tail = result.output[-max_tail:]
    pytest.fail(
        "Errors detected in container logs:\n"
        + "\n".join(f"  - {e}" for e in errors)
        + f"\n\nFull log: {result.log_file}"
        + f"\n\n--- container output (last {max_tail} chars) ---\n{tail}"
    )


# ---------------------------------------------------------------------------
# Base test class
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class PluginBuildTests:
    """Reusable test suite for single-workspace plugin builds.

    Subclasses must provide two class-scoped fixtures:

    - ``container_result`` -> :class:`ContainerResult`
    - ``expected_plugins`` -> ``list[str]``
    """

    def test_container_exits_successfully(self, container_result: ContainerResult) -> None:
        assert container_result.returncode == 0, (
            f"Container exited with code {container_result.returncode}\n"
            f"Full log: {container_result.log_file}\n"
            f"output:\n{container_result.output[-3000:]}"
        )

    def test_no_errors_in_logs(self, container_result: ContainerResult) -> None:
        assert_no_errors_in_logs(container_result)

    def test_all_plugins_produce_tgz(
        self,
        container_result: ContainerResult,
        expected_plugins: list[str],
    ) -> None:
        tgz_files = get_output_tgz_files(container_result.output_dir)

        for plugin_path in expected_plugins:
            matches = find_outputs_for_plugin(plugin_path, tgz_files)
            assert matches, (
                f"No .tgz output found for plugin '{plugin_path}'\n"
                f"Available tgz files: {[f.name for f in tgz_files]}"
            )

    def test_all_plugins_produce_integrity(
        self,
        container_result: ContainerResult,
        expected_plugins: list[str],
    ) -> None:
        integrity_files = get_output_integrity_files(container_result.output_dir)

        for plugin_path in expected_plugins:
            matches = find_outputs_for_plugin(plugin_path, integrity_files)
            assert matches, (
                f"No .tgz.integrity output found for plugin '{plugin_path}'\n"
                f"Available integrity files: {[f.name for f in integrity_files]}"
            )

    def test_output_tarballs_are_nonzero(
        self, container_result: ContainerResult
    ) -> None:
        tgz_files = get_output_tgz_files(container_result.output_dir)
        assert tgz_files, "No .tgz files found in output directory"

        for tgz in tgz_files:
            assert tgz.stat().st_size > 0, f"Tarball is empty: {tgz.name}"

    def test_output_count_matches_plugins(
        self,
        container_result: ContainerResult,
        expected_plugins: list[str],
    ) -> None:
        tgz_files = get_output_tgz_files(container_result.output_dir)
        assert len(tgz_files) >= len(expected_plugins), (
            f"Expected at least {len(expected_plugins)} tgz outputs "
            f"(one per plugin), got {len(tgz_files)}.\n"
            f"Plugins: {expected_plugins}\n"
            f"Outputs: {[f.name for f in tgz_files]}"
        )


@pytest.mark.e2e
class MultiWorkspaceBuildTests:
    """Reusable test suite for multi-workspace plugin builds.

    Subclasses must provide:

    - Class attribute ``WORKSPACES`` -> ``list[str]``
    - Class-scoped fixture ``container_result`` -> :class:`ContainerResult`
    - Class-scoped fixture ``config_dir`` -> :class:`Path`
      (directory containing per-workspace subdirectories with configs)

    The ``workspace`` test parameter is automatically parametrized via the
    :func:`pytest_generate_tests` hook using the ``WORKSPACES`` attribute.
    """

    WORKSPACES: list[str] = []

    def test_container_exits_successfully(self, container_result: ContainerResult) -> None:
        assert container_result.returncode == 0, (
            f"Container exited with code {container_result.returncode}\n"
            f"Full log: {container_result.log_file}\n"
            f"output:\n{container_result.output[-3000:]}"
        )

    def test_no_errors_in_logs(self, container_result: ContainerResult) -> None:
        assert_no_errors_in_logs(container_result)

    def test_workspace_produces_tgz(
        self,
        container_result: ContainerResult,
        config_dir: Path,
        workspace: str,
    ) -> None:
        expected_plugins = parse_plugins_from_config(config_dir / workspace)
        tgz_files = get_output_tgz_files(container_result.output_dir / workspace)

        for plugin_path in expected_plugins:
            matches = find_outputs_for_plugin(plugin_path, tgz_files)
            assert matches, (
                f"[{workspace}] No .tgz output found for plugin '{plugin_path}'\n"
                f"Available tgz files: {[f.name for f in tgz_files]}"
            )

    def test_workspace_produces_integrity(
        self,
        container_result: ContainerResult,
        config_dir: Path,
        workspace: str,
    ) -> None:
        expected_plugins = parse_plugins_from_config(config_dir / workspace)
        integrity_files = get_output_integrity_files(
            container_result.output_dir / workspace
        )

        for plugin_path in expected_plugins:
            matches = find_outputs_for_plugin(plugin_path, integrity_files)
            assert matches, (
                f"[{workspace}] No .tgz.integrity output found for plugin "
                f"'{plugin_path}'\n"
                f"Available integrity files: {[f.name for f in integrity_files]}"
            )

    def test_workspace_tarballs_are_nonzero(
        self,
        container_result: ContainerResult,
        workspace: str,
    ) -> None:
        tgz_files = get_output_tgz_files(container_result.output_dir / workspace)
        assert tgz_files, f"[{workspace}] No .tgz files found in output directory"

        for tgz in tgz_files:
            assert tgz.stat().st_size > 0, f"[{workspace}] Tarball is empty: {tgz.name}"

    def test_workspace_output_count_matches_plugins(
        self,
        container_result: ContainerResult,
        config_dir: Path,
        workspace: str,
    ) -> None:
        expected_plugins = parse_plugins_from_config(config_dir / workspace)
        tgz_files = get_output_tgz_files(container_result.output_dir / workspace)
        assert len(tgz_files) >= len(expected_plugins), (
            f"[{workspace}] Expected at least {len(expected_plugins)} tgz outputs "
            f"(one per plugin), got {len(tgz_files)}.\n"
            f"Plugins: {expected_plugins}\n"
            f"Outputs: {[f.name for f in tgz_files]}"
        )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize ``workspace`` from the test class's ``WORKSPACES`` attribute."""
    if "workspace" in metafunc.fixturenames:
        cls = metafunc.cls
        if cls and hasattr(cls, "WORKSPACES"):
            metafunc.parametrize("workspace", cls.WORKSPACES)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def container_image() -> str:
    """Container image to test — read from ``E2E_IMAGE`` (required)."""
    image = os.environ.get("E2E_IMAGE")
    if not image:
        pytest.fail(
            "E2E_IMAGE environment variable is required but not set.\n"
            "Set it to the PR container image to test, e.g.:\n"
            "  E2E_IMAGE=quay.io/rhdh-community/dynamic-plugins-factory:pr-42 "
            "pytest tests/e2e/ -m e2e"
        )
    return image


@pytest.fixture(scope="session")
def container_runtime() -> str:
    """Container runtime binary — read from ``E2E_CONTAINER_RUNTIME`` (default: podman)."""
    runtime = os.environ.get("E2E_CONTAINER_RUNTIME", "podman")
    if not shutil.which(runtime):
        pytest.fail(
            f"Container runtime '{runtime}' not found on $PATH.\n"
            f"Install {runtime} or set E2E_CONTAINER_RUNTIME to an available runtime."
        )
    return runtime


@pytest.fixture(scope="session")
def e2e_log_dir() -> Path:
    """Directory where container logs are persisted."""
    log_dir = Path(os.environ.get("E2E_LOG_DIR", str(DEFAULT_LOG_DIR)))
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


@pytest.fixture(scope="session")
def run_factory_container(
    container_image: str,
    container_runtime: str,
    tmp_path_factory: pytest.TempPathFactory,
    e2e_log_dir: Path,
):
    """Factory fixture: call the returned function to run the container.

    Each call creates a fresh output directory, persists the container log
    to ``E2E_LOG_DIR``, and returns a :class:`ContainerResult`.
    """

    def _run(
        config_dir: Path,
        extra_args: Optional[list[str]] = None,
        timeout: int = CONTAINER_TIMEOUT,
    ) -> ContainerResult:
        output_dir = tmp_path_factory.mktemp("outputs")
        log_name = config_dir.parent.name if config_dir.name == "config" else config_dir.name
        log_file = e2e_log_dir / f"{log_name}.log"

        cmd = [
            container_runtime,
            "run",
            "--rm",
            "--device", "/dev/fuse",
            "-v", f"{config_dir}:/config:z",
            "-v", f"{output_dir}:/outputs:z",
            container_image,
        ]
        if extra_args:
            cmd.extend(extra_args)

        completed = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
        log_file.write_text(completed.stdout)

        return ContainerResult(
            returncode=completed.returncode,
            output=completed.stdout,
            output_dir=output_dir,
            log_file=log_file,
        )

    return _run
