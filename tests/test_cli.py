"""
Unit tests for CLI argument parsing.

Tests the argument parser to ensure all arguments are correctly defined and parsed.
"""

from src.rhdh_dynamic_plugin_factory.cli import create_parser


class TestCreateParserCleanArgument:
    """Tests for the --clean CLI argument."""

    def test_clean_flag_default_is_false(self):
        """Test that --clean defaults to False when not provided."""
        parser = create_parser()
        args = parser.parse_args([
            "--workspace-path", "workspaces/todo",
        ])

        assert args.clean is False

    def test_clean_flag_set_to_true(self):
        """Test that --clean sets the flag to True."""
        parser = create_parser()
        args = parser.parse_args([
            "--workspace-path", "workspaces/todo",
            "--clean",
        ])

        assert args.clean is True

    def test_clean_flag_is_store_true_action(self):
        """Test that --clean is a boolean flag (not requiring a value)."""
        parser = create_parser()

        # Should work without a value after --clean
        args = parser.parse_args([
            "--workspace-path", "workspaces/todo",
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
