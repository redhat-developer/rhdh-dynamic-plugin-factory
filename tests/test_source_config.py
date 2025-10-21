"""
Unit tests for SourceConfig class.

Tests the source configuration loading and repository URL parsing.
"""

import json
from unittest.mock import patch
import pytest

from src.rhdh_dynamic_plugin_factory.config import SourceConfig

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
        """Test that missing repo field raises ValueError with descriptive message."""
        source_data = {
            "repo-ref": "main"
        }
        
        source_file = tmp_path / "source.json"
        source_file.write_text(json.dumps(source_data))
        
        with pytest.raises(ValueError, match="Missing required field"):
            SourceConfig.from_file(source_file)
    
    def test_from_file_empty_repo(self, tmp_path):
        """Test that empty repo field raises ValueError."""
        source_data = {
            "repo": "",
            "repo-ref": "main"
        }
        
        source_file = tmp_path / "source.json"
        source_file.write_text(json.dumps(source_data))
        
        with pytest.raises(ValueError, match="repo is required"):
            SourceConfig.from_file(source_file)
    
    def test_from_file_empty_repo_ref(self, tmp_path):
        """Test that empty repo_ref field raises ValueError."""
        source_data = {
            "repo": "https://github.com/test/repo",
            "repo-ref": ""
        }
        
        source_file = tmp_path / "source.json"
        source_file.write_text(json.dumps(source_data))
        
        with pytest.raises(ValueError, match="repo_ref is required"):
            SourceConfig.from_file(source_file)
    
    def test_from_file_missing_repo_ref(self, tmp_path):
        """Test that missing repo_ref field raises ValueError."""
        source_data = {
            "repo": "https://github.com/test/repo"
        }
        
        source_file = tmp_path / "source.json"
        source_file.write_text(json.dumps(source_data))
        
        # repo_ref is now required and will raise ValueError if missing/None
        with pytest.raises(ValueError, match="repo_ref is required"):
            SourceConfig.from_file(source_file)
    
    def test_from_file_malformed_json(self, tmp_path):
        """Test that malformed JSON raises ValueError with descriptive message."""
        source_file = tmp_path / "source.json"
        source_file.write_text("{ invalid json }")
        
        with pytest.raises(ValueError, match="Invalid JSON"):
            SourceConfig.from_file(source_file)
    
    def test_from_file_nonexistent_file(self, tmp_path):
        """Test that nonexistent file raises ValueError with descriptive message."""
        source_file = tmp_path / "nonexistent.json"
        
        with pytest.raises(ValueError, match="Source configuration file not found"):
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
            
            result = config.clone_to_path(repo_path)
            
            assert result is True
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
        """Test that non-existent repo_path returns True early."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )
        
        repo_path = tmp_path / "nonexistent"
        
        result = config.clone_to_path(repo_path)
        
        # According to the code, it returns True if repo_path doesn't exist
        assert result is True
    
    def test_clone_to_path_clone_fails(self, tmp_path):
        """Test that clone failure returns False."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )
        
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        
        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run:
            mock_run.return_value = 1  # Failed
            
            result = config.clone_to_path(repo_path)
            
            assert result is False
    
    def test_clone_to_path_checkout_fails(self, tmp_path):
        """Test that checkout failure returns False."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )
        
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        
        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run:
            # First call (clone) succeeds, second call (checkout) fails
            mock_run.side_effect = [0, 1]
            
            result = config.clone_to_path(repo_path)
            
            assert result is False
    
    def test_clone_to_path_exception(self, tmp_path):
        """Test that exceptions return False."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main"
        )
        
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        
        with patch("src.rhdh_dynamic_plugin_factory.config.run_command_with_streaming") as mock_run:
            mock_run.side_effect = Exception("Test exception")
            
            result = config.clone_to_path(repo_path)
            
            assert result is False

