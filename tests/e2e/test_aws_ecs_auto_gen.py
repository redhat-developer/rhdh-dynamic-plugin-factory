"""
E2E tests for the AWS ECS build-arg auto-generation flow.

Runs the factory container with a bare plugins-list.yaml (plugin paths only,
no build arguments) and ``--generate-build-args`` so the factory computes
embed/shared/suppress flags via dependency analysis.  Validates that the
resulting plugins-list.yaml matches the expected output and that both ECS
plugins are built successfully.
"""

import shutil
from pathlib import Path

import pytest
import yaml

from .conftest import (
    FIXTURES_DIR,
    ContainerResult,
    assert_no_errors_in_logs,
    find_outputs_for_plugin,
    get_output_integrity_files,
    get_output_tgz_files,
    parse_plugins_from_config,
)

AUTO_GEN_FIXTURE_DIR = FIXTURES_DIR / "aws-ecs-auto-gen"


@pytest.fixture(scope="class")
def auto_gen_config_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copy the fixture to a temp directory so the container can write to it.

    ``--generate-build-args`` overwrites ``plugins-list.yaml`` in-place, so we
    need a mutable copy to avoid polluting the fixture on disk.
    """
    dest = tmp_path_factory.mktemp("auto-gen-config")
    shutil.copytree(AUTO_GEN_FIXTURE_DIR, dest, dirs_exist_ok=True)
    return dest


@pytest.fixture(scope="class")
def auto_gen_result(run_factory_container, auto_gen_config_dir) -> ContainerResult:
    """Run the factory container with --generate-build-args."""
    return run_factory_container(
        auto_gen_config_dir,
        extra_args=["--generate-build-args"],
    )


@pytest.fixture(scope="class")
def expected_plugins(auto_gen_config_dir) -> list[str]:
    """Plugin paths from the (now enriched) plugins-list.yaml."""
    return parse_plugins_from_config(auto_gen_config_dir)


@pytest.mark.e2e
class TestAwsEcsAutoGen:
    """Validate build-arg generation and build output for the AWS ECS plugins."""

    def test_container_exits_successfully(self, auto_gen_result: ContainerResult) -> None:
        assert auto_gen_result.returncode == 0, (
            f"Container exited with code {auto_gen_result.returncode}\n"
            f"Full log: {auto_gen_result.log_file}\n"
            f"output:\n{auto_gen_result.output[-3000:]}"
        )

    def test_no_errors_in_logs(self, auto_gen_result: ContainerResult) -> None:
        assert_no_errors_in_logs(auto_gen_result)

    def test_generated_build_args_match_expected(self, auto_gen_config_dir) -> None:
        generated = yaml.safe_load(
            (auto_gen_config_dir / "plugins-list.yaml").read_text()
        )
        expected = yaml.safe_load(
            (AUTO_GEN_FIXTURE_DIR / "expected-plugins-list.yaml").read_text()
        )
        assert generated == expected, (
            "plugins-list.yaml after --generate-build-args does not match expected.\n"
            f"Generated: {generated}\n"
            f"Expected:  {expected}"
        )

    def test_all_plugins_produce_tgz(
        self,
        auto_gen_result: ContainerResult,
        expected_plugins: list[str],
    ) -> None:
        tgz_files = get_output_tgz_files(auto_gen_result.output_dir)

        for plugin_path in expected_plugins:
            matches = find_outputs_for_plugin(plugin_path, tgz_files)
            assert matches, (
                f"No .tgz output found for plugin '{plugin_path}'\n"
                f"Available tgz files: {[f.name for f in tgz_files]}"
            )

    def test_all_plugins_produce_integrity(
        self,
        auto_gen_result: ContainerResult,
        expected_plugins: list[str],
    ) -> None:
        integrity_files = get_output_integrity_files(auto_gen_result.output_dir)

        for plugin_path in expected_plugins:
            matches = find_outputs_for_plugin(plugin_path, integrity_files)
            assert matches, (
                f"No .tgz.integrity output found for plugin '{plugin_path}'\n"
                f"Available integrity files: {[f.name for f in integrity_files]}"
            )

    def test_output_tarballs_are_nonzero(
        self, auto_gen_result: ContainerResult
    ) -> None:
        tgz_files = get_output_tgz_files(auto_gen_result.output_dir)
        assert tgz_files, "No .tgz files found in output directory"

        for tgz in tgz_files:
            assert tgz.stat().st_size > 0, f"Tarball is empty: {tgz.name}"

    def test_output_count_matches_plugins(
        self,
        auto_gen_result: ContainerResult,
        expected_plugins: list[str],
    ) -> None:
        tgz_files = get_output_tgz_files(auto_gen_result.output_dir)
        assert len(tgz_files) >= len(expected_plugins), (
            f"Expected at least {len(expected_plugins)} tgz outputs "
            f"(one per plugin), got {len(tgz_files)}.\n"
            f"Plugins: {expected_plugins}\n"
            f"Outputs: {[f.name for f in tgz_files]}"
        )
