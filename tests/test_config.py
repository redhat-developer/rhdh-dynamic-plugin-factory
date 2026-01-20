"""
Unit tests for PluginFactoryConfig class.

Tests the configuration loading, validation, and setup functionality
without executing shell scripts.
"""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import subprocess

from src.rhdh_dynamic_plugin_factory.config import PluginFactoryConfig


class TestPluginFactoryConfigLoadFromEnv:
    """Tests for PluginFactoryConfig.load_from_env method."""
    
    def test_load_from_env_valid_configuration(self, mock_args, setup_test_env, monkeypatch):
        """Test loading configuration with all required fields present."""
        # Update mock_args to use the setup_test_env paths
        mock_args.config_dir = setup_test_env["config_dir"]
        mock_args.repo_path = setup_test_env["source_dir"]
        mock_args.workspace_path = "."
        
        # Ensure environment variables are set
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        monkeypatch.setenv("WORKSPACE_PATH", ".")
        
        # Load configuration
        config = PluginFactoryConfig.load_from_env(mock_args)
        
        # Verify all required fields are set
        assert config.rhdh_cli_version == "1.7.2"
        assert config.log_level == "INFO"
        assert config.config_dir == setup_test_env["config_dir"]
        assert config.repo_path == setup_test_env["source_dir"]
        assert config.workspace_path == "."
        assert config.use_local is False
        
        # Verify directories exist
        assert os.path.exists(config.config_dir)
        assert os.path.exists(config.repo_path)
        
        # Verify path types are strings
        assert isinstance(config.config_dir, str)
        assert isinstance(config.repo_path, str)
        assert isinstance(config.workspace_path, str)
    
    def test_load_from_env_missing_rhdh_cli_version(self, mock_args, setup_test_env, clean_env):
        """Test that missing RHDH_CLI_VERSION raises ValueError."""
        # Don't set RHDH_CLI_VERSION
        clean_env.setenv("WORKSPACE_PATH", ".")
        
        mock_args.config_dir = setup_test_env["config_dir"]
        mock_args.repo_path = setup_test_env["source_dir"]
        mock_args.workspace_path = "."
        
        # Patch to prevent loading from default.env
        with patch.object(Path, 'exists', return_value=False):
            with pytest.raises(ValueError, match="RHDH_CLI_VERSION must be set"):
                PluginFactoryConfig.load_from_env(mock_args)
    
    def test_load_from_env_invalid_log_level(self, mock_args, setup_test_env, monkeypatch):
        """Test that invalid log level raises ValueError."""
        # Set required environment variables
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        monkeypatch.setenv("WORKSPACE_PATH", ".")
        monkeypatch.setenv("LOG_LEVEL", "INVALID_LEVEL")
        
        mock_args.config_dir = setup_test_env["config_dir"]
        mock_args.repo_path = setup_test_env["source_dir"]
        mock_args.workspace_path = "."
        mock_args.log_level = "INVALID_LEVEL"
        
        with pytest.raises(ValueError, match="Invalid log level"):
            PluginFactoryConfig.load_from_env(mock_args)
    
    @pytest.mark.parametrize("log_level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    def test_load_from_env_valid_log_levels(self, mock_args, setup_test_env, monkeypatch, log_level):
        """Test that all valid log levels are accepted."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        monkeypatch.setenv("WORKSPACE_PATH", ".")
        monkeypatch.setenv("LOG_LEVEL", log_level)
        
        mock_args.config_dir = setup_test_env["config_dir"]
        mock_args.repo_path = setup_test_env["source_dir"]
        mock_args.workspace_path = "."
        mock_args.log_level = log_level
        
        config = PluginFactoryConfig.load_from_env(mock_args)
        assert config.log_level == log_level
    
    def test_load_from_env_environment_variable_precedence(self, mock_args, setup_test_env, clean_env, tmp_path):
        """Test that custom .env file with override=True overrides environment variables."""
        # Set initial environment variables
        clean_env.setenv("RHDH_CLI_VERSION", "1.7.2")
        clean_env.setenv("WORKSPACE_PATH", ".")
        
        # Create a custom .env file with different values
        # Since load_dotenv is called with override=True, these values should win
        custom_env_file = tmp_path / "custom.env"
        custom_env_file.write_text("RHDH_CLI_VERSION=1.5.0\n")
        
        mock_args.config_dir = setup_test_env["config_dir"]
        mock_args.repo_path = setup_test_env["source_dir"]
        mock_args.workspace_path = "."
        
        # Load the config - the custom env file is loaded with override=True
        # So its values will override the environment variables
        config = PluginFactoryConfig.load_from_env(mock_args, env_file=custom_env_file)
        
        # Custom .env file values should override the initial env vars
        assert config.rhdh_cli_version == "1.5.0"
    
    def test_load_from_env_additional_env_file_loading(self, mock_args, setup_test_env, tmp_path, monkeypatch):
        """Test that additional .env file merges with defaults."""
        # Create a custom .env file with additional configuration
        custom_env_file = tmp_path / "custom.env"
        custom_env_file.write_text(
            "RHDH_CLI_VERSION=1.6.0\n"
            "REGISTRY_URL=quay.io\n"
            "REGISTRY_NAMESPACE=test-namespace\n"
        )
        
        # Set required variables
        monkeypatch.setenv("WORKSPACE_PATH", ".")
        
        mock_args.config_dir = setup_test_env["config_dir"]
        mock_args.repo_path = setup_test_env["source_dir"]
        mock_args.workspace_path = "."
        
        # Load with custom env file (should be loaded and override defaults)
        with patch("src.rhdh_dynamic_plugin_factory.config.load_dotenv") as mock_load_dotenv:
            # Let the actual load_dotenv run but track it
            from dotenv import load_dotenv as real_load_dotenv
            mock_load_dotenv.side_effect = real_load_dotenv
            
            # Actually set the env vars for the test
            monkeypatch.setenv("RHDH_CLI_VERSION", "1.6.0")
            monkeypatch.setenv("REGISTRY_URL", "quay.io")
            monkeypatch.setenv("REGISTRY_NAMESPACE", "test-namespace")
            
            config = PluginFactoryConfig.load_from_env(mock_args, env_file=custom_env_file)
            
            # Verify custom env file was loaded
            assert mock_load_dotenv.call_count >= 1
        
        # Verify values from custom env file
        assert config.rhdh_cli_version == "1.6.0"
        assert config.registry_url == "quay.io"
        assert config.registry_namespace == "test-namespace"
    
    def test_load_from_env_missing_workspace_path(self, mock_args, setup_test_env, monkeypatch):
        """Test that missing workspace_path raises ValueError."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        # Don't set WORKSPACE_PATH env var to test fallback
        monkeypatch.delenv("WORKSPACE_PATH", raising=False)
        
        mock_args.config_dir = setup_test_env["config_dir"]
        mock_args.repo_path = setup_test_env["source_dir"]
        mock_args.workspace_path = None  # Missing workspace_path
        
        # When workspace_path is None and WORKSPACE_PATH env var is not set,
        # validation should raise ValueError
        with pytest.raises(ValueError, match="WORKSPACE_PATH must be set"):
            PluginFactoryConfig.load_from_env(mock_args)
    
    def test_load_from_env_directory_creation(self, mock_args, tmp_path, monkeypatch):
        """Test that config_dir and repo_path directories are created."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        monkeypatch.setenv("WORKSPACE_PATH", ".")
        
        # Use non-existent directories
        new_config_dir = tmp_path / "new_config"
        new_repo_path = tmp_path / "new_workspace"
        
        # Create minimal required files in config_dir for validation
        new_config_dir.mkdir(parents=True, exist_ok=True)
        new_repo_path.mkdir(parents=True, exist_ok=True)
        
        # Create dummy file in repo_path to satisfy validation
        (new_repo_path / "dummy.txt").write_text("test")
        
        mock_args.config_dir = str(new_config_dir)
        mock_args.repo_path = str(new_repo_path)
        mock_args.workspace_path = "."
        
        config = PluginFactoryConfig.load_from_env(mock_args)
        
        # Verify directories exist
        assert os.path.exists(config.config_dir)
        assert os.path.exists(config.repo_path)
        assert new_config_dir.exists()
        assert new_repo_path.exists()
    
    def test_load_from_env_registry_config_from_environment(self, mock_args, setup_test_env, monkeypatch):
        """Test that registry configuration is loaded from environment variables."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        monkeypatch.setenv("WORKSPACE_PATH", ".")
        monkeypatch.setenv("REGISTRY_URL", "quay.io")
        monkeypatch.setenv("REGISTRY_USERNAME", "test_user")
        monkeypatch.setenv("REGISTRY_PASSWORD", "test_pass")
        monkeypatch.setenv("REGISTRY_NAMESPACE", "test_namespace")
        monkeypatch.setenv("REGISTRY_INSECURE", "true")
        
        mock_args.config_dir = setup_test_env["config_dir"]
        mock_args.repo_path = setup_test_env["source_dir"]
        mock_args.workspace_path = "."
        
        config = PluginFactoryConfig.load_from_env(mock_args)
        
        # Verify registry configuration
        assert config.registry_url == "quay.io"
        assert config.registry_username == "test_user"
        assert config.registry_password == "test_pass"
        assert config.registry_namespace == "test_namespace"
        assert config.registry_insecure is True
    
    def test_load_from_env_registry_insecure_false(self, mock_args, setup_test_env, monkeypatch):
        """Test that REGISTRY_INSECURE defaults to False."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        monkeypatch.setenv("WORKSPACE_PATH", ".")
        monkeypatch.setenv("REGISTRY_INSECURE", "false")
        
        mock_args.config_dir = setup_test_env["config_dir"]
        mock_args.repo_path = setup_test_env["source_dir"]
        mock_args.workspace_path = "."
        
        config = PluginFactoryConfig.load_from_env(mock_args)
        
        assert config.registry_insecure is False
    
    def test_load_from_env_use_local_flag(self, mock_args, setup_test_env, monkeypatch):
        """Test that use_local flag is loaded from args."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        monkeypatch.setenv("WORKSPACE_PATH", ".")
        
        mock_args.config_dir = setup_test_env["config_dir"]
        mock_args.repo_path = setup_test_env["source_dir"]
        mock_args.workspace_path = "."
        mock_args.use_local = True
        
        config = PluginFactoryConfig.load_from_env(mock_args)
        
        assert config.use_local is True
    
    def test_load_from_env_source_json_missing_repo_path_empty(self, mock_args, tmp_path, monkeypatch):
        """Test that missing source.json with empty repo_path raises ValueError."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        monkeypatch.setenv("WORKSPACE_PATH", ".")
        
        # Create empty directories
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        repo_path = tmp_path / "workspace"
        repo_path.mkdir(parents=True, exist_ok=True)
        # repo_path is empty (no files)
        
        mock_args.config_dir = str(config_dir)
        mock_args.repo_path = str(repo_path)
        mock_args.workspace_path = "."
        
        with pytest.raises(ValueError, match="source.json not found"):
            PluginFactoryConfig.load_from_env(mock_args)
    
    def test_load_from_env_source_json_missing_repo_path_has_content(self, mock_args, tmp_path, monkeypatch):
        """Test that missing source.json with non-empty repo_path logs warning but passes."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        monkeypatch.setenv("WORKSPACE_PATH", ".")
        
        # Create config dir without source.json
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        # Create repo_path with some content
        repo_path = tmp_path / "workspace"
        repo_path.mkdir(parents=True, exist_ok=True)
        (repo_path / "some_file.txt").write_text("content")
        
        mock_args.config_dir = str(config_dir)
        mock_args.repo_path = str(repo_path)
        mock_args.workspace_path = "."
        
        # Should not raise, just log warning
        config = PluginFactoryConfig.load_from_env(mock_args)
        
        assert config is not None
        assert config.config_dir == str(config_dir)
        assert config.repo_path == str(repo_path)


class TestLoadRegistryConfig:
    """Tests for PluginFactoryConfig.load_registry_config method."""
    
    def test_skip_when_push_images_false(self, make_config):
        """Test that registry configuration is skipped when push_images is False."""
        config = make_config()
        
        with patch.object(config, 'logger') as mock_logger:
            config.load_registry_config(push_images=False)
            mock_logger.info.assert_called_once_with(
                "Skipping registry configuration (not pushing images)"
            )
    
    def test_missing_registry_url(self, make_config):
        """Test that missing REGISTRY_URL raises ValueError when push_images is True."""
        config = make_config(registry_url=None, registry_namespace="test-namespace")
        
        with pytest.raises(ValueError, match="REGISTRY_URL environment variable is required"):
            config.load_registry_config(push_images=True)
    
    def test_missing_registry_namespace(self, make_config):
        """Test that missing REGISTRY_NAMESPACE raises ValueError when push_images is True."""
        config = make_config(registry_url="quay.io", registry_namespace=None)
        
        with pytest.raises(ValueError, match="REGISTRY_NAMESPACE environment variable is required"):
            config.load_registry_config(push_images=True)
    
    def test_successful_buildah_login(self, make_config):
        """Test successful buildah login with valid credentials."""
        config = make_config(
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password="test-password",
            registry_insecure=False
        )
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            with patch.object(config, 'logger') as mock_logger:
                config.load_registry_config(push_images=True)
                
                mock_run.assert_called_once()
                call_args = mock_run.call_args
                
                expected_cmd = [
                    "buildah", "login",
                    "--username", "test-user",
                    "--password", "test-password",
                    "quay.io"
                ]
                assert call_args[0][0] == expected_cmd
                assert call_args[1]['check'] is True
                assert call_args[1]['stdout'] == subprocess.PIPE
                assert call_args[1]['stderr'] == subprocess.PIPE
                
                mock_logger.info.assert_called_with(
                    "Logged in to registry quay.io with buildah."
                )
    
    def test_failed_buildah_login(self, make_config):
        """Test that failed buildah login logs warning but doesn't raise."""
        config = make_config(
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password="wrong-password",
            registry_insecure=False
        )
        
        with patch('subprocess.run') as mock_run:
            mock_error = subprocess.CalledProcessError(
                returncode=1,
                cmd=['buildah', 'login'],
                stderr=b"Authentication failed"
            )
            mock_run.side_effect = mock_error
            
            with patch.object(config, 'logger') as mock_logger:
                config.load_registry_config(push_images=True)
                
                mock_logger.warning.assert_called_once()
                warning_call = mock_logger.warning.call_args[0][0]
                assert "Failed to login to registry quay.io" in warning_call
                assert "Authentication failed" in warning_call
    
    def test_missing_registry_credentials(self, make_config):
        """Test that missing credentials raise ValueError when push_images is True."""
        config = make_config(
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username=None,
            registry_password=None,
            registry_insecure=False
        )
        
        with pytest.raises(ValueError, match="REGISTRY_USERNAME and REGISTRY_PASSWORD environment variables are required"):
            config.load_registry_config(push_images=True)
    
    def test_missing_registry_username(self, make_config):
        """Test that missing username raises ValueError when push_images is True."""
        config = make_config(
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username=None,
            registry_password="test-password",
            registry_insecure=False
        )
        
        with pytest.raises(ValueError, match="REGISTRY_USERNAME and REGISTRY_PASSWORD environment variables are required"):
            config.load_registry_config(push_images=True)
    
    def test_missing_registry_password(self, make_config):
        """Test that missing password raises ValueError when push_images is True."""
        config = make_config(
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password=None,
            registry_insecure=False
        )
        
        with pytest.raises(ValueError, match="REGISTRY_USERNAME and REGISTRY_PASSWORD environment variables are required"):
            config.load_registry_config(push_images=True)
    
    def test_insecure_registry_flag(self, make_config):
        """Test that insecure flag is added to buildah command when registry_insecure is True."""
        config = make_config(
            registry_url="localhost:5000",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password="test-password",
            registry_insecure=True
        )
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            config.load_registry_config(push_images=True)
            
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            
            expected_cmd = [
                "buildah", "login",
                "--username", "test-user",
                "--password", "test-password",
                "--tls-verify=false",
                "localhost:5000"
            ]
            assert call_args[0][0] == expected_cmd
    
    def test_secure_registry_default(self, make_config):
        """Test that insecure flag is NOT added when registry_insecure is False."""
        config = make_config(
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password="test-password",
            registry_insecure=False
        )
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            config.load_registry_config(push_images=True)
            
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            
            expected_cmd = [
                "buildah", "login",
                "--username", "test-user",
                "--password", "test-password",
                "quay.io"
            ]
            assert call_args[0][0] == expected_cmd
            assert "--tls-verify=false" not in call_args[0][0]


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
                            
                            result = config.export_plugins(output_dir, push_images=False)
                            
                            assert result is True
                            
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
        """Test that export_plugins returns False when script doesn't exist."""
        config = make_config()
        
        output_dir = str(setup_test_env["tmp_path"] / "output")
        
        with patch.object(Path, "exists", return_value=False):
            with patch.object(config, "logger") as mock_logger:
                result = config.export_plugins(output_dir, push_images=False)
                
                assert result is False
                
                mock_logger.error.assert_called_once()
                error_msg = mock_logger.error.call_args[0][0]
                assert "Script not found" in error_msg
    
    def test_export_plugins_no_plugins_list(self, make_config, setup_test_env):
        """Test that export_plugins returns False when plugins-list.yaml doesn't exist."""
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
                with patch.object(config, "logger") as mock_logger:
                    result = config.export_plugins(output_dir, push_images=False)
                    
                    assert result is False
                    
                    error_calls = [call[0][0] for call in mock_logger.error.call_args_list]
                    assert any("No plugins file found" in str(call) for call in error_calls)
    
    def test_export_plugins_script_fails(self, make_config, setup_test_env):
        """Test that export_plugins returns False when script returns non-zero exit code."""
        config = make_config(
            registry_url="quay.io",
            registry_namespace="test-namespace"
        )
        
        output_dir = str(setup_test_env["tmp_path"] / "output")
        
        with patch.object(Path, "exists", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run_cmd:
                    with patch("src.rhdh_dynamic_plugin_factory.config.load_dotenv"):
                        with patch.object(config, "logger") as mock_logger:
                            mock_run_cmd.return_value = 1
                            
                            result = config.export_plugins(output_dir, push_images=False)
                            
                            assert result is False
                            
                            error_calls = [call[0][0] for call in mock_logger.error.call_args_list]
                            assert any("exit code 1" in str(call) for call in error_calls)
    
    def test_export_plugins_has_failures(self, make_config, setup_test_env):
        """Test that export_plugins returns False when display_export_results indicates failures."""
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
                            with patch.object(config, "logger") as mock_logger:
                                mock_run_cmd.return_value = 0
                                mock_display.return_value = True
                                
                                result = config.export_plugins(output_dir, push_images=False)
                                
                                assert result is False
                                
                                error_calls = [call[0][0] for call in mock_logger.error.call_args_list]
                                assert any("completed with failures" in str(call) for call in error_calls)
    
    def test_export_plugins_exception(self, make_config, setup_test_env):
        """Test that export_plugins handles exceptions gracefully."""
        config = make_config()
        
        output_dir = str(setup_test_env["tmp_path"] / "output")
        
        with patch.object(Path, "exists", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run_cmd:
                    with patch("src.rhdh_dynamic_plugin_factory.config.load_dotenv"):
                        with patch.object(config, "logger") as mock_logger:
                            mock_run_cmd.side_effect = Exception("Test exception")
                            
                            result = config.export_plugins(output_dir, push_images=False)
                            
                            assert result is False
                            
                            mock_logger.error.assert_called()
                            error_msg = mock_logger.error.call_args[0][0]
                            assert "Failed to run export script" in error_msg
                            assert "Test exception" in error_msg
    
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

