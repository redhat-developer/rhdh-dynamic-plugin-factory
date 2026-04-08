"""
Unit tests for multi-workspace support.

Tests workspace discovery, mode detection, WorkspaceInfo, .env inheritance,
git worktree cloning, and per-workspace path management.
"""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.rhdh_dynamic_plugin_factory.config import PluginFactoryConfig
from src.rhdh_dynamic_plugin_factory.source_config import (
    SourceConfig,
    WorkspaceInfo,
    discover_workspaces,
    clone_workspaces_with_worktrees,
)
from src.rhdh_dynamic_plugin_factory.utils import repo_dir_name
from src.rhdh_dynamic_plugin_factory.cli import (
    _run,
    _run_multi_workspace,
    _load_env_for_workspace,
)
from src.rhdh_dynamic_plugin_factory.exceptions import PluginFactoryError, ConfigurationError, ExecutionError


class TestWorkspaceInfo:
    """Tests for WorkspaceInfo dataclass."""

    def test_resolve_paths(self, tmp_path):
        """Test that resolve_paths sets repo_path and output_dir correctly."""
        ws = WorkspaceInfo(
            name="todo",
            config_dir=tmp_path / "config" / "todo",
            source_config=MagicMock(),
        )
        
        base_repo = tmp_path / "source"
        base_output = tmp_path / "outputs"
        ws.resolve_paths(base_repo, base_output)
        
        assert ws.repo_path == base_repo / "todo"
        assert ws.output_dir == base_output / "todo"
    
    def test_paths_default_to_none(self):
        """Test that repo_path and output_dir default to None."""
        ws = WorkspaceInfo(
            name="test",
            config_dir=Path("/tmp/test"),
            source_config=MagicMock(),
        )
        
        assert ws.repo_path is None
        assert ws.output_dir is None


class TestDiscoverWorkspaces:
    """Tests for discover_workspaces function."""
    
    def test_discovers_multiple_workspaces(self, tmp_path, write_source_json):
        """Test discovering multiple workspaces with source.json files."""
        write_source_json(tmp_path / "todo", "https://github.com/backstage/community-plugins", "main", "workspaces/todo")
        write_source_json(tmp_path / "aws-ecs", "https://github.com/awslabs/backstage-plugins-for-aws", "abc123", ".")
        
        with patch.object(SourceConfig, "resolve_default_ref", return_value="refs/heads/main"):
            workspaces = discover_workspaces(tmp_path)
        
        assert len(workspaces) == 2
        names = [ws.name for ws in workspaces]
        assert "todo" in names
        assert "aws-ecs" in names
    
    def test_sorted_by_repo_then_name(self, tmp_path, write_source_json):
        """Test that workspaces are sorted by repo URL then name."""
        write_source_json(tmp_path / "zz-ws", "https://github.com/aaa/repo", "main", ".")
        write_source_json(tmp_path / "aa-ws", "https://github.com/zzz/repo", "main", ".")
        write_source_json(tmp_path / "bb-ws", "https://github.com/aaa/repo", "v1.0", ".")
        
        with patch.object(SourceConfig, "resolve_default_ref", return_value="refs/heads/main"):
            workspaces = discover_workspaces(tmp_path)
        
        # aaa/repo workspaces first (sorted by name), then zzz/repo
        assert workspaces[0].name == "bb-ws"
        assert workspaces[1].name == "zz-ws"
        assert workspaces[2].name == "aa-ws"
    
    def test_ignores_directories_without_source_json(self, tmp_path, write_source_json):
        """Test that directories without source.json are ignored."""
        write_source_json(tmp_path / "valid", "https://github.com/test/repo", "main", ".")
        (tmp_path / "patches").mkdir()
        (tmp_path / "no-source").mkdir()
        (tmp_path / ".env").write_text("KEY=VALUE")
        
        with patch.object(SourceConfig, "resolve_default_ref", return_value="refs/heads/main"):
            workspaces = discover_workspaces(tmp_path)
        
        assert len(workspaces) == 1
        assert workspaces[0].name == "valid"
    
    def test_empty_config_dir(self, tmp_path):
        """Test that empty config dir returns empty list."""
        workspaces = discover_workspaces(tmp_path)
        assert workspaces == []
    
    def test_nonexistent_config_dir(self, tmp_path):
        """Test that nonexistent config dir returns empty list."""
        workspaces = discover_workspaces(tmp_path / "nonexistent")
        assert workspaces == []
    
    def test_files_at_root_ignored(self, tmp_path):
        """Test that files (not directories) at config root are ignored."""
        (tmp_path / "source.json").write_text('{"repo": "test", "repo-ref": "main"}')
        (tmp_path / "plugins-list.yaml").write_text("plugins/foo:")
        
        workspaces = discover_workspaces(tmp_path)
        assert workspaces == []
    
    def test_invalid_source_json_raises_error(self, tmp_path):
        """Test that invalid source.json in a workspace raises ConfigurationError."""
        ws_dir = tmp_path / "bad-workspace"
        ws_dir.mkdir()
        (ws_dir / "source.json").write_text("{ invalid json }")
        
        with pytest.raises(ConfigurationError, match="Invalid JSON"):
            discover_workspaces(tmp_path)
    
    def test_single_workspace_subdirectory(self, tmp_path, write_source_json):
        """Test that even a single subdirectory with source.json is detected."""
        write_source_json(tmp_path / "only-one", "https://github.com/test/repo", "v1.0", ".")
        
        workspaces = discover_workspaces(tmp_path)
        
        assert len(workspaces) == 1
        assert workspaces[0].name == "only-one"
        assert workspaces[0].source_config.repo == "https://github.com/test/repo"


class TestModeDetection:
    """Tests for mode detection in _run()."""
    
    def test_multi_workspace_rejects_source_repo(self, tmp_path, mock_args, monkeypatch, write_source_json):
        """Test that --source-repo is rejected in multi-workspace mode."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        config_dir = tmp_path / "config"
        write_source_json(config_dir / "ws1", "https://github.com/test/repo", "main", ".")
        
        mock_args.config_dir = config_dir
        mock_args.source_repo = "https://github.com/other/repo"
        
        with pytest.raises(ConfigurationError, match="--source-repo cannot be used in multi-workspace mode"):
            _run(mock_args)
    
    def test_multi_workspace_rejects_source_ref(self, tmp_path, mock_args, monkeypatch, write_source_json):
        """Test that --source-ref is rejected in multi-workspace mode."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        config_dir = tmp_path / "config"
        write_source_json(config_dir / "ws1", "https://github.com/test/repo", "main", ".")
        
        mock_args.config_dir = config_dir
        mock_args.source_ref = "v1.0"
        
        with pytest.raises(ConfigurationError, match="--source-ref cannot be used in multi-workspace mode"):
            _run(mock_args)
    
    def test_multi_workspace_rejects_workspace_path(self, tmp_path, mock_args, monkeypatch, write_source_json):
        """Test that --workspace-path is rejected in multi-workspace mode."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        config_dir = tmp_path / "config"
        write_source_json(config_dir / "ws1", "https://github.com/test/repo", "main", ".")
        
        mock_args.config_dir = config_dir
        mock_args.workspace_path = "workspaces/todo"
        
        with pytest.raises(ConfigurationError, match="--workspace-path cannot be used in multi-workspace mode"):
            _run(mock_args)
    
    def test_no_workspaces_uses_single_mode(self, tmp_path, mock_args, monkeypatch):
        """Test that empty config dir uses single-workspace mode."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True)
        
        mock_args.config_dir = config_dir
        mock_args.workspace_path = "."
        
        # Should call _run_single_workspace path (will fail at source validation, but mode is correct)
        with patch("src.rhdh_dynamic_plugin_factory.cli._run_single_workspace") as mock_single:
            _run(mock_args)
            mock_single.assert_called_once_with(mock_args)

    def test_multi_workspace_skips_root_source_and_plugins_validation(
        self, tmp_path, mock_args, monkeypatch, write_source_json
    ):
        """Test that multi-workspace mode does NOT emit root-level source.json / plugins-list.yaml warnings."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")

        config_dir = tmp_path / "config"
        write_source_json(config_dir / "ws1", "https://github.com/test/repo", "main", ".")

        mock_args.config_dir = config_dir
        mock_args.repo_path = tmp_path / "source"
        mock_args.output_dir = tmp_path / "outputs"
        mock_args.clean = True
        mock_args.workspace_path = None

        with patch("src.rhdh_dynamic_plugin_factory.cli.clone_workspaces_with_worktrees"), \
             patch("src.rhdh_dynamic_plugin_factory.cli._process_workspace"), \
             patch("src.rhdh_dynamic_plugin_factory.config.PluginFactoryConfig._validate_source_json") as mock_src, \
             patch("src.rhdh_dynamic_plugin_factory.config.PluginFactoryConfig._validate_plugins_list") as mock_pl:
            try:
                _run_multi_workspace(mock_args, discover_workspaces(config_dir))
            except Exception:
                pass

            mock_src.assert_not_called()
            mock_pl.assert_not_called()


class TestRepoDirName:
    """Tests for repo_dir_name helper."""
    
    def test_https_url(self):
        assert repo_dir_name("https://github.com/backstage/community-plugins") == "community-plugins"
    
    def test_https_url_with_git_suffix(self):
        assert repo_dir_name("https://github.com/git/git.git") == "git"
    
    def test_trailing_slash(self):
        assert repo_dir_name("https://github.com/backstage/community-plugins/") == "community-plugins"
    
    def test_ssh_url(self):
        assert repo_dir_name("git@github.com:backstage/community-plugins.git") == "community-plugins"


class TestEnvInheritance:
    """Tests for .env inheritance and isolation between workspaces."""
    
    def test_load_env_for_workspace_layered(self, tmp_path, monkeypatch):
        """Test that workspace .env overrides base_env values."""
        ws_env = tmp_path / "ws.env"
        ws_env.write_text("LEVEL=workspace\nWS_ONLY=yes\n")
        
        snapshot = dict(os.environ)
        
        # base_env simulates Podman + default.env + root .env already loaded
        base_env = dict(snapshot)
        base_env["LEVEL"] = "root"
        base_env["DEFAULT_ONLY"] = "yes"
        base_env["ROOT_ONLY"] = "yes"
        
        _load_env_for_workspace(base_env, ws_env)
        
        # Workspace .env should win for LEVEL
        assert os.environ.get("LEVEL") == "workspace"
        assert os.environ.get("DEFAULT_ONLY") == "yes"
        assert os.environ.get("ROOT_ONLY") == "yes"
        assert os.environ.get("WS_ONLY") == "yes"
        
        # Restore
        os.environ.clear()
        os.environ.update(snapshot)
    
    def test_load_env_isolates_between_workspaces(self, tmp_path, monkeypatch):
        """Test that env from one workspace doesn't leak into the next."""
        ws1_env = tmp_path / "ws1.env"
        ws1_env.write_text("WS1_SECRET=secret1\n")
        
        ws2_env = tmp_path / "ws2.env"
        ws2_env.write_text("WS2_VALUE=value2\n")
        
        base_env = dict(os.environ)
        
        # Load workspace 1
        _load_env_for_workspace(base_env, ws1_env)
        assert os.environ.get("WS1_SECRET") == "secret1"
        
        # Load workspace 2 -- ws1 vars should be gone
        _load_env_for_workspace(base_env, ws2_env)
        assert os.environ.get("WS1_SECRET") is None
        assert os.environ.get("WS2_VALUE") == "value2"
        
        # Restore
        os.environ.clear()
        os.environ.update(base_env)
    
    def test_load_env_missing_files_no_error(self, tmp_path):
        """Test that a missing workspace .env is silently skipped."""
        base_env = dict(os.environ)
        
        _load_env_for_workspace(base_env, tmp_path / "nonexistent.env")
        
        # Restore
        os.environ.clear()
        os.environ.update(base_env)
    
    def test_podman_env_var_precedence(self, tmp_path):
        """Test precedence: workspace .env > root .env > Podman/system env vars > default.env.
        
        base_env simulates the state after load_from_env has already applied
        default.env (no override) and root .env (override) on top of Podman/system vars.
        """
        ws_env = tmp_path / "ws.env"
        ws_env.write_text("ROOT_VAR=from_workspace\n")
        
        original_snapshot = dict(os.environ)
        
        # base_env simulates: Podman vars + default.env (no override) + root .env (override)
        # Podman had PODMAN_VAR, SHARED_VAR, DEFAULT_VAR
        # default.env tried DEFAULT_VAR=from_default, SHARED_VAR=from_default (no override -> Podman wins)
        # root .env set SHARED_VAR=from_root (override -> root wins), ROOT_VAR=from_root
        base_env = dict(original_snapshot)
        base_env["PODMAN_VAR"] = "from_podman"
        base_env["DEFAULT_VAR"] = "from_podman"
        base_env["SHARED_VAR"] = "from_root"
        base_env["ROOT_VAR"] = "from_root"
        
        _load_env_for_workspace(base_env, ws_env)
        
        # Podman-only var survives (not overridden by any .env file)
        assert os.environ.get("PODMAN_VAR") == "from_podman"
        # default.env did NOT override Podman var (already baked into base_env)
        assert os.environ.get("DEFAULT_VAR") == "from_podman"
        # root .env DID override Podman var (already baked into base_env)
        assert os.environ.get("SHARED_VAR") == "from_root"
        # workspace .env overrides root .env
        assert os.environ.get("ROOT_VAR") == "from_workspace"
        
        # Restore
        os.environ.clear()
        os.environ.update(original_snapshot)


class TestCloneWorkspacesWithWorktrees:
    """Tests for clone_workspaces_with_worktrees function."""
    
    def test_groups_by_repo_and_clones_once(self, tmp_path):
        """Test that the same repo is only cloned once for multiple workspaces."""
        base_repo = tmp_path / "source"
        base_repo.mkdir()
        
        ws1 = WorkspaceInfo(
            name="ws1",
            config_dir=tmp_path / "config" / "ws1",
            source_config=MagicMock(repo="https://github.com/test/repo", repo_ref="main"),
            repo_path=base_repo / "ws1",
            output_dir=tmp_path / "out" / "ws1",
        )
        ws2 = WorkspaceInfo(
            name="ws2",
            config_dir=tmp_path / "config" / "ws2",
            source_config=MagicMock(repo="https://github.com/test/repo", repo_ref="v1.0"),
            repo_path=base_repo / "ws2",
            output_dir=tmp_path / "out" / "ws2",
        )
        
        with patch("src.rhdh_dynamic_plugin_factory.source_config.run_command_with_streaming", return_value=0) as mock_stream:
            clone_workspaces_with_worktrees([ws1, ws2], base_repo)
            
            cmds = [c[0][0] for c in mock_stream.call_args_list]
            clone_cmds = [c for c in cmds if "clone" in c]
            worktree_cmds = [c for c in cmds if "worktree" in c]
            
            assert len(clone_cmds) == 1
            assert len(worktree_cmds) == 2
    
    def test_raises_if_repo_path_not_set(self, tmp_path):
        """Test that missing repo_path raises PluginFactoryError."""
        base_repo = tmp_path / "source"
        base_repo.mkdir()
        
        ws = WorkspaceInfo(
            name="test",
            config_dir=tmp_path,
            source_config=MagicMock(repo="https://github.com/test/repo", repo_ref="main"),
            repo_path=None,
        )
        
        with patch("src.rhdh_dynamic_plugin_factory.source_config.run_command_with_streaming", return_value=0):
            with pytest.raises(PluginFactoryError, match="no resolved repository path"):
                clone_workspaces_with_worktrees([ws], base_repo)
    
    def test_clone_failure_raises_error(self, tmp_path):
        """Test that git clone failure raises ExecutionError."""
        base_repo = tmp_path / "source"
        base_repo.mkdir()
        
        ws = WorkspaceInfo(
            name="ws1",
            config_dir=tmp_path / "config" / "ws1",
            source_config=MagicMock(repo="https://github.com/test/nonexistent", repo_ref="main"),
            repo_path=base_repo / "ws1",
            output_dir=tmp_path / "out" / "ws1",
        )
        
        with patch("src.rhdh_dynamic_plugin_factory.source_config.run_command_with_streaming", return_value=128):
            with pytest.raises(ExecutionError, match="Failed to clone repository"):
                clone_workspaces_with_worktrees([ws], base_repo)
    
    def test_multiple_repos_each_cloned_once(self, tmp_path):
        """Test that different repos are each cloned once."""
        base_repo = tmp_path / "source"
        base_repo.mkdir()
        
        ws1 = WorkspaceInfo(
            name="ws1",
            config_dir=tmp_path / "config" / "ws1",
            source_config=MagicMock(repo="https://github.com/org/repo-a", repo_ref="main"),
            repo_path=base_repo / "ws1",
            output_dir=tmp_path / "out" / "ws1",
        )
        ws2 = WorkspaceInfo(
            name="ws2",
            config_dir=tmp_path / "config" / "ws2",
            source_config=MagicMock(repo="https://github.com/org/repo-b", repo_ref="v1.0"),
            repo_path=base_repo / "ws2",
            output_dir=tmp_path / "out" / "ws2",
        )
        
        with patch("src.rhdh_dynamic_plugin_factory.source_config.run_command_with_streaming", return_value=0) as mock_stream:
            clone_workspaces_with_worktrees([ws1, ws2], base_repo)
            
            cmds = [c[0][0] for c in mock_stream.call_args_list]
            clone_cmds = [c for c in cmds if "clone" in c]
            worktree_cmds = [c for c in cmds if "worktree" in c]
            
            assert len(clone_cmds) == 2
            assert len(worktree_cmds) == 2


class TestCloneWorkspacesWithWorktreesIntegration:
    """Integration tests for clone_workspaces_with_worktrees using real git operations.
    
    Verifies that worktrees are created at the correct paths with the expected
    file contents, not just that git commands are invoked.
    """

    @staticmethod
    def _create_test_repo(tmp_path: Path, name: str = "test-repo",
                          files: dict[str, str] | None = None) -> tuple[Path, str]:
        """Create a real local git repository with known files.
        
        Returns:
            Tuple of (repo_path, commit_sha).
        """
        repo = tmp_path / name
        repo.mkdir()

        files = files or {"package.json": '{"name": "test"}'}
        for relpath, content in files.items():
            fpath = repo / relpath
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content)

        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init", "--author", "test <test@test.com>"],
            cwd=repo, capture_output=True, check=True,
            env={**os.environ, "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@test.com"},
        )
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()
        return repo, sha

    def test_worktree_contains_expected_files(self, tmp_path):
        """Test that worktree directories contain actual checked-out files."""
        origin, sha = self._create_test_repo(tmp_path, files={
            "package.json": '{"name": "root"}',
            "src/index.ts": "export {}",
            "plugins/ecs/README.md": "# ECS Plugin",
        })

        base_repo = tmp_path / "source"
        base_repo.mkdir()

        ws = WorkspaceInfo(
            name="ws1",
            config_dir=tmp_path / "config" / "ws1",
            source_config=SourceConfig(repo=str(origin), repo_ref=sha, workspace_path="."),
            repo_path=base_repo / "ws1",
            output_dir=tmp_path / "out" / "ws1",
        )

        clone_workspaces_with_worktrees([ws], base_repo)

        assert (base_repo / "ws1" / "package.json").exists()
        assert (base_repo / "ws1" / "package.json").read_text() == '{"name": "root"}'
        assert (base_repo / "ws1" / "src" / "index.ts").exists()
        assert (base_repo / "ws1" / "plugins" / "ecs" / "README.md").exists()

    def test_worktree_with_nested_workspace_path(self, tmp_path):
        """Test that a workspace_path like 'workspaces/todo' exists inside the worktree."""
        origin, sha = self._create_test_repo(tmp_path, files={
            "package.json": '{"name": "monorepo"}',
            "workspaces/todo/package.json": '{"name": "todo"}',
            "workspaces/todo/src/index.ts": "export const TODO = true;",
        })

        base_repo = tmp_path / "source"
        base_repo.mkdir()

        ws = WorkspaceInfo(
            name="todo",
            config_dir=tmp_path / "config" / "todo",
            source_config=SourceConfig(repo=str(origin), repo_ref=sha, workspace_path="workspaces/todo"),
            repo_path=base_repo / "todo",
            output_dir=tmp_path / "out" / "todo",
        )

        clone_workspaces_with_worktrees([ws], base_repo)

        workspace_full = base_repo / "todo" / "workspaces" / "todo"
        assert workspace_full.exists(), "Nested workspace path must exist in worktree"
        assert (workspace_full / "package.json").read_text() == '{"name": "todo"}'
        assert (workspace_full / "src" / "index.ts").exists()

    def test_multiple_worktrees_from_same_repo(self, tmp_path):
        """Test that two workspaces from the same repo get independent worktrees."""
        origin, sha = self._create_test_repo(tmp_path, files={
            "package.json": '{"name": "shared"}',
            "workspaces/a/file.txt": "workspace-a",
            "workspaces/b/file.txt": "workspace-b",
        })

        base_repo = tmp_path / "source"
        base_repo.mkdir()

        ws_a = WorkspaceInfo(
            name="ws-a",
            config_dir=tmp_path / "config" / "ws-a",
            source_config=SourceConfig(repo=str(origin), repo_ref=sha, workspace_path="workspaces/a"),
            repo_path=base_repo / "ws-a",
            output_dir=tmp_path / "out" / "ws-a",
        )
        ws_b = WorkspaceInfo(
            name="ws-b",
            config_dir=tmp_path / "config" / "ws-b",
            source_config=SourceConfig(repo=str(origin), repo_ref=sha, workspace_path="workspaces/b"),
            repo_path=base_repo / "ws-b",
            output_dir=tmp_path / "out" / "ws-b",
        )

        clone_workspaces_with_worktrees([ws_a, ws_b], base_repo)

        assert (base_repo / "ws-a" / "workspaces" / "a" / "file.txt").read_text() == "workspace-a"
        assert (base_repo / "ws-b" / "workspaces" / "b" / "file.txt").read_text() == "workspace-b"
        # Both worktrees have the full repo content
        assert (base_repo / "ws-a" / "package.json").exists()
        assert (base_repo / "ws-b" / "package.json").exists()

    def test_worktrees_from_different_repos(self, tmp_path):
        """Test that workspaces from different repos each get correct content."""
        origin_a, sha_a = self._create_test_repo(tmp_path, name="repo-a", files={
            "package.json": '{"name": "repo-a"}',
        })
        origin_b, sha_b = self._create_test_repo(tmp_path, name="repo-b", files={
            "package.json": '{"name": "repo-b"}',
        })

        base_repo = tmp_path / "source"
        base_repo.mkdir()

        ws_a = WorkspaceInfo(
            name="ws-a",
            config_dir=tmp_path / "config" / "ws-a",
            source_config=SourceConfig(repo=str(origin_a), repo_ref=sha_a, workspace_path="."),
            repo_path=base_repo / "ws-a",
            output_dir=tmp_path / "out" / "ws-a",
        )
        ws_b = WorkspaceInfo(
            name="ws-b",
            config_dir=tmp_path / "config" / "ws-b",
            source_config=SourceConfig(repo=str(origin_b), repo_ref=sha_b, workspace_path="."),
            repo_path=base_repo / "ws-b",
            output_dir=tmp_path / "out" / "ws-b",
        )

        clone_workspaces_with_worktrees([ws_a, ws_b], base_repo)

        assert (base_repo / "ws-a" / "package.json").read_text() == '{"name": "repo-a"}'
        assert (base_repo / "ws-b" / "package.json").read_text() == '{"name": "repo-b"}'

    def test_git_apply_works_in_worktree(self, tmp_path):
        """Test that git apply works correctly inside a worktree (patch paths resolve properly)."""
        origin, sha = self._create_test_repo(tmp_path, files={
            "package.json": '{"version": "1.0.0"}\n',
        })

        base_repo = tmp_path / "source"
        base_repo.mkdir()

        ws = WorkspaceInfo(
            name="ws1",
            config_dir=tmp_path / "config" / "ws1",
            source_config=SourceConfig(repo=str(origin), repo_ref=sha, workspace_path="."),
            repo_path=base_repo / "ws1",
            output_dir=tmp_path / "out" / "ws1",
        )

        clone_workspaces_with_worktrees([ws], base_repo)

        patch_content = (
            '--- a/package.json\n'
            '+++ b/package.json\n'
            '@@ -1 +1 @@\n'
            '-{"version": "1.0.0"}\n'
            '+{"version": "2.0.0"}\n'
        )
        patch_file = tmp_path / "test.patch"
        patch_file.write_text(patch_content)

        worktree = base_repo / "ws1"
        result = subprocess.run(
            ["git", "apply", str(patch_file)],
            cwd=worktree, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"git apply failed: {result.stderr}"
        assert (worktree / "package.json").read_text() == '{"version": "2.0.0"}\n'

class TestApplyPatchesAndOverlaysIntegration:
    """Integration tests for apply_patches_and_overlays with real git worktrees.

    Verifies that overlays are applied in the workspace subdirectory and that
    patches work correctly when workspace_path is ``"."``.
    """

    @staticmethod
    def _create_test_repo(tmp_path: Path, files: dict[str, str]) -> tuple[Path, str]:
        repo = tmp_path / "origin"
        repo.mkdir()
        for relpath, content in files.items():
            fpath = repo / relpath
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content)
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init", "--author", "test <test@test.com>"],
            cwd=repo, capture_output=True, check=True,
            env={**os.environ, "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@test.com"},
        )
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()
        return repo, sha

    def test_overlays_applied_in_workspace_subdir(self, tmp_path, monkeypatch):
        """Overlays are copied into the workspace subdirectory, not the repo root."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")

        origin, sha = self._create_test_repo(tmp_path, files={
            "package.json": '{"name": "monorepo"}\n',
            "workspaces/todo/plugins/todo/index.ts": "export {};\n",
        })

        base_repo = tmp_path / "source"
        base_repo.mkdir()

        ws = WorkspaceInfo(
            name="todo",
            config_dir=tmp_path / "config" / "todo",
            source_config=SourceConfig(repo=str(origin), repo_ref=sha, workspace_path="workspaces/todo"),
            repo_path=base_repo / "todo",
            output_dir=tmp_path / "out" / "todo",
        )
        clone_workspaces_with_worktrees([ws], base_repo)

        # Set up config dir with plugins-list.yaml and an overlay
        config_dir = tmp_path / "config" / "todo"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "plugins-list.yaml").write_text("plugins/todo:\n")

        overlay_dir = config_dir / "plugins" / "todo" / "overlay"
        overlay_dir.mkdir(parents=True)
        (overlay_dir / "scalprum-config.json").write_text('{"overlay": true}\n')

        config = PluginFactoryConfig(
            rhdh_cli_version="1.7.2",
            repo_path=str(base_repo / "todo"),
            config_dir=str(config_dir),
            workspace_path="workspaces/todo",
        )

        config.apply_patches_and_overlays(
            config_dir=str(config_dir),
            repo_path=str(base_repo / "todo"),
            workspace_path="workspaces/todo",
        )

        workspace_dir = base_repo / "todo" / "workspaces" / "todo"
        assert (workspace_dir / "plugins" / "todo" / "scalprum-config.json").read_text() == '{"overlay": true}\n'

    def test_workspace_path_dot_applies_both_at_same_dir(self, tmp_path, monkeypatch):
        """When workspace_path is '.', patches and overlays target the same directory."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")

        origin, sha = self._create_test_repo(tmp_path, files={
            "package.json": '{"version": "1.0.0"}\n',
            "plugins/ecs/index.ts": "export {};\n",
        })

        base_repo = tmp_path / "source"
        base_repo.mkdir()

        ws = WorkspaceInfo(
            name="ecs",
            config_dir=tmp_path / "config" / "ecs",
            source_config=SourceConfig(repo=str(origin), repo_ref=sha, workspace_path="."),
            repo_path=base_repo / "ecs",
            output_dir=tmp_path / "out" / "ecs",
        )
        clone_workspaces_with_worktrees([ws], base_repo)

        config_dir = tmp_path / "config" / "ecs"
        config_dir.mkdir(parents=True, exist_ok=True)

        patches_dir = config_dir / "patches"
        patches_dir.mkdir()
        (patches_dir / "1-bump.patch").write_text(
            '--- a/package.json\n'
            '+++ b/package.json\n'
            '@@ -1 +1 @@\n'
            '-{"version": "1.0.0"}\n'
            '+{"version": "2.0.0"}\n'
        )

        (config_dir / "plugins-list.yaml").write_text("plugins/ecs:\n")
        overlay_dir = config_dir / "plugins" / "ecs" / "overlay"
        overlay_dir.mkdir(parents=True)
        (overlay_dir / "config.json").write_text('{"cfg": true}\n')

        config = PluginFactoryConfig(
            rhdh_cli_version="1.7.2",
            repo_path=str(base_repo / "ecs"),
            config_dir=str(config_dir),
            workspace_path=".",
        )

        config.apply_patches_and_overlays(
            config_dir=str(config_dir),
            repo_path=str(base_repo / "ecs"),
            workspace_path=".",
        )

        worktree = base_repo / "ecs"
        assert (worktree / "package.json").read_text() == '{"version": "2.0.0"}\n'
        assert (worktree / "plugins" / "ecs" / "config.json").read_text() == '{"cfg": true}\n'


class TestUpfrontCleanInMultiWorkspace:
    """Tests for upfront source directory clean/prompt in _run_multi_workspace.
    
    In multi-workspace mode, the entire base_repo_path is cleaned once upfront
    before clone_workspaces_with_worktrees is called, mirroring single-workspace
    behavior where clone_to_path handles existing content.
    """
    
    def test_clean_flag_cleans_source_dir_before_cloning(self, tmp_path, mock_args, monkeypatch, write_source_json):
        """Test that --clean auto-cleans base_repo_path before worktree setup."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        
        config_dir = tmp_path / "config"
        write_source_json(config_dir / "ws1", "https://github.com/test/repo", "main", ".")
        
        base_repo = tmp_path / "source"
        base_repo.mkdir()
        (base_repo / "stale-content").write_text("old data")
        
        mock_args.config_dir = config_dir
        mock_args.repo_path = base_repo
        mock_args.output_dir = tmp_path / "outputs"
        mock_args.clean = True
        mock_args.workspace_path = None
        
        with patch("src.rhdh_dynamic_plugin_factory.cli.clone_workspaces_with_worktrees") as mock_clone, \
             patch("src.rhdh_dynamic_plugin_factory.cli.PluginFactoryConfig.load_from_env") as mock_load:
            mock_config = MagicMock()
            mock_config.use_local = False
            mock_load.return_value = mock_config
            
            try:
                _run_multi_workspace(mock_args, discover_workspaces(config_dir))
            except Exception:
                pass
            
            # base_repo_path should have been cleaned (stale-content removed)
            assert not (base_repo / "stale-content").exists()
            
            # clone_workspaces_with_worktrees should have been called
            mock_clone.assert_called_once()
    
    def test_no_clean_prompts_user_for_nonempty_source_dir(self, tmp_path, mock_args, monkeypatch, write_source_json):
        """Test that non-empty base_repo_path without --clean prompts user."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        
        config_dir = tmp_path / "config"
        write_source_json(config_dir / "ws1", "https://github.com/test/repo", "main", ".")
        
        base_repo = tmp_path / "source"
        base_repo.mkdir()
        (base_repo / "stale-content").write_text("old data")
        
        mock_args.config_dir = config_dir
        mock_args.repo_path = base_repo
        mock_args.output_dir = tmp_path / "outputs"
        mock_args.clean = False
        mock_args.workspace_path = None
        
        with patch("src.rhdh_dynamic_plugin_factory.cli.PluginFactoryConfig.load_from_env") as mock_load, \
             patch("builtins.input", return_value="n"):
            mock_config = MagicMock()
            mock_config.use_local = False
            mock_load.return_value = mock_config
            
            with pytest.raises(PluginFactoryError, match="aborted by user"):
                _run_multi_workspace(mock_args, discover_workspaces(config_dir))
    
    def test_empty_source_dir_skips_prompt(self, tmp_path, mock_args, monkeypatch, write_source_json):
        """Test that an empty base_repo_path proceeds without prompting."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        
        config_dir = tmp_path / "config"
        write_source_json(config_dir / "ws1", "https://github.com/test/repo", "main", ".")
        
        base_repo = tmp_path / "source"
        base_repo.mkdir()
        
        mock_args.config_dir = config_dir
        mock_args.repo_path = base_repo
        mock_args.output_dir = tmp_path / "outputs"
        mock_args.clean = False
        mock_args.workspace_path = None
        
        with patch("src.rhdh_dynamic_plugin_factory.cli.clone_workspaces_with_worktrees") as mock_clone, \
             patch("src.rhdh_dynamic_plugin_factory.cli.PluginFactoryConfig.load_from_env") as mock_load, \
             patch("builtins.input") as mock_input:
            mock_config = MagicMock()
            mock_config.use_local = False
            mock_load.return_value = mock_config
            
            try:
                _run_multi_workspace(mock_args, discover_workspaces(config_dir))
            except Exception:
                pass
            
            mock_input.assert_not_called()
            mock_clone.assert_called_once()


class TestIgnoredContentWarnings:
    """Tests that _run_multi_workspace warns about all non-workspace root-level content."""

    def test_warns_about_all_ignored_content(self, tmp_path, mock_args, monkeypatch, write_source_json):
        """Loose files and non-workspace dirs produce a single grouped warning."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")

        config_dir = tmp_path / "config"
        write_source_json(config_dir / "ws1", "https://github.com/test/repo", "main", ".")

        # Intentionally ignored root-level content
        (config_dir / "source.json").write_text('{"repo":"x"}')
        (config_dir / "plugins-list.yaml").write_text("plugins/foo:")
        (config_dir / "notes.txt").write_text("scratch")
        (config_dir / "patches").mkdir()
        (config_dir / ".env").write_text("ROOT=1")

        mock_args.config_dir = config_dir
        mock_args.repo_path = tmp_path / "source"
        mock_args.output_dir = tmp_path / "outputs"
        mock_args.clean = True
        mock_args.workspace_path = None

        with patch("src.rhdh_dynamic_plugin_factory.cli.clone_workspaces_with_worktrees"), \
             patch("src.rhdh_dynamic_plugin_factory.cli.PluginFactoryConfig.load_from_env") as mock_load, \
             patch("src.rhdh_dynamic_plugin_factory.cli.logger") as mock_logger:
            mock_config = MagicMock()
            mock_config.use_local = False
            mock_load.return_value = mock_config

            try:
                _run_multi_workspace(mock_args, discover_workspaces(config_dir))
            except Exception:
                pass

            warning_calls = [
                c for c in mock_logger.warning.call_args_list
                if "will be ignored" in str(c)
            ]
            assert len(warning_calls) == 1
            msg = warning_calls[0][0][0]
            assert "notes.txt" in msg
            assert "source.json" in msg
            assert "plugins-list.yaml" in msg
            assert "patches/" in msg
            assert ".env" not in msg

    def test_no_warning_when_only_workspaces_and_env(self, tmp_path, mock_args, monkeypatch, write_source_json):
        """No ignored-content warning when root only has workspaces and .env."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")

        config_dir = tmp_path / "config"
        write_source_json(config_dir / "ws1", "https://github.com/test/repo", "main", ".")
        (config_dir / ".env").write_text("ROOT=1")

        mock_args.config_dir = config_dir
        mock_args.repo_path = tmp_path / "source"
        mock_args.output_dir = tmp_path / "outputs"
        mock_args.clean = True
        mock_args.workspace_path = None

        with patch("src.rhdh_dynamic_plugin_factory.cli.clone_workspaces_with_worktrees"), \
             patch("src.rhdh_dynamic_plugin_factory.cli.PluginFactoryConfig.load_from_env") as mock_load, \
             patch("src.rhdh_dynamic_plugin_factory.cli.logger") as mock_logger:
            mock_config = MagicMock()
            mock_config.use_local = False
            mock_load.return_value = mock_config

            try:
                _run_multi_workspace(mock_args, discover_workspaces(config_dir))
            except Exception:
                pass

            warning_calls = [
                c for c in mock_logger.warning.call_args_list
                if "will be ignored" in str(c)
            ]
            assert len(warning_calls) == 0

    def test_distinguishes_files_from_directories(self, tmp_path, mock_args, monkeypatch, write_source_json):
        """Warning labels files as '(file)' and dirs as '(directory ...)'."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")

        config_dir = tmp_path / "config"
        write_source_json(config_dir / "ws1", "https://github.com/test/repo", "main", ".")
        (config_dir / "stray.txt").write_text("data")
        (config_dir / "leftover").mkdir()

        mock_args.config_dir = config_dir
        mock_args.repo_path = tmp_path / "source"
        mock_args.output_dir = tmp_path / "outputs"
        mock_args.clean = True
        mock_args.workspace_path = None

        with patch("src.rhdh_dynamic_plugin_factory.cli.clone_workspaces_with_worktrees"), \
             patch("src.rhdh_dynamic_plugin_factory.cli.PluginFactoryConfig.load_from_env") as mock_load, \
             patch("src.rhdh_dynamic_plugin_factory.cli.logger") as mock_logger:
            mock_config = MagicMock()
            mock_config.use_local = False
            mock_load.return_value = mock_config

            try:
                _run_multi_workspace(mock_args, discover_workspaces(config_dir))
            except Exception:
                pass

            warning_calls = [
                c for c in mock_logger.warning.call_args_list
                if "will be ignored" in str(c)
            ]
            assert len(warning_calls) == 1
            msg = warning_calls[0][0][0]
            assert "stray.txt (file)" in msg
            assert "leftover/ (directory" in msg


class TestRegistryRefresh:
    """Tests for PluginFactoryConfig.refresh_registry_config()."""
    
    def _make_config(self, monkeypatch, tmp_path, push_images=False, **registry_overrides):
        """Helper to build a PluginFactoryConfig with registry fields."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        
        defaults = {
            "REGISTRY_URL": "quay.io",
            "REGISTRY_USERNAME": "user",
            "REGISTRY_PASSWORD": "pass",
            "REGISTRY_NAMESPACE": "ns",
            "REGISTRY_INSECURE": "false",
        }
        defaults.update(registry_overrides)
        for k, v in defaults.items():
            monkeypatch.setenv(k, v)
        
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path / "source"
        repo_path.mkdir(parents=True, exist_ok=True)
        (repo_path / "placeholder").write_text("")
        
        import argparse
        args = argparse.Namespace(
            config_dir=config_dir,
            repo_path=repo_path,
            workspace_path=".",
            use_local=False,
            push_images=push_images,
            log_level="INFO",
            source_repo=None,
            source_ref=None,
        )
        
        return PluginFactoryConfig.load_from_env(args, push_images=push_images)
    
    def test_updates_fields_from_environ(self, tmp_path, monkeypatch):
        """Test that refresh reads new values from os.environ."""
        config = self._make_config(monkeypatch, tmp_path)
        
        assert config.registry_url == "quay.io"
        assert config.registry_namespace == "ns"
        
        monkeypatch.setenv("REGISTRY_URL", "ghcr.io")
        monkeypatch.setenv("REGISTRY_NAMESPACE", "new-ns")
        
        config.refresh_registry_config()
        
        assert config.registry_url == "ghcr.io"
        assert config.registry_namespace == "new-ns"
    
    def test_relogin_triggered_when_creds_change(self, tmp_path, monkeypatch):
        """Test that buildah login is re-run when registry credentials change."""
        config = self._make_config(monkeypatch, tmp_path, push_images=True)
        
        monkeypatch.setenv("REGISTRY_URL", "ghcr.io")
        monkeypatch.setenv("REGISTRY_USERNAME", "new-user")
        monkeypatch.setenv("REGISTRY_PASSWORD", "new-pass")
        
        with patch.object(config, "_buildah_login") as mock_login:
            config.refresh_registry_config()
            mock_login.assert_called_once()
    
    def test_relogin_skipped_when_creds_unchanged(self, tmp_path, monkeypatch):
        """Test that buildah login is NOT re-run when credentials haven't changed."""
        config = self._make_config(monkeypatch, tmp_path, push_images=True)
        
        with patch.object(config, "_buildah_login") as mock_login:
            config.refresh_registry_config()
            mock_login.assert_not_called()
    
    def test_relogin_skipped_when_push_images_disabled(self, tmp_path, monkeypatch):
        """Test that buildah login is skipped when push_images is False."""
        config = self._make_config(monkeypatch, tmp_path, push_images=False)
        
        monkeypatch.setenv("REGISTRY_URL", "ghcr.io")
        
        with patch.object(config, "_buildah_login") as mock_login:
            config.refresh_registry_config()
            mock_login.assert_not_called()
    
    def test_validation_error_on_missing_url_after_refresh(self, tmp_path, monkeypatch):
        """Missing REGISTRY_URL after refresh raises ConfigurationError."""
        config = self._make_config(monkeypatch, tmp_path, push_images=True)
        
        monkeypatch.delenv("REGISTRY_URL")
        monkeypatch.setenv("REGISTRY_USERNAME", "changed")
        
        with pytest.raises(ConfigurationError, match="REGISTRY_URL"):
            config.refresh_registry_config()
    
    def test_namespace_change_without_cred_change_no_relogin(self, tmp_path, monkeypatch):
        """Changing only namespace updates the field but skips re-login."""
        config = self._make_config(monkeypatch, tmp_path, push_images=True)
        
        monkeypatch.setenv("REGISTRY_NAMESPACE", "different-ns")
        
        with patch.object(config, "_buildah_login") as mock_login:
            config.refresh_registry_config()
            assert config.registry_namespace == "different-ns"
            mock_login.assert_not_called()

    def test_refresh_reads_auth_file_from_environ(self, tmp_path, monkeypatch):
        """REGISTRY_AUTH_FILE in env is picked up by refresh."""
        config = self._make_config(monkeypatch, tmp_path)
        assert config.registry_auth_file is None

        monkeypatch.setenv("REGISTRY_AUTH_FILE", "/auth.json")
        config.refresh_registry_config()
        assert config.registry_auth_file == "/auth.json"

    def test_refresh_auth_file_change_triggers_revalidation(self, tmp_path, monkeypatch):
        """Auth file value changing between refreshes triggers re-validation + login."""
        config = self._make_config(monkeypatch, tmp_path, push_images=True)

        monkeypatch.setenv("REGISTRY_AUTH_FILE", "/new-auth.json")

        with patch.object(config, "_buildah_login") as mock_login:
            config.refresh_registry_config()
            mock_login.assert_called_once()

    def test_refresh_with_auth_file_no_username_password(self, tmp_path, monkeypatch):
        """Workspace has auth file + URL + namespace but no credentials -- succeeds."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        monkeypatch.setenv("REGISTRY_URL", "quay.io")
        monkeypatch.setenv("REGISTRY_NAMESPACE", "ns")
        monkeypatch.setenv("REGISTRY_INSECURE", "false")
        monkeypatch.delenv("REGISTRY_USERNAME", raising=False)
        monkeypatch.delenv("REGISTRY_PASSWORD", raising=False)

        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path / "source"
        repo_path.mkdir(parents=True, exist_ok=True)
        (repo_path / "placeholder").write_text("")

        import argparse
        args = argparse.Namespace(
            config_dir=config_dir, repo_path=repo_path, workspace_path=".",
            use_local=False, push_images=True, log_level="INFO",
            source_repo=None, source_ref=None,
        )
        config = PluginFactoryConfig.load_from_env(args, push_images=True)

        monkeypatch.setenv("REGISTRY_AUTH_FILE", "/auth.json")
        config.refresh_registry_config()
        assert config.registry_auth_file == "/auth.json"


class TestMultiWorkspaceDeferredCredentials:
    """Integration-style tests for multi-workspace deferred credential flow."""

    def _make_multi_ws_config(self, monkeypatch, tmp_path, env_vars=None):
        """Build a config in multi-workspace mode with optional env overrides."""
        monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
        if env_vars:
            for k, v in env_vars.items():
                monkeypatch.setenv(k, v)

        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        repo_path = tmp_path / "source"
        repo_path.mkdir(parents=True, exist_ok=True)
        (repo_path / "placeholder").write_text("")

        import argparse
        args = argparse.Namespace(
            config_dir=config_dir, repo_path=repo_path, workspace_path=".",
            use_local=False, push_images=True, log_level="INFO",
            source_repo=None, source_ref=None,
        )
        return PluginFactoryConfig.load_from_env(
            args, push_images=True, multi_workspace=True,
        )

    def test_root_env_no_credentials_workspace_env_has_credentials(self, tmp_path, monkeypatch):
        """Root has URL/NS only; workspace provides username/password."""
        config = self._make_multi_ws_config(monkeypatch, tmp_path, env_vars={
            "REGISTRY_URL": "quay.io",
            "REGISTRY_NAMESPACE": "ns",
        })
        assert config.registry_username is None

        monkeypatch.setenv("REGISTRY_USERNAME", "ws-user")
        monkeypatch.setenv("REGISTRY_PASSWORD", "ws-pass")

        with patch.object(config, "_buildah_login") as mock_login:
            config.refresh_registry_config()
            mock_login.assert_called_once()
        assert config.registry_username == "ws-user"

    def test_root_env_empty_workspaces_provide_all_registry_config(self, tmp_path, monkeypatch):
        """Root has NO registry vars; workspace provides everything."""
        config = self._make_multi_ws_config(monkeypatch, tmp_path)
        assert config.registry_url is None

        monkeypatch.setenv("REGISTRY_URL", "ghcr.io")
        monkeypatch.setenv("REGISTRY_NAMESPACE", "org")
        monkeypatch.setenv("REGISTRY_USERNAME", "user")
        monkeypatch.setenv("REGISTRY_PASSWORD", "pass")

        with patch.object(config, "_buildah_login") as mock_login:
            config.refresh_registry_config()
            mock_login.assert_called_once()
        assert config.registry_url == "ghcr.io"

    def test_root_env_no_creds_workspace_also_missing_url_fails(self, tmp_path, monkeypatch):
        """Root and workspace both missing REGISTRY_URL -- raises ConfigurationError."""
        config = self._make_multi_ws_config(monkeypatch, tmp_path)

        monkeypatch.setenv("REGISTRY_USERNAME", "user")
        monkeypatch.setenv("REGISTRY_PASSWORD", "pass")

        with pytest.raises(ConfigurationError, match="REGISTRY_URL"):
            config.refresh_registry_config()

    def test_root_env_no_creds_workspace_has_url_but_no_auth_warns(self, tmp_path, monkeypatch):
        """Workspace has URL + NS but no credentials/auth file -- warns but succeeds."""
        config = self._make_multi_ws_config(monkeypatch, tmp_path)

        monkeypatch.setenv("REGISTRY_URL", "quay.io")
        monkeypatch.setenv("REGISTRY_NAMESPACE", "ns")

        with patch.object(config, "logger") as mock_logger:
            with patch.object(config, "_buildah_login"):
                config.refresh_registry_config()
            warning_calls = [
                c for c in mock_logger.warning.call_args_list
                if "No explicit registry authentication" in str(c)
            ]
            assert len(warning_calls) == 1

    def test_root_env_no_credentials_workspace_env_has_auth_file(self, tmp_path, monkeypatch):
        """Root has nothing; workspace provides auth file + URL + namespace."""
        config = self._make_multi_ws_config(monkeypatch, tmp_path)

        monkeypatch.setenv("REGISTRY_URL", "quay.io")
        monkeypatch.setenv("REGISTRY_NAMESPACE", "ns")
        monkeypatch.setenv("REGISTRY_AUTH_FILE", "/auth.json")

        config.refresh_registry_config()
        assert config.registry_auth_file == "/auth.json"

    def test_mixed_workspaces_different_auth_strategies(self, tmp_path, monkeypatch):
        """Three workspaces with different auth: user/pass, auth file, pre-auth."""
        config = self._make_multi_ws_config(monkeypatch, tmp_path)

        # WS-A: username/password
        monkeypatch.setenv("REGISTRY_URL", "quay.io")
        monkeypatch.setenv("REGISTRY_NAMESPACE", "ns")
        monkeypatch.setenv("REGISTRY_USERNAME", "user")
        monkeypatch.setenv("REGISTRY_PASSWORD", "pass")
        monkeypatch.delenv("REGISTRY_AUTH_FILE", raising=False)
        with patch.object(config, "_buildah_login") as mock_login:
            config.refresh_registry_config()
            mock_login.assert_called_once()

        # WS-B: auth file (clear creds, set auth file)
        monkeypatch.delenv("REGISTRY_USERNAME", raising=False)
        monkeypatch.delenv("REGISTRY_PASSWORD", raising=False)
        monkeypatch.setenv("REGISTRY_AUTH_FILE", "/auth.json")
        config.refresh_registry_config()
        assert config.registry_auth_file == "/auth.json"

        # WS-C: pre-authenticated (no creds, no auth file)
        monkeypatch.delenv("REGISTRY_AUTH_FILE", raising=False)
        with patch.object(config, "logger") as mock_logger:
            with patch.object(config, "_buildah_login"):
                config.refresh_registry_config()
            warning_calls = [
                c for c in mock_logger.warning.call_args_list
                if "No explicit registry authentication" in str(c)
            ]
            assert len(warning_calls) == 1
