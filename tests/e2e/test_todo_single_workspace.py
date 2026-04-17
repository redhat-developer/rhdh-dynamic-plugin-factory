"""
E2E tests for the TODO single-workspace example.

Runs the factory container with the todo fixture config and validates that
both frontend and backend plugins are built successfully.
"""

import pytest

from .conftest import (
    FIXTURES_DIR,
    ContainerResult,
    PluginBuildTests,
    parse_plugins_from_config,
)

TODO_CONFIG_DIR = FIXTURES_DIR / "todo" / "config"


@pytest.fixture(scope="class")
def container_result(run_factory_container) -> ContainerResult:
    """Run the factory container once for the todo fixture; shared by the class."""
    return run_factory_container(TODO_CONFIG_DIR)


@pytest.fixture(scope="class")
def expected_plugins() -> list[str]:
    """Plugin paths parsed from the todo fixture's plugins-list.yaml."""
    return parse_plugins_from_config(TODO_CONFIG_DIR)


@pytest.mark.e2e
class TestTodoSingleWorkspace(PluginBuildTests):
    """Validate a full container run of the TODO single-workspace example."""
