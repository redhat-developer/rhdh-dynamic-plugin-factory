"""
E2E tests for the multi-workspace example.

Runs the factory container with a config containing two workspaces (todo and
aws-ecs) and validates that patches, overlays, and per-workspace outputs all
work correctly.
"""

from pathlib import Path

import pytest

from .conftest import (
    FIXTURES_DIR,
    ContainerResult,
    MultiWorkspaceBuildTests,
)

MULTI_WS_CONFIG_DIR = FIXTURES_DIR / "multi-workspace"


@pytest.fixture(scope="class")
def container_result(run_factory_container) -> ContainerResult:
    """Run the factory container once for the multi-workspace fixture."""
    return run_factory_container(MULTI_WS_CONFIG_DIR)


@pytest.fixture(scope="class")
def config_dir() -> Path:
    return MULTI_WS_CONFIG_DIR


@pytest.mark.e2e
class TestMultiWorkspace(MultiWorkspaceBuildTests):
    """Validate a full container run of the multi-workspace example."""

    WORKSPACES = ["todo", "aws-ecs"]
