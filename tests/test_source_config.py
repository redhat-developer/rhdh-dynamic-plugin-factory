"""
Unit tests for SourceConfig class.

Tests the source configuration loading, CLI arg construction, and repository cloning.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.rhdh_dynamic_plugin_factory.config import PluginFactoryConfig
from src.rhdh_dynamic_plugin_factory.source_config import SourceConfig
from src.rhdh_dynamic_plugin_factory.exceptions import ConfigurationError, ExecutionError, PluginFactoryError

class TestSourceConfigFromFile:
    """Tests for SourceConfig.from_file method."""
    
    def test_from_file_valid_source_json(self, tmp_path):
        """Test loading valid source.json with all required fields."""
        source_data = {
            "repo": "https://github.com/awslabs/backstage-plugins-for-aws",
            "repo-ref": "78df9399a81cfd95265cab53815f54210b1d7f50",
            "workspace-path": "."
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
            "repo-ref": "main",
            "workspace-path": "."
        }
        
        source_file = tmp_path / "source.json"
        source_file.write_text(json.dumps(source_data))
        
        with pytest.raises(ConfigurationError, match="repo is required"):
            SourceConfig.from_file(source_file)
    
    def test_from_file_empty_repo_ref_resolves_default(self, tmp_path):
        """Test that empty repo-ref triggers default branch resolution."""
        source_data = {
            "repo": "https://github.com/test/repo",
            "repo-ref": "",
            "workspace-path": "."
        }
        
        source_file = tmp_path / "source.json"
        source_file.write_text(json.dumps(source_data))
        
        with patch.object(SourceConfig, "resolve_default_ref", return_value="refs/heads/main"):
            config = SourceConfig.from_file(source_file)
            assert config.repo == "https://github.com/test/repo"
            assert config.repo_ref == "refs/heads/main"
            assert config.workspace_path == "."
    
    def test_from_file_missing_repo_ref_resolves_default(self, tmp_path):
        """Test that omitted repo-ref triggers default branch resolution."""
        source_data = {
            "repo": "https://github.com/test/repo",
            "workspace-path": "."
        }
        
        source_file = tmp_path / "source.json"
        source_file.write_text(json.dumps(source_data))
        
        with patch.object(SourceConfig, "resolve_default_ref", return_value="refs/heads/main"):
            config = SourceConfig.from_file(source_file)
            assert config.repo == "https://github.com/test/repo"
            assert config.repo_ref == "refs/heads/main"
            assert config.workspace_path == "."
    
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

class TestSourceConfigFromCliArgs:
    """Tests for SourceConfig.from_cli_args classmethod."""
    
    def test_from_cli_args_with_all_fields(self):
        """Test creating SourceConfig from CLI args with all fields."""
        config = SourceConfig.from_cli_args(
            repo="https://github.com/backstage/community-plugins",
            repo_ref="abc123",
            workspace_path="workspaces/todo",
        )
        
        assert config.repo == "https://github.com/backstage/community-plugins"
        assert config.repo_ref == "abc123"
        assert config.workspace_path == "workspaces/todo"
    
    def test_from_cli_args_with_none_repo_ref_resolves_default(self):
        """Test creating SourceConfig from CLI args with None repo_ref triggers resolution."""
        with patch.object(SourceConfig, "resolve_default_ref", return_value="refs/heads/main"):
            config = SourceConfig.from_cli_args(
                repo="https://github.com/backstage/community-plugins",
                repo_ref=None,
                workspace_path="workspaces/todo",
            )
            
            assert config.repo == "https://github.com/backstage/community-plugins"
            assert config.repo_ref == "refs/heads/main"
            assert config.workspace_path == "workspaces/todo"
    
    def test_from_cli_args_missing_repo_raises_error(self):
        """Test that missing repo raises ConfigurationError."""
        with pytest.raises(ConfigurationError, match="repo is required"):
            SourceConfig.from_cli_args(
                repo="",
                repo_ref="main",
                workspace_path="workspaces/todo",
            )
    
    def test_from_cli_args_missing_workspace_path_raises_error(self):
        """Test that missing workspace_path raises ConfigurationError."""
        with pytest.raises(ConfigurationError, match="workspace-path is required"):
            SourceConfig.from_cli_args(
                repo="https://github.com/backstage/community-plugins",
                repo_ref="main",
                workspace_path="",
            )


class TestResolveDefaultRef:
    """Tests for SourceConfig.resolve_default_ref static method.
    
    Happy-path tests use real git ls-remote calls to verify parsing
    against actual git output. Error cases use mocks since they can't
    be reliably triggered against real repositories.
    """
    
    def test_resolve_default_ref_real_repo(self):
        """Test resolving default branch against a real public repository."""
        ref = SourceConfig.resolve_default_ref("https://github.com/git/git.git")
        
        # Should return the master branch
        assert (ref == "refs/heads/master")
        # Branch name should be non-empty
        branch_name = ref.removeprefix("refs/heads/")
        assert branch_name == "master"
    
    def test_resolve_default_ref_git_failure(self):
        """Test that git ls-remote failure raises ExecutionError."""
        error = subprocess.CalledProcessError(128, "git", stderr="fatal: repository not found")
        
        with patch("subprocess.run", side_effect=error):
            with pytest.raises(ExecutionError, match="Failed to resolve default branch"):
                SourceConfig.resolve_default_ref("https://github.com/test/nonexistent")
    
    def test_resolve_default_ref_no_symbolic_ref(self):
        """Test that missing symbolic ref raises ConfigurationError with actionable message."""
        mock_result = MagicMock()
        mock_result.stdout = "abc123def456\tHEAD\n"
        
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(ConfigurationError, match="Could not resolve the default branch"):
                SourceConfig.resolve_default_ref("https://github.com/test/repo")
    
    def test_resolve_default_ref_empty_output(self):
        """Test that empty git ls-remote output raises ConfigurationError."""
        mock_result = MagicMock()
        mock_result.stdout = ""
        
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(ConfigurationError, match="Could not resolve the default branch"):
                SourceConfig.resolve_default_ref("https://github.com/test/repo")


class TestSourceConfigCloneToPath:
    """Tests for SourceConfig.clone_to_path method."""
    
    def test_clone_to_path_success(self, tmp_path):
        """Test successful clone with mock git commands."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main",
            workspace_path="."
        )
        
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        
        with patch("src.rhdh_dynamic_plugin_factory.source_config.run_command_with_streaming") as mock_run:
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
    
    def test_clone_to_path_resolved_default_ref(self, tmp_path):
        """Test that clone works correctly when repo_ref was resolved from default branch."""
        with patch.object(SourceConfig, "resolve_default_ref", return_value="refs/heads/main"):
            config = SourceConfig(
                repo="https://github.com/testowner/testrepo",
                repo_ref=None,
                workspace_path="."
            )
        
        # repo_ref should already be resolved at creation time
        assert config.repo_ref == "refs/heads/main"
        
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        
        with patch("src.rhdh_dynamic_plugin_factory.source_config.run_command_with_streaming") as mock_run:
            mock_run.return_value = 0
            
            config.clone_to_path(repo_path)
            
            # Both clone and checkout should happen
            assert mock_run.call_count == 2
            
            # Verify clone command
            clone_call = mock_run.call_args_list[0]
            assert clone_call[0][0] == ["git", "clone", "https://github.com/testowner/testrepo", str(repo_path)]
            
            # Verify checkout command with resolved ref
            checkout_call = mock_run.call_args_list[1]
            assert checkout_call[0][0] == ["git", "checkout", "refs/heads/main"]

    def test_clone_to_path_repo_path_does_not_exist(self, tmp_path):
        """Test that non-existent repo_path raises ConfigurationError."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main",
            workspace_path="."
        )
        
        repo_path = tmp_path / "nonexistent"
        
        with pytest.raises(ConfigurationError, match="Destination directory does not exist"):
            config.clone_to_path(repo_path)
    
    def test_clone_to_path_clone_fails(self, tmp_path):
        """Test that clone failure raises ExecutionError."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main",
            workspace_path="."
        )
        
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        
        with patch("src.rhdh_dynamic_plugin_factory.source_config.run_command_with_streaming") as mock_run:
            mock_run.return_value = 1  # Failed
            
            with pytest.raises(ExecutionError, match="Failed to clone repository"):
                config.clone_to_path(repo_path)
    
    def test_clone_to_path_checkout_fails(self, tmp_path):
        """Test that checkout failure raises ExecutionError."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main",
            workspace_path="."
        )
        
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        
        with patch("src.rhdh_dynamic_plugin_factory.source_config.run_command_with_streaming") as mock_run:
            # First call (clone) succeeds, second call (checkout) fails
            mock_run.side_effect = [0, 1]
            
            with pytest.raises(ExecutionError, match="Failed to checkout ref"):
                config.clone_to_path(repo_path)
    
    def test_clone_to_path_exception(self, tmp_path):
        """Test that exceptions are wrapped in ExecutionError."""
        config = SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref="main",
            workspace_path="."
        )
        
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        
        with patch("src.rhdh_dynamic_plugin_factory.source_config.run_command_with_streaming") as mock_run:
            mock_run.side_effect = Exception("Test exception")
            
            with pytest.raises(ExecutionError, match="Failed during repository clone/checkout"):
                config.clone_to_path(repo_path)


class TestSourceConfigCloneToPathClean:
    """Tests for SourceConfig.clone_to_path clean argument and user prompt behavior.
    
    Uses real filesystem operations to verify that nested directory contents are 
    actually removed or preserved as expected.
    """

    @staticmethod
    def _make_nested_repo(repo_path: Path) -> None:
        """Create a realistic nested directory structure for testing."""
        repo_path.mkdir(exist_ok=True)
        (repo_path / "existing_file.txt").write_text("existing content")
        (repo_path / ".hidden_config").write_text("hidden")
        src = repo_path / "src"
        src.mkdir()
        (src / "index.ts").write_text("export {}")
        components = src / "components"
        components.mkdir()
        (components / "App.tsx").write_text("<App/>")
        modules = repo_path / "node_modules" / "package"
        modules.mkdir(parents=True)
        (modules / "index.js").write_text("module.exports = {}")

    @staticmethod
    def _make_config(repo_ref: str = "main") -> SourceConfig:
        return SourceConfig(
            repo="https://github.com/testowner/testrepo",
            repo_ref=repo_ref,
            workspace_path="."
        )

    def test_clean_flag_auto_cleans_nested_contents(self, tmp_path):
        """Test that clean=True removes all nested contents without prompting."""
        config = self._make_config()
        repo_path = tmp_path / "repo"
        self._make_nested_repo(repo_path)

        with patch("src.rhdh_dynamic_plugin_factory.source_config.run_command_with_streaming") as mock_run, \
             patch("builtins.input") as mock_input:
            mock_run.return_value = 0

            config.clone_to_path(repo_path, clean=True)

            mock_input.assert_not_called()
            assert repo_path.exists(), "Directory itself should still exist"
            assert list(repo_path.iterdir()) == [], "All nested contents should be removed"

    def test_no_clean_flag_prompts_user_confirm_yes(self, tmp_path):
        """Test that clean=False prompts user and cleans nested contents when user enters 'y'."""
        config = self._make_config()
        repo_path = tmp_path / "repo"
        self._make_nested_repo(repo_path)

        with patch("src.rhdh_dynamic_plugin_factory.source_config.run_command_with_streaming") as mock_run, \
             patch("builtins.input", return_value="y"):
            mock_run.return_value = 0

            config.clone_to_path(repo_path, clean=False)

            assert repo_path.exists(), "Directory itself should still exist"
            assert list(repo_path.iterdir()) == [], "All nested contents should be removed"

    def test_no_clean_flag_prompts_user_confirm_no_preserves_contents(self, tmp_path):
        """Test that declining the prompt preserves all nested contents."""
        config = self._make_config()
        repo_path = tmp_path / "repo"
        self._make_nested_repo(repo_path)

        original_contents = {p.name for p in repo_path.rglob("*")}

        with patch("builtins.input", return_value="n"):
            with pytest.raises(PluginFactoryError, match="aborted by user"):
                config.clone_to_path(repo_path, clean=False)

        remaining_contents = {p.name for p in repo_path.rglob("*")}
        assert remaining_contents == original_contents, "No files should have been removed"

    def test_no_clean_flag_empty_input_preserves_contents(self, tmp_path):
        """Test that pressing Enter without input preserves all nested contents."""
        config = self._make_config()
        repo_path = tmp_path / "repo"
        self._make_nested_repo(repo_path)

        original_contents = {p.name for p in repo_path.rglob("*")}

        with patch("builtins.input", return_value=""):
            with pytest.raises(PluginFactoryError, match="aborted by user"):
                config.clone_to_path(repo_path, clean=False)

        remaining_contents = {p.name for p in repo_path.rglob("*")}
        assert remaining_contents == original_contents, "No files should have been removed"

    def test_empty_directory_skips_clean_and_prompt(self, tmp_path):
        """Test that an empty directory skips both clean and user prompt."""
        config = self._make_config()
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        with patch("src.rhdh_dynamic_plugin_factory.source_config.run_command_with_streaming") as mock_run, \
             patch("builtins.input") as mock_input:
            mock_run.return_value = 0

            config.clone_to_path(repo_path, clean=True)

            mock_input.assert_not_called()

    def test_empty_directory_no_clean_flag_skips_prompt(self, tmp_path):
        """Test that an empty directory with clean=False does not prompt user."""
        config = self._make_config()
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        with patch("src.rhdh_dynamic_plugin_factory.source_config.run_command_with_streaming") as mock_run, \
             patch("builtins.input") as mock_input:
            mock_run.return_value = 0

            config.clone_to_path(repo_path, clean=False)

            mock_input.assert_not_called()

    def test_clean_flag_default_is_false(self, tmp_path):
        """Test that the clean parameter defaults to False."""
        config = self._make_config()
        repo_path = tmp_path / "repo"
        self._make_nested_repo(repo_path)

        with patch("builtins.input", return_value="n"):
            with pytest.raises(PluginFactoryError, match="aborted by user"):
                config.clone_to_path(repo_path)

    def test_clean_proceeds_with_clone_after_cleaning(self, tmp_path):
        """Test that after cleaning nested contents, git clone and checkout are executed."""
        config = self._make_config(repo_ref="v1.0.0")
        repo_path = tmp_path / "repo"
        self._make_nested_repo(repo_path)

        with patch("src.rhdh_dynamic_plugin_factory.source_config.run_command_with_streaming") as mock_run:
            mock_run.return_value = 0

            config.clone_to_path(repo_path, clean=True)

            assert list(repo_path.iterdir()) == [], "Directory should be empty before clone runs"
            assert mock_run.call_count == 2

            clone_call = mock_run.call_args_list[0]
            assert clone_call[0][0] == ["git", "clone", "https://github.com/testowner/testrepo", str(repo_path)]

            checkout_call = mock_run.call_args_list[1]
            assert checkout_call[0][0] == ["git", "checkout", "v1.0.0"]

    def test_prompt_confirm_yes_proceeds_with_clone(self, tmp_path):
        """Test that after user confirms 'y', nested contents are cleaned and clone/checkout run."""
        config = self._make_config()
        repo_path = tmp_path / "repo"
        self._make_nested_repo(repo_path)

        with patch("src.rhdh_dynamic_plugin_factory.source_config.run_command_with_streaming") as mock_run, \
             patch("builtins.input", return_value="y"):
            mock_run.return_value = 0

            config.clone_to_path(repo_path, clean=False)

            assert list(repo_path.iterdir()) == [], "Directory should be empty before clone runs"
            assert mock_run.call_count == 2

    def test_prompt_confirm_no_does_not_clone(self, tmp_path):
        """Test that when user declines, no nested contents are removed and clone does not run."""
        config = self._make_config()
        repo_path = tmp_path / "repo"
        self._make_nested_repo(repo_path)

        original_contents = {p.name for p in repo_path.rglob("*")}

        with patch("src.rhdh_dynamic_plugin_factory.source_config.run_command_with_streaming") as mock_run, \
             patch("builtins.input", return_value="n"):
            with pytest.raises(PluginFactoryError, match="aborted by user"):
                config.clone_to_path(repo_path, clean=False)

            mock_run.assert_not_called()

        remaining_contents = {p.name for p in repo_path.rglob("*")}
        assert remaining_contents == original_contents, "No files should have been removed"

class TestDiscoverSourceConfigCliArgs:
    """Tests for PluginFactoryConfig.discover_source_config with CLI args."""
    
    def test_cli_args_take_precedence_over_source_json(self, make_config, setup_test_env):
        """Test that --source-repo takes precedence over source.json."""
        config = make_config(
            source_repo="https://github.com/cli/override-repo",
            source_ref="v2.0.0",
        )
        
        source_config = config.discover_source_config()
        
        assert source_config is not None
        assert source_config.repo == "https://github.com/cli/override-repo"
        assert source_config.repo_ref == "v2.0.0"
    
    def test_cli_args_with_none_repo_ref_resolves_default(self, make_config, setup_test_env):
        """Test that --source-repo without --source-ref resolves default branch."""
        config = make_config(
            source_repo="https://github.com/cli/override-repo",
            source_ref=None,
        )
        
        with patch.object(SourceConfig, "resolve_default_ref", return_value="refs/heads/main"):
            source_config = config.discover_source_config()
        
        assert source_config is not None
        assert source_config.repo == "https://github.com/cli/override-repo"
        assert source_config.repo_ref == "refs/heads/main"
    
    def test_cli_args_skipped_when_use_local(self, make_config, setup_test_env):
        """Test that CLI args are ignored when --use-local is set."""
        config = make_config(
            source_repo="https://github.com/cli/override-repo",
            source_ref="v2.0.0",
            use_local=True,
        )
        
        source_config = config.discover_source_config()
        
        # Should return None (using local), not the CLI args
        assert source_config is None
    
    def test_falls_back_to_source_json_when_no_cli_args(self, make_config, setup_test_env):
        """Test that source.json is used when no CLI args are provided."""
        config = make_config(
            source_repo=None,
            source_ref=None,
        )
        
        source_config = config.discover_source_config()
        
        # Should use the source.json from setup_test_env fixture
        assert source_config is not None
        assert source_config.repo == "https://github.com/awslabs/backstage-plugins-for-aws"
        assert source_config.repo_ref == "78df9399a81cfd95265cab53815f54210b1d7f50"
    
    def test_workspace_path_from_source_json(self, tmp_path, monkeypatch, write_source_json):
        """Test that workspace_path is resolved from source.json when not provided via CLI."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        
        config_dir = tmp_path / "config"
        source_dir = tmp_path / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        
        write_source_json(config_dir, "https://github.com/test/repo", "main", "workspaces/todo")
        
        config = PluginFactoryConfig(
            rhdh_cli_version="1.7.2",
            config_dir=str(config_dir),
            repo_path=str(source_dir),
            workspace_path="",  # Not provided
        )
        
        source_config = config.discover_source_config()
        
        assert source_config is not None
        assert source_config.workspace_path == "workspaces/todo"
