"""
Unit tests for CLI argument parsing.

Tests the argument parser to ensure all arguments are correctly defined and parsed.
"""

import pytest

from src.rhdh_dynamic_plugin_factory.cli import create_parser, _run
from src.rhdh_dynamic_plugin_factory.exceptions import ConfigurationError


class TestCreateParserCleanArgument:
    """Tests for the --clean CLI argument."""

    def test_clean_flag_default_is_false(self):
        """Test that --clean defaults to False when not provided."""
        parser = create_parser()
        args = parser.parse_args([])

        assert args.clean is False

    def test_clean_flag_set_to_true(self):
        """Test that --clean sets the flag to True."""
        parser = create_parser()
        args = parser.parse_args([
            "--clean",
        ])

        assert args.clean is True

    def test_clean_flag_is_store_true_action(self):
        """Test that --clean is a boolean flag (not requiring a value)."""
        parser = create_parser()

        # Should work without a value after --clean
        args = parser.parse_args([
            "--clean",
            "--log-level", "DEBUG",
        ])

        assert args.clean is True
        assert args.log_level == "DEBUG"

    def test_clean_flag_combined_with_other_args(self):
        """Test that --clean works correctly alongside other arguments."""
        parser = create_parser()
        args = parser.parse_args([
            "--workspace-path", "workspaces/todo",
            "--config-dir", "/custom/config",
            "--repo-path", "/custom/source",
            "--clean",
            "--use-local",
            "--log-level", "WARNING",
        ])

        assert args.clean is True
        assert args.use_local is True
        assert str(args.config_dir) == "/custom/config"
        assert str(args.repo_path) == "/custom/source"
        assert args.log_level == "WARNING"


class TestCreateParserSourceRepoArgument:
    """Tests for the --source-repo and --source-ref CLI arguments."""

    def test_source_repo_default_is_none(self):
        """Test that --source-repo defaults to None when not provided."""
        parser = create_parser()
        args = parser.parse_args([])

        assert args.source_repo is None

    def test_source_ref_default_is_none(self):
        """Test that --source-ref defaults to None when not provided."""
        parser = create_parser()
        args = parser.parse_args([])

        assert args.source_ref is None

    def test_source_repo_set(self):
        """Test that --source-repo is correctly parsed."""
        parser = create_parser()
        args = parser.parse_args([
            "--source-repo", "https://github.com/backstage/community-plugins",
        ])

        assert args.source_repo == "https://github.com/backstage/community-plugins"
        assert args.source_ref is None

    def test_source_ref_set(self):
        """Test that --source-ref is correctly parsed alongside --source-repo."""
        parser = create_parser()
        args = parser.parse_args([
            "--source-repo", "https://github.com/backstage/community-plugins",
            "--source-ref", "abc123",
        ])

        assert args.source_repo == "https://github.com/backstage/community-plugins"
        assert args.source_ref == "abc123"

    def test_source_args_combined_with_workspace_path(self):
        """Test that source args work alongside --workspace-path."""
        parser = create_parser()
        args = parser.parse_args([
            "--source-repo", "https://github.com/backstage/community-plugins",
            "--source-ref", "main",
            "--workspace-path", "workspaces/todo",
        ])

        assert args.source_repo == "https://github.com/backstage/community-plugins"
        assert args.source_ref == "main"
        assert str(args.workspace_path) == "workspaces/todo"


class TestRunSourceArgValidation:
    """Tests for --source-repo/--source-ref validation in _run().
    
    The validation now occurs in PluginFactoryConfig.__post_init__,
    which is called during load_from_env() inside _run().
    """

    def test_source_ref_without_source_repo_raises_error(self, mock_args, monkeypatch):
        """Test that --source-ref without --source-repo raises ConfigurationError."""
        # RHDH_CLI_VERSION must be set so __post_init__ reaches the source arg check
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        
        mock_args.source_ref = "main"
        mock_args.source_repo = None

        with pytest.raises(ConfigurationError, match="--source-ref requires --source-repo"):
            _run(mock_args)
