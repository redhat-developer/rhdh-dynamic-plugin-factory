"""
Unit tests for PluginFactoryConfig.export_plugins method.

Tests the plugin export functionality including environment variable setup
and script execution.
"""

import os
from pathlib import Path
from unittest.mock import patch
import pytest

from src.rhdh_dynamic_plugin_factory.exceptions import ExecutionError, PluginFactoryError

class TestExportPlugins:
    """Tests for PluginFactoryConfig.export_plugins method."""
    
    def test_export_plugins_success(self, make_config, setup_test_env):
        """Test successful execution of export_plugins."""
        config = make_config(
            registry_url="quay.io",
            registry_namespace="test-namespace"
        )
        
        output_dir = str(setup_test_env["tmp_path"] / "output")
        
        with patch.object(Path, "exists", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run_cmd:
                    with patch("src.rhdh_dynamic_plugin_factory.config.display_export_results") as mock_display:
                        with patch("src.rhdh_dynamic_plugin_factory.config.load_dotenv"):
                            mock_run_cmd.return_value = 0
                            mock_display.return_value = False
                            
                            config.export_plugins(output_dir, push_images=False)  # Should not raise any exceptions
                            
                            mock_run_cmd.assert_called_once()
                            call_args = mock_run_cmd.call_args
                            
                            cmd = call_args[0][0]
                            assert len(cmd) == 1
                            assert "export-workspace.sh" in cmd[0]
                            
                            assert call_args[0][1] == config.logger
                            
                            expected_workspace = os.path.abspath(os.path.join(config.repo_path, config.workspace_path))
                            assert call_args[1]["cwd"] == Path(expected_workspace)
                            
                            env = call_args[1]["env"]
                            assert "INPUTS_DESTINATION" in env
                            assert "INPUTS_PLUGINS_FILE" in env
                            assert "INPUTS_PUSH_CONTAINER_IMAGE" in env
    
    def test_export_plugins_environment_variables_no_push(self, make_config, setup_test_env):
        """Test that environment variables are correctly set when push_images is False."""
        config = make_config(
            registry_url="quay.io",
            registry_namespace="test-namespace"
        )
        
        tmp_path = setup_test_env["tmp_path"]
        output_dir = str(tmp_path / "output")
        
        with patch.object(Path, "exists", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run_cmd:
                    with patch("src.rhdh_dynamic_plugin_factory.config.display_export_results") as mock_display:
                        with patch("src.rhdh_dynamic_plugin_factory.config.load_dotenv"):
                            mock_run_cmd.return_value = 0
                            mock_display.return_value = False
                            
                            _result = config.export_plugins(output_dir, push_images=False)
                            
                            env = mock_run_cmd.call_args[1]["env"]
                            
                            assert env["INPUTS_SCALPRUM_CONFIG_FILE_NAME"] == "scalprum-config.json"
                            assert env["INPUTS_SOURCE_OVERLAY_FOLDER_NAME"] == "overlay"
                            assert env["INPUTS_SOURCE_PATCH_FILE_NAME"] == "patch"
                            assert env["INPUTS_APP_CONFIG_FILE_NAME"] == "app-config.dynamic.yaml"
                            assert env["INPUTS_CLI_PACKAGE"] == "@red-hat-developer-hub/cli"
                            assert env["INPUTS_PUSH_CONTAINER_IMAGE"] == "false"
                            assert env["INPUTS_JANUS_CLI_VERSION"] == "1.7.2"
                            assert env["INPUTS_IMAGE_REPOSITORY_PREFIX"] == "quay.io/test-namespace"
                            assert env["INPUTS_CONTAINER_BUILD_TOOL"] == "buildah"
                            assert str((tmp_path / "output").absolute()) in env["INPUTS_DESTINATION"]
                            assert "plugins-list.yaml" in env["INPUTS_PLUGINS_FILE"]
    
    def test_export_plugins_environment_variables_with_push(self, make_config, setup_test_env):
        """Test that environment variables are correctly set when push_images is True."""
        config = make_config(
            registry_url="quay.io",
            registry_namespace="test-namespace"
        )
        
        output_dir = str(setup_test_env["tmp_path"] / "output")
        
        with patch.object(Path, "exists", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run_cmd:
                    with patch("src.rhdh_dynamic_plugin_factory.config.display_export_results") as mock_display:
                        with patch("src.rhdh_dynamic_plugin_factory.config.load_dotenv"):
                            mock_run_cmd.return_value = 0
                            mock_display.return_value = False
                            
                            _result = config.export_plugins(output_dir, push_images=True)
                            
                            env = mock_run_cmd.call_args[1]["env"]
                            assert env["INPUTS_PUSH_CONTAINER_IMAGE"] == "true"
    
    def test_export_plugins_default_registry_values(self, make_config, setup_test_env):
        """Test that default values are used when registry_url or registry_namespace are None."""
        config = make_config(
            registry_url=None,
            registry_namespace=None
        )
        
        output_dir = str(setup_test_env["tmp_path"] / "output")
        
        with patch.object(Path, "exists", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run_cmd:
                    with patch("src.rhdh_dynamic_plugin_factory.config.display_export_results") as mock_display:
                        with patch("src.rhdh_dynamic_plugin_factory.config.load_dotenv"):
                            mock_run_cmd.return_value = 0
                            mock_display.return_value = False
                            
                            _result = config.export_plugins(output_dir, push_images=False)
                            
                            env = mock_run_cmd.call_args[1]["env"]
                            assert env["INPUTS_IMAGE_REPOSITORY_PREFIX"] == "localhost/default"
    
    def test_export_plugins_script_not_found(self, make_config, setup_test_env):
        """Test that export_plugins raises ExecutionError when script doesn't exist."""
        config = make_config()
        
        output_dir = str(setup_test_env["tmp_path"] / "output")
        
        with patch.object(Path, "exists", return_value=False):
            with pytest.raises(ExecutionError, match="Script not found"):
                config.export_plugins(output_dir, push_images=False)
    
    def test_export_plugins_no_plugins_list(self, make_config, setup_test_env):
        """Test that export_plugins raises PluginFactoryError when plugins-list.yaml doesn't exist."""
        config = make_config()
        
        output_dir = str(setup_test_env["tmp_path"] / "output")
        
        original_path_exists = Path.exists
        
        def path_exists_side_effect(path_obj):
            if "export-workspace.sh" in str(path_obj):
                return True
            return original_path_exists(path_obj)
        
        def os_exists_side_effect(path_str):
            if "plugins-list.yaml" in str(path_str):
                return False
            return True
        
        with patch.object(Path, "exists", new=path_exists_side_effect):
            with patch("os.path.exists", side_effect=os_exists_side_effect):
                with pytest.raises(PluginFactoryError, match="No plugins file found"):
                    config.export_plugins(output_dir, push_images=False)
    
    def test_export_plugins_script_fails(self, make_config, setup_test_env):
        """Test that export_plugins raises ExecutionError when script returns non-zero exit code."""
        config = make_config(
            registry_url="quay.io",
            registry_namespace="test-namespace"
        )
        
        output_dir = str(setup_test_env["tmp_path"] / "output")
        
        with patch.object(Path, "exists", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run_cmd:
                    with patch("src.rhdh_dynamic_plugin_factory.config.load_dotenv"):
                        mock_run_cmd.return_value = 1
                        
                        with pytest.raises(ExecutionError, match="exit code 1"):
                            config.export_plugins(output_dir, push_images=False)
    
    def test_export_plugins_has_failures(self, make_config, setup_test_env):
        """Test that export_plugins raises ExecutionError when display_export_results indicates failures."""
        config = make_config(
            registry_url="quay.io",
            registry_namespace="test-namespace"
        )
        
        output_dir = str(setup_test_env["tmp_path"] / "output")
        
        with patch.object(Path, "exists", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run_cmd:
                    with patch("src.rhdh_dynamic_plugin_factory.config.display_export_results") as mock_display:
                        with patch("src.rhdh_dynamic_plugin_factory.config.load_dotenv"):
                            mock_run_cmd.return_value = 0
                            mock_display.return_value = True
                            
                            with pytest.raises(ExecutionError, match="completed with failures"):
                                config.export_plugins(output_dir, push_images=False)
    
    def test_export_plugins_exception(self, make_config, setup_test_env):
        """Test that export_plugins wraps exceptions in ExecutionError."""
        config = make_config()
        
        output_dir = str(setup_test_env["tmp_path"] / "output")
        
        with patch.object(Path, "exists", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run_cmd:
                    with patch("src.rhdh_dynamic_plugin_factory.config.load_dotenv"):
                        mock_run_cmd.side_effect = Exception("Test exception")
                        
                        with pytest.raises(ExecutionError, match="Failed to run export script.*Test exception"):
                            config.export_plugins(output_dir, push_images=False)
    
    def test_export_plugins_custom_env_file(self, make_config, setup_test_env):
        """Test that export_plugins loads custom .env file from config directory."""
        config = make_config(
            registry_url="quay.io",
            registry_namespace="test-namespace"
        )
        
        custom_env = Path(setup_test_env["config_dir"]) / ".env"
        custom_env.write_text("CUSTOM_VAR=custom_value\n")
        
        output_dir = str(setup_test_env["tmp_path"] / "output")
        
        with patch.object(Path, "exists", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run_cmd:
                    with patch("src.rhdh_dynamic_plugin_factory.config.display_export_results") as mock_display:
                        with patch("src.rhdh_dynamic_plugin_factory.config.load_dotenv") as mock_load_dotenv:
                            with patch.object(config, "logger") as mock_logger:
                                mock_run_cmd.return_value = 0
                                mock_display.return_value = False
                                
                                _result = config.export_plugins(output_dir, push_images=False)
                                
                                assert mock_load_dotenv.call_count >= 1
                                
                                debug_calls = [call[0][0] for call in mock_logger.debug.call_args_list]
                                assert any(".env" in str(call) for call in debug_calls)
