"""
E2E tests for the TODO single-workspace example.

Runs the factory container with the todo fixture config and validates that
both frontend and backend plugins are built successfully.
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

TODO_CONFIG_DIR = FIXTURES_DIR / "todo" / "config"


@pytest.fixture(scope="class")
def todo_result(run_factory_container) -> ContainerResult:
    """Run the factory container once for the todo fixture; shared by the class."""
    return run_factory_container(TODO_CONFIG_DIR)


@pytest.fixture(scope="class")
def expected_plugins() -> list[str]:
    """Plugin paths parsed from the todo fixture's plugins-list.yaml."""
    return parse_plugins_from_config(TODO_CONFIG_DIR)


@pytest.mark.e2e
class TestTodoSingleWorkspace:
    """Validate a full container run of the TODO single-workspace example."""

    def test_container_exits_successfully(self, todo_result: ContainerResult) -> None:
        assert todo_result.returncode == 0, (
            f"Container exited with code {todo_result.returncode}\n"
            f"Full log: {todo_result.log_file}\n"
            f"output:\n{todo_result.output[-3000:]}"
        )

    def test_no_errors_in_logs(self, todo_result: ContainerResult) -> None:
        assert_no_errors_in_logs(todo_result)

    def test_all_plugins_produce_tgz(
        self,
        todo_result: ContainerResult,
        expected_plugins: list[str],
    ) -> None:
        tgz_files = get_output_tgz_files(todo_result.output_dir)

        for plugin_path in expected_plugins:
            matches = find_outputs_for_plugin(plugin_path, tgz_files)
            assert matches, (
                f"No .tgz output found for plugin '{plugin_path}'\n"
                f"Available tgz files: {[f.name for f in tgz_files]}"
            )

    def test_all_plugins_produce_integrity(
        self,
        todo_result: ContainerResult,
        expected_plugins: list[str],
    ) -> None:
        integrity_files = get_output_integrity_files(todo_result.output_dir)

        for plugin_path in expected_plugins:
            plugin_name = plugin_path.split("/")[-1]
            matches = [f for f in integrity_files if plugin_name in f.name]
            assert matches, (
                f"No .tgz.integrity output found for plugin '{plugin_path}'\n"
                f"Available integrity files: {[f.name for f in integrity_files]}"
            )

    def test_output_tarballs_are_nonzero(
        self, todo_result: ContainerResult
    ) -> None:
        tgz_files = get_output_tgz_files(todo_result.output_dir)
        assert tgz_files, "No .tgz files found in output directory"

        for tgz in tgz_files:
            assert tgz.stat().st_size > 0, f"Tarball is empty: {tgz.name}"

    def test_output_count_matches_plugins(
        self,
        todo_result: ContainerResult,
        expected_plugins: list[str],
    ) -> None:
        tgz_files = get_output_tgz_files(todo_result.output_dir)
        assert len(tgz_files) >= len(expected_plugins), (
            f"Expected at least {len(expected_plugins)} tgz outputs "
            f"(one per plugin), got {len(tgz_files)}.\n"
            f"Plugins: {expected_plugins}\n"
            f"Outputs: {[f.name for f in tgz_files]}"
        )
