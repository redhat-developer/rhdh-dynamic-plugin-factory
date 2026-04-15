"""
E2E tests for the multi-workspace build-arg auto-generation flow.

Runs the factory container with two workspaces (aws-ecs and backstage), each
containing a bare plugins-list.yaml (plugin paths only, no build arguments)
and ``--generate-build-args`` so the factory computes embed/shared/suppress
flags via dependency analysis.  Validates that the resulting plugins-list.yaml
for each workspace matches the expected output and that all plugins are built
successfully.
"""

import shutil
from pathlib import Path

import pytest
import yaml

from .conftest import (
    FIXTURES_DIR,
    ContainerResult,
    MultiWorkspaceBuildTests,
)

FIXTURE_DIR = FIXTURES_DIR / "multi-workspace-auto-gen"


@pytest.fixture(scope="class")
def config_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copy the fixture to a temp directory so the container can write to it.

    ``--generate-build-args`` overwrites ``plugins-list.yaml`` in-place, so we
    need a mutable copy to avoid polluting the fixture on disk.
    """
    dest = tmp_path_factory.mktemp("multi-ws-auto-gen-config")
    shutil.copytree(FIXTURE_DIR, dest, dirs_exist_ok=True)
    return dest


@pytest.fixture(scope="class")
def container_result(run_factory_container, config_dir) -> ContainerResult:
    """Run the factory container once with --generate-build-args."""
    return run_factory_container(
        config_dir,
        extra_args=["--generate-build-args"],
    )


@pytest.mark.e2e
class TestMultiWorkspaceAutoGen(MultiWorkspaceBuildTests):
    """Validate build-arg generation and build output across workspaces."""

    WORKSPACES = ["aws-ecs", "backstage"]

    def test_generated_build_args_match_expected(
        self,
        config_dir: Path,
        workspace: str,
    ) -> None:
        generated = yaml.safe_load(
            (config_dir / workspace / "plugins-list.yaml").read_text()
        )
        expected = yaml.safe_load(
            (FIXTURE_DIR / workspace / "expected-plugins-list.yaml").read_text()
        )
        assert generated == expected, (
            f"[{workspace}] plugins-list.yaml after --generate-build-args "
            f"does not match expected.\n"
            f"Generated: {generated}\n"
            f"Expected:  {expected}"
        )
