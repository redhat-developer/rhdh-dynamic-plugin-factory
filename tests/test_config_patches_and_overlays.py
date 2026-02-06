"""
Unit tests for PluginFactoryConfig.apply_patches_and_overlays method.

Tests the patch and overlay application functionality.
"""

import os
from pathlib import Path
from unittest.mock import patch

from src.rhdh_dynamic_plugin_factory.config import PluginFactoryConfig


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
                
                result = config.apply_patches_and_overlays()
                
                assert result is True
                
                mock_run_cmd.assert_called_once()
                call_args = mock_run_cmd.call_args
                
                cmd = call_args[0][0]
                assert len(cmd) == 3
                assert cmd[0] == str(script_path.absolute())
                assert cmd[1] == os.path.abspath(config.config_dir)
                expected_workspace = os.path.abspath(os.path.join(config.repo_path, config.workspace_path))
                assert cmd[2] == expected_workspace
                
                assert call_args[0][1] == config.logger
                assert call_args[1]["cwd"] == Path(expected_workspace)
                assert call_args[1]["stderr_log_func"] == config.logger.error
    
    def test_apply_patches_and_overlays_script_not_found(self, make_config):
        """Test that apply_patches_and_overlays returns False when script doesn't exist."""
        config = make_config()
        
        with patch.object(Path, "exists", return_value=False):
            with patch.object(config, "logger") as mock_logger:
                result = config.apply_patches_and_overlays()
                
                assert result is False
                
                mock_logger.error.assert_called_once()
                error_msg = mock_logger.error.call_args[0][0]
                assert "Script not found" in error_msg
    
    def test_apply_patches_and_overlays_script_fails(self, make_config):
        """Test that apply_patches_and_overlays returns False when script returns non-zero exit code."""
        config = make_config()
        
        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run_cmd:
            with patch.object(Path, "exists", return_value=True):
                with patch.object(config, "logger") as mock_logger:
                    mock_run_cmd.return_value = 1
                    
                    result = config.apply_patches_and_overlays()
                    
                    assert result is False
                    
                    error_calls = [call[0][0] for call in mock_logger.error.call_args_list]
                    assert any("exit code 1" in str(call) for call in error_calls)
    
    def test_apply_patches_and_overlays_exception(self, make_config):
        """Test that apply_patches_and_overlays handles exceptions gracefully."""
        config = make_config()
        
        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run_cmd:
            with patch.object(Path, "exists", return_value=True):
                with patch.object(config, "logger") as mock_logger:
                    mock_run_cmd.side_effect = Exception("Test exception")
                    
                    result = config.apply_patches_and_overlays()
                    
                    assert result is False
                    
                    mock_logger.error.assert_called()
                    error_msg = mock_logger.error.call_args[0][0]
                    assert "Failed to run patch script" in error_msg
                    assert "Test exception" in error_msg
