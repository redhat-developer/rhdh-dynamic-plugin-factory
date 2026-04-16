"""
Unit tests for PluginFactoryConfig.apply_patches_and_overlays method.

Tests the patch and overlay application functionality.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from src.rhdh_dynamic_plugin_factory.exceptions import ExecutionError


class TestApplyPatchesAndOverlays:
    """Tests for PluginFactoryConfig.apply_patches_and_overlays method."""

    def test_apply_patches_and_overlays_success(self, make_config):
        """Test successful execution of apply_patches_and_overlays."""
        config = make_config()

        script_dir = Path(__file__).parent.parent / "scripts"
        script_path = script_dir / "override-sources.sh"

        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run_cmd:
            with patch.object(Path, "exists", return_value=True):
                mock_run_cmd.return_value = 0

                config.apply_patches_and_overlays()  # Should not raise any exceptions

                mock_run_cmd.assert_called_once()
                call_args = mock_run_cmd.call_args

                cmd = call_args[0][0]
                expected_repo_root = os.path.abspath(config.repo_path)
                expected_workspace = os.path.abspath(os.path.join(config.repo_path, config.workspace_path))
                assert len(cmd) == 3
                assert cmd[0] == str(script_path.absolute())
                assert cmd[1] == os.path.abspath(config.config_dir)
                assert cmd[2] == expected_workspace

                assert call_args[0][1] == config.logger
                assert call_args[1]["cwd"] == Path(expected_repo_root)
                assert call_args[1]["stderr_log_func"] == config.logger.error

    def test_apply_patches_and_overlays_script_not_found(self, make_config):
        """Test that apply_patches_and_overlays raises ExecutionError when script doesn't exist."""
        config = make_config()

        with patch.object(Path, "exists", return_value=False):
            with pytest.raises(ExecutionError, match="Script not found"):
                config.apply_patches_and_overlays()

    def test_apply_patches_and_overlays_script_fails(self, make_config):
        """Test that apply_patches_and_overlays raises ExecutionError when script returns non-zero exit code."""
        config = make_config()

        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run_cmd:
            with patch.object(Path, "exists", return_value=True):
                mock_run_cmd.return_value = 1

                with pytest.raises(ExecutionError, match="exit code 1"):
                    config.apply_patches_and_overlays()

    def test_apply_patches_and_overlays_exception(self, make_config):
        """Test that apply_patches_and_overlays wraps exceptions in ExecutionError."""
        config = make_config()

        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run_cmd:
            with patch.object(Path, "exists", return_value=True):
                mock_run_cmd.side_effect = Exception("Test exception")

                with pytest.raises(ExecutionError, match="Failed to run patch script.*Test exception"):
                    config.apply_patches_and_overlays()
