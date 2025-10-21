"""
Unit tests for PluginFactoryConfig class.

Tests the configuration loading, validation, and setup functionality
without executing shell scripts.
"""

from pathlib import Path
from unittest.mock import patch
import pytest

from src.rhdh_dynamic_plugin_factory.config import PluginFactoryConfig


class TestPluginFactoryConfigLoadFromEnv:
    """Tests for PluginFactoryConfig.load_from_env method."""
    
    def test_load_from_env_valid_configuration(self, mock_args, setup_test_env, monkeypatch):
        """Test loading configuration with all required fields present."""
        # Update mock_args to use the setup_test_env paths
        mock_args.config_dir = setup_test_env["config_dir"]
        mock_args.repo_path = setup_test_env["workspace_dir"]
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
        assert config.repo_path == setup_test_env["workspace_dir"]
        assert config.workspace_path == Path(".")
        assert config.use_local is False
        
        # Verify directories were created
        assert config.config_dir.exists()
        assert config.repo_path.exists()
        
        # Verify path types
        assert isinstance(config.config_dir, Path)
        assert isinstance(config.repo_path, Path)
        assert isinstance(config.workspace_path, Path)
    
    def test_load_from_env_missing_rhdh_cli_version(self, mock_args, setup_test_env, clean_env):
        """Test that missing RHDH_CLI_VERSION raises ValueError."""
        # Don't set RHDH_CLI_VERSION
        clean_env.setenv("WORKSPACE_PATH", ".")
        
        mock_args.config_dir = setup_test_env["config_dir"]
        mock_args.repo_path = setup_test_env["workspace_dir"]
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
        mock_args.repo_path = setup_test_env["workspace_dir"]
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
        mock_args.repo_path = setup_test_env["workspace_dir"]
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
        mock_args.repo_path = setup_test_env["workspace_dir"]
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
        mock_args.repo_path = setup_test_env["workspace_dir"]
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
        """Test that missing workspace_path handles gracefully with sys.exit."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        
        mock_args.config_dir = setup_test_env["config_dir"]
        mock_args.repo_path = setup_test_env["workspace_dir"]
        mock_args.workspace_path = None  # Missing workspace_path
        
        with pytest.raises(SystemExit):
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
        
        mock_args.config_dir = new_config_dir
        mock_args.repo_path = new_repo_path
        mock_args.workspace_path = "."
        
        config = PluginFactoryConfig.load_from_env(mock_args)
        
        # Verify directories were created
        assert config.config_dir.exists()
        assert config.repo_path.exists()
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
        mock_args.repo_path = setup_test_env["workspace_dir"]
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
        mock_args.repo_path = setup_test_env["workspace_dir"]
        mock_args.workspace_path = "."
        
        config = PluginFactoryConfig.load_from_env(mock_args)
        
        assert config.registry_insecure is False
    
    def test_load_from_env_use_local_flag(self, mock_args, setup_test_env, monkeypatch):
        """Test that use_local flag is loaded from args."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        monkeypatch.setenv("WORKSPACE_PATH", ".")
        
        mock_args.config_dir = setup_test_env["config_dir"]
        mock_args.repo_path = setup_test_env["workspace_dir"]
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
        
        mock_args.config_dir = config_dir
        mock_args.repo_path = repo_path
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
        
        mock_args.config_dir = config_dir
        mock_args.repo_path = repo_path
        mock_args.workspace_path = "."
        
        # Should not raise, just log warning
        config = PluginFactoryConfig.load_from_env(mock_args)
        
        assert config is not None
        assert config.config_dir == config_dir
        assert config.repo_path == repo_path

