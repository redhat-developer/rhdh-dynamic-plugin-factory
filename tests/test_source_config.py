"""
Unit tests for SourceConfig class.

Tests the source configuration loading and repository URL parsing.
"""

import json
from unittest.mock import patch
import pytest

from src.rhdh_dynamic_plugin_factory.config import SourceConfig
from src.rhdh_dynamic_plugin_factory.exceptions import ConfigurationError, ExecutionError, PluginFactoryError

class TestSourceConfigFromFile:
    """Tests for SourceConfig.from_file method."""
    
    def test_from_file_valid_source_json(self, tmp_path):
        """Test loading valid source.json with all required fields."""
        source_data = {
            "repo": "https://github.com/awslabs/backstage-plugins-for-aws",
            "repo-ref": "78df9399a81cfd95265cab53815f54210b1d7f50"
        }
        
        source_file = tmp_path / "source.json"
        source_file.write_text(json.dumps(source_data))
        
        config = SourceConfig.from_file(source_file)
        
        assert config.repo == "https://github.com/awslabs/backstage-plugins-for-aws"
        assert config.repo_ref == "78df9399a81cfd95265cab53815f54210b1d7f50"
    
    def test_from_file_missing_repo(self, tmp_path):
        """Test that missing repo field raises ConfigurationError with descriptive message."""
        source_data = {
            "repo-ref": "main"
        }
        
        source_file = tmp_path / "source.json"
        source_file.write_text(json.dumps(source_data))
        
        with pytest.raises(ConfigurationError, match="Missing required field"):
            SourceConfig.from_file(source_file)
    
    def test_from_file_empty_repo(self, tmp_path):
        """Test that empty repo field raises ConfigurationError."""
        source_data = {
            "repo": "",
            "repo-ref": "main"
        }
        
        source_file = tmp_path / "source.json"
        source_file.write_text(json.dumps(source_data))
        
        with pytest.raises(ConfigurationError, match="repo is required"):
            SourceConfig.from_file(source_file)
    
    def test_from_file_empty_repo_ref(self, tmp_path):
        """Test that empty repo_ref field raises ConfigurationError."""
        source_data = {
            "repo": "https://github.com/test/repo",
            "repo-ref": ""
        }
        
        source_file = tmp_path / "source.json"
        source_file.write_text(json.dumps(source_data))
        
        with pytest.raises(ConfigurationError, match="repo_ref is required"):
            SourceConfig.from_file(source_file)
    
    def test_from_file_missing_repo_ref(self, tmp_path):
        """Test that missing repo_ref field raises ConfigurationError."""
        source_data = {
            "repo": "https://github.com/test/repo"
        }
        
        source_file = tmp_path / "source.json"
        source_file.write_text(json.dumps(source_data))
        
        # repo_ref is now required and will raise ConfigurationError if missing/None
        with pytest.raises(ConfigurationError, match="repo_ref is required"):
            SourceConfig.from_file(source_file)
    
    def test_from_file_malformed_json(self, tmp_path):
        """Test that malformed JSON raises ConfigurationError with descriptive message."""
        source_file = tmp_path / "source.json"
        source_file.write_text("{ invalid json }")
        
        with pytest.raises(ConfigurationError, match="Invalid JSON"):
            SourceConfig.from_file(source_file)
    
    def test_from_file_nonexistent_file(self, tmp_path):
        """Test that nonexistent file raises ConfigurationError with descriptive message."""
        source_file = tmp_path / "nonexistent.json"
        
        with pytest.raises(ConfigurationError, match="Source configuration file not found"):
            SourceConfig.from_file(source_file)


class TestSourceConfigCloneToPath:
    """Tests for SourceConfig.clone_to_path method."""
    
    def test_clone_to_path_success(self, tmp_path):
        """Test successful clone with mock git commands."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )
        
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        
        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run:
            mock_run.return_value = 0
            
            config.clone_to_path(repo_path)  # Should not raise any exceptions
            
            assert mock_run.call_count == 2  # clone + checkout
            
            # Verify clone command
            clone_call = mock_run.call_args_list[0]
            assert clone_call[0][0][0] == "git"
            assert clone_call[0][0][1] == "clone"
            assert "https://github.com/testowner/testrepo" in clone_call[0][0][2]
            
            # Verify checkout command
            checkout_call = mock_run.call_args_list[1]
            assert checkout_call[0][0][0] == "git"
            assert checkout_call[0][0][1] == "checkout"
            assert checkout_call[0][0][2] == "main"
    
    def test_clone_to_path_repo_path_does_not_exist(self, tmp_path):
        """Test that non-existent repo_path raises ConfigurationError."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )
        
        repo_path = tmp_path / "nonexistent"
        
        with pytest.raises(ConfigurationError, match="Destination directory does not exist"):
            config.clone_to_path(repo_path)
    
    def test_clone_to_path_clone_fails(self, tmp_path):
        """Test that clone failure raises ExecutionError."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )
        
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        
        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run:
            mock_run.return_value = 1  # Failed
            
            with pytest.raises(ExecutionError, match="Failed to clone repository"):
                config.clone_to_path(repo_path)
    
    def test_clone_to_path_checkout_fails(self, tmp_path):
        """Test that checkout failure raises ExecutionError."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )
        
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        
        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run:
            # First call (clone) succeeds, second call (checkout) fails
            mock_run.side_effect = [0, 1]
            
            with pytest.raises(ExecutionError, match="Failed to checkout ref"):
                config.clone_to_path(repo_path)
    
    def test_clone_to_path_exception(self, tmp_path):
        """Test that exceptions are wrapped in ExecutionError."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )
        
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        
        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run:
            mock_run.side_effect = Exception("Test exception")
            
            with pytest.raises(ExecutionError, match="Failed during repository clone/checkout"):
                config.clone_to_path(repo_path)


class TestSourceConfigCloneToPathClean:
    """Tests for SourceConfig.clone_to_path clean argument and user prompt behavior."""

    def test_clean_flag_auto_cleans_nonempty_directory(self, tmp_path):
        """Test that clean=True automatically cleans a non-empty directory without prompting."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )

        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "existing_file.txt").write_text("existing content")
        (repo_path / "subdir").mkdir()
        (repo_path / "subdir" / "nested.txt").write_text("nested content")

        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run, \
             patch("src.rhdh_dynamic_plugin_factory.config.clean_directory") as mock_clean:
            mock_run.return_value = 0

            config.clone_to_path(repo_path, clean=True)  # Should not raise any exceptions

            mock_clean.assert_called_once_with(repo_path)

    def test_clean_flag_does_not_prompt_user(self, tmp_path):
        """Test that clean=True does not call input() for user confirmation."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )

        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "existing_file.txt").write_text("existing content")

        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run, \
             patch("src.rhdh_dynamic_plugin_factory.config.clean_directory"), \
             patch("builtins.input") as mock_input:
            mock_run.return_value = 0

            config.clone_to_path(repo_path, clean=True)

            mock_input.assert_not_called()

    def test_no_clean_flag_prompts_user_confirm_yes(self, tmp_path):
        """Test that clean=False prompts user and proceeds when user enters 'y'."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )

        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "existing_file.txt").write_text("existing content")

        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run, \
             patch("src.rhdh_dynamic_plugin_factory.config.clean_directory") as mock_clean, \
             patch("builtins.input", return_value="y"):
            mock_run.return_value = 0

            config.clone_to_path(repo_path, clean=False)  # Should not raise any exceptions

            mock_clean.assert_called_once_with(repo_path)

    def test_no_clean_flag_prompts_user_confirm_no(self, tmp_path):
        """Test that clean=False prompts user and raises PluginFactoryError when user declines."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )

        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "existing_file.txt").write_text("existing content")

        with patch("builtins.input", return_value="n") as mock_input:
            with pytest.raises(PluginFactoryError, match="aborted by user"):
                config.clone_to_path(repo_path, clean=False)

            mock_input.assert_called_once()

    def test_no_clean_flag_prompts_user_empty_input_aborts(self, tmp_path):
        """Test that clean=False raises PluginFactoryError when user presses Enter without typing anything."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )

        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "existing_file.txt").write_text("existing content")

        with patch("builtins.input", return_value=""):
            with pytest.raises(PluginFactoryError, match="aborted by user"):
                config.clone_to_path(repo_path, clean=False)

    def test_empty_directory_skips_clean_and_prompt(self, tmp_path):
        """Test that an empty directory skips both clean and prompt logic."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )

        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        # Directory is empty

        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run, \
             patch("src.rhdh_dynamic_plugin_factory.config.clean_directory") as mock_clean, \
             patch("builtins.input") as mock_input:
            mock_run.return_value = 0

            config.clone_to_path(repo_path, clean=True)  # Should not raise

            mock_clean.assert_not_called()
            mock_input.assert_not_called()

    def test_empty_directory_no_clean_flag_skips_prompt(self, tmp_path):
        """Test that an empty directory with clean=False does not prompt user."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )

        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        # Directory is empty

        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run, \
             patch("builtins.input") as mock_input:
            mock_run.return_value = 0

            config.clone_to_path(repo_path, clean=False)  # Should not raise any exceptions]

            mock_input.assert_not_called()

    def test_clean_flag_default_is_false(self, tmp_path):
        """Test that the clean parameter defaults to False."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )

        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "existing_file.txt").write_text("existing content")

        with patch("builtins.input", return_value="n"):
            # Call without clean argument - should prompt and raise PluginFactoryError when user declines
            with pytest.raises(PluginFactoryError, match="aborted by user"):
                config.clone_to_path(repo_path)

    def test_clean_proceeds_with_clone_after_cleaning(self, tmp_path):
        """Test that after cleaning, git clone and checkout are executed."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="v1.0.0"
        )

        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "old_file.txt").write_text("old content")

        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run, \
             patch("src.rhdh_dynamic_plugin_factory.config.clean_directory"):
            mock_run.return_value = 0

            config.clone_to_path(repo_path, clean=True)  # Should not raise any exceptions

            assert mock_run.call_count == 2  # clone + checkout

            # Verify clone command
            clone_call = mock_run.call_args_list[0]
            assert clone_call[0][0] == ["git", "clone", "https://github.com/testowner/testrepo", str(repo_path)]

            # Verify checkout command
            checkout_call = mock_run.call_args_list[1]
            assert checkout_call[0][0] == ["git", "checkout", "v1.0.0"]

    def test_prompt_confirm_yes_proceeds_with_clone(self, tmp_path):
        """Test that after user confirms 'y', git clone and checkout are executed."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )

        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "old_file.txt").write_text("old content")

        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run, \
             patch("src.rhdh_dynamic_plugin_factory.config.clean_directory"), \
             patch("builtins.input", return_value="y"):
            mock_run.return_value = 0

            config.clone_to_path(repo_path, clean=False)  # Should not raise any exceptions

            assert mock_run.call_count == 2  # clone + checkout

    def test_prompt_confirm_no_does_not_clone(self, tmp_path):
        """Test that when user declines, git clone is not executed."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )

        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / "existing_file.txt").write_text("existing content")

        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run, \
             patch("builtins.input", return_value="n"):

            with pytest.raises(PluginFactoryError, match="aborted by user"):
                config.clone_to_path(repo_path, clean=False)

            mock_run.assert_not_called()

