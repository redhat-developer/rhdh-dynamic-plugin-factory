"""
E2E tests for the multi-workspace example.

Runs the factory container with a config containing two workspaces (todo and
aws-ecs) and validates that patches, overlays, and per-workspace outputs all
work correctly.
"""

import pytest

from .conftest import (
    FIXTURES_DIR,
    ContainerResult,
    assert_no_errors_in_logs,
    find_outputs_for_plugin,
    get_output_integrity_files,
    get_output_tgz_files,
    parse_plugins_from_config,
)

MULTI_WS_CONFIG_DIR = FIXTURES_DIR / "multi-workspace"
WORKSPACES = ["todo", "aws-ecs"]


@pytest.fixture(scope="class")
def multi_ws_result(run_factory_container) -> ContainerResult:
    """Run the factory container once for the multi-workspace fixture."""
    return run_factory_container(MULTI_WS_CONFIG_DIR)


@pytest.mark.e2e
class TestMultiWorkspace:
    """Validate a full container run of the multi-workspace example."""

    def test_container_exits_successfully(self, multi_ws_result: ContainerResult) -> None:
        assert multi_ws_result.returncode == 0, (
            f"Container exited with code {multi_ws_result.returncode}\n"
            f"Full log: {multi_ws_result.log_file}\n"
            f"output:\n{multi_ws_result.output[-3000:]}"
        )

    def test_no_errors_in_logs(self, multi_ws_result: ContainerResult) -> None:
        assert_no_errors_in_logs(multi_ws_result)

    @pytest.mark.parametrize("workspace", WORKSPACES)
    def test_workspace_produces_tgz(
        self,
        multi_ws_result: ContainerResult,
        workspace: str,
    ) -> None:
        expected_plugins = parse_plugins_from_config(MULTI_WS_CONFIG_DIR / workspace)
        tgz_files = get_output_tgz_files(multi_ws_result.output_dir / workspace)

        for plugin_path in expected_plugins:
            matches = find_outputs_for_plugin(plugin_path, tgz_files)
            assert matches, (
                f"[{workspace}] No .tgz output found for plugin '{plugin_path}'\n"
                f"Available tgz files: {[f.name for f in tgz_files]}"
            )

    @pytest.mark.parametrize("workspace", WORKSPACES)
    def test_workspace_produces_integrity(
        self,
        multi_ws_result: ContainerResult,
        workspace: str,
    ) -> None:
        expected_plugins = parse_plugins_from_config(MULTI_WS_CONFIG_DIR / workspace)
        integrity_files = get_output_integrity_files(multi_ws_result.output_dir / workspace)

        for plugin_path in expected_plugins:
            matches = find_outputs_for_plugin(plugin_path, integrity_files)
            assert matches, (
                f"[{workspace}] No .tgz.integrity output found for plugin '{plugin_path}'\n"
                f"Available integrity files: {[f.name for f in integrity_files]}"
            )

    @pytest.mark.parametrize("workspace", WORKSPACES)
    def test_workspace_tarballs_are_nonzero(
        self,
        multi_ws_result: ContainerResult,
        workspace: str,
    ) -> None:
        tgz_files = get_output_tgz_files(multi_ws_result.output_dir / workspace)
        assert tgz_files, f"[{workspace}] No .tgz files found in output directory"

        for tgz in tgz_files:
            assert tgz.stat().st_size > 0, f"[{workspace}] Tarball is empty: {tgz.name}"

    @pytest.mark.parametrize("workspace", WORKSPACES)
    def test_workspace_output_count_matches_plugins(
        self,
        multi_ws_result: ContainerResult,
        workspace: str,
    ) -> None:
        expected_plugins = parse_plugins_from_config(MULTI_WS_CONFIG_DIR / workspace)
        tgz_files = get_output_tgz_files(multi_ws_result.output_dir / workspace)
        assert len(tgz_files) >= len(expected_plugins), (
            f"[{workspace}] Expected at least {len(expected_plugins)} tgz outputs "
            f"(one per plugin), got {len(tgz_files)}.\n"
            f"Plugins: {expected_plugins}\n"
            f"Outputs: {[f.name for f in tgz_files]}"
        )
