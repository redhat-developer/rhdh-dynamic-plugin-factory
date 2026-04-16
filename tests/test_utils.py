"""
Unit tests for utility functions.
"""

from src.rhdh_dynamic_plugin_factory.utils import collect_build_logs


class TestCollectBuildLogs:
    """Tests for collect_build_logs function."""

    def test_displays_build_log_contents(self, tmp_path, mock_logger):
        """Test that build log contents are logged with the full file path."""
        log_dir = tmp_path / "xfs-abc123"
        log_dir.mkdir()
        log_file = log_dir / "build.log"
        log_file.write_text("gyp ERR! build error\ngyp ERR! not ok")

        collect_build_logs(mock_logger, tmp_dir=tmp_path)

        mock_logger.warning.assert_any_call(f"[yellow]Build log: {log_file}[/yellow]")
        mock_logger.warning.assert_any_call("  gyp ERR! build error")
        mock_logger.warning.assert_any_call("  gyp ERR! not ok")

    def test_displays_multiple_build_logs(self, tmp_path, mock_logger):
        """Test that all build.log files are found and displayed."""
        for name in ("xfs-aaa", "xfs-bbb"):
            d = tmp_path / name
            d.mkdir()
            (d / "build.log").write_text(f"error in {name}")

        collect_build_logs(mock_logger, tmp_dir=tmp_path)

        logged_lines = [call[0][0] for call in mock_logger.warning.call_args_list]
        assert any("xfs-aaa" in line and "Build log:" in line for line in logged_lines)
        assert any("xfs-bbb" in line and "Build log:" in line for line in logged_lines)

    def test_no_build_logs_found(self, tmp_path, mock_logger):
        """Test that a 'no build logs found' message is logged when none exist."""
        collect_build_logs(mock_logger, tmp_dir=tmp_path)

        mock_logger.warning.assert_called_once()
        assert "No build logs found" in mock_logger.warning.call_args[0][0]

    def test_warns_on_empty_build_logs(self, tmp_path, mock_logger):
        """Test that empty build.log files produce a warning."""
        log_dir = tmp_path / "xfs-empty"
        log_dir.mkdir()
        log_file = log_dir / "build.log"
        log_file.write_text("")

        collect_build_logs(mock_logger, tmp_dir=tmp_path)

        mock_logger.warning.assert_any_call(f"[yellow]Empty build log: {log_file}[/yellow]")

    def test_handles_unreadable_build_log(self, tmp_path, mock_logger):
        """Test that unreadable files are reported but don't cause a crash."""
        log_dir = tmp_path / "xfs-noperm"
        log_dir.mkdir()
        log_file = log_dir / "build.log"
        log_file.write_text("some content")
        log_file.chmod(0o000)

        try:
            collect_build_logs(mock_logger, tmp_dir=tmp_path)

            logged_lines = [call[0][0] for call in mock_logger.warning.call_args_list]
            assert any("Could not read build log" in line for line in logged_lines)
        finally:
            log_file.chmod(0o644)

    def test_finds_nested_build_logs(self, tmp_path, mock_logger):
        """Test that build.log files in deeply nested directories are found."""
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        log_file = nested / "build.log"
        log_file.write_text("nested error")

        collect_build_logs(mock_logger, tmp_dir=tmp_path)

        mock_logger.warning.assert_any_call(f"[yellow]Build log: {log_file}[/yellow]")
        mock_logger.warning.assert_any_call("  nested error")

    def test_defaults_to_system_tmp(self, mock_logger):
        """Test that tmp_dir defaults to the system temp directory."""
        collect_build_logs(mock_logger)
        # Should not raise; may or may not find logs depending on system state

    def test_summary_message_includes_count(self, tmp_path, mock_logger):
        """Test that the summary message shows the correct log count."""
        for i in range(3):
            d = tmp_path / f"dir-{i}"
            d.mkdir()
            (d / "build.log").write_text(f"error {i}")

        collect_build_logs(mock_logger, tmp_dir=tmp_path)

        mock_logger.warning.assert_any_call(
            "[yellow]Found 3 build log(s) that may contain details about the failure:[/yellow]"
        )
