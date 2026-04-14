"""
E2E tests for the Backstage core repo build-arg auto-generation flow.

Runs the factory container with a bare plugins-list.yaml (plugin paths only,
no build arguments) and ``--generate-build-args`` so the factory computes
embed/shared flags via dependency analysis.  Validates that the resulting
plugins-list.yaml matches the expected output and that all four plugins are
built successfully.
"""

import shutil
from pathlib import Path

import pytest
import yaml

from .conftest import (
    FIXTURES_DIR,
    ContainerResult,
    PluginBuildTests,
    parse_plugins_from_config,
)

BACKSTAGE_FIXTURE_DIR = FIXTURES_DIR / "backstage-auto-gen"


@pytest.fixture(scope="class")
def backstage_config_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copy the fixture to a temp directory so the container can write to it.

    ``--generate-build-args`` overwrites ``plugins-list.yaml`` in-place, so we
    need a mutable copy to avoid polluting the fixture on disk.
    """
    dest = tmp_path_factory.mktemp("backstage-auto-gen-config")
    shutil.copytree(BACKSTAGE_FIXTURE_DIR, dest, dirs_exist_ok=True)
    return dest


@pytest.fixture(scope="class")
def container_result(run_factory_container, backstage_config_dir) -> ContainerResult:
    """Run the factory container with --generate-build-args."""
    return run_factory_container(
        backstage_config_dir,
        extra_args=["--generate-build-args"],
    )


@pytest.fixture(scope="class")
def expected_plugins(backstage_config_dir) -> list[str]:
    """Plugin paths from the (now enriched) plugins-list.yaml."""
    return parse_plugins_from_config(backstage_config_dir)


@pytest.mark.e2e
class TestBackstageAutoGen(PluginBuildTests):
    """Validate build-arg generation and build output for Backstage core plugins."""

    def test_generated_build_args_match_expected(self, backstage_config_dir) -> None:
        generated = yaml.safe_load(
            (backstage_config_dir / "plugins-list.yaml").read_text()
        )
        expected = yaml.safe_load(
            (BACKSTAGE_FIXTURE_DIR / "expected-plugins-list.yaml").read_text()
        )
        assert generated == expected, (
            "plugins-list.yaml after --generate-build-args does not match expected.\n"
            f"Generated: {generated}\n"
            f"Expected:  {expected}"
        )
