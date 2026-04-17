"""
Unit tests for PluginFactoryConfig.discover_plugins_list and
PluginFactoryConfig.populate_plugins_build_args methods.

Tests the two-phase plugins-list.yaml generation:
  Phase 1 (discover_plugins_list): scan workspace, write paths only
  Phase 2 (populate_plugins_build_args): compute build args for existing file
"""

import json
from pathlib import Path

import pytest
import yaml
from src.rhdh_dynamic_plugin_factory import constants
from src.rhdh_dynamic_plugin_factory.constants import PLUGIN_LIST_FILE
from src.rhdh_dynamic_plugin_factory.exceptions import PluginFactoryError


def _make_plugin_dir(base, rel_path, name, role, dependencies=None):
    """Helper to create a plugin directory with a package.json."""
    plugin_dir = base / rel_path
    plugin_dir.mkdir(parents=True, exist_ok=True)
    pkg = {"name": name, "version": "1.0.0", "backstage": {"role": role}}
    if dependencies:
        pkg["dependencies"] = dependencies
    (plugin_dir / "package.json").write_text(json.dumps(pkg))
    return plugin_dir


def _make_node_module(base, dep_name, dependencies=None):
    """Helper to create a workspace-root node_modules/<dep>/package.json entry."""
    nm_dir = base / "node_modules" / dep_name
    nm_dir.mkdir(parents=True, exist_ok=True)
    pkg = {"name": dep_name, "version": "1.0.0"}
    if dependencies:
        pkg["dependencies"] = dependencies
    (nm_dir / "package.json").write_text(json.dumps(pkg))


class TestDiscoverPluginsList:
    """Tests for PluginFactoryConfig.discover_plugins_list (Phase 1)."""

    def test_generates_file_when_missing(self, make_config, setup_test_env):
        """When plugins-list.yaml is missing, discover plugins and write the file."""
        config = make_config()
        config_dir = setup_test_env["config_dir"]

        plugins_file = Path(config_dir) / PLUGIN_LIST_FILE
        plugins_file.unlink()
        assert not plugins_file.exists()

        workspace = Path(config.repo_path)
        _make_plugin_dir(workspace, "plugins/todo", "@test/plugin-todo", "frontend-plugin")
        _make_plugin_dir(
            workspace,
            "plugins/todo-backend",
            "@test/plugin-todo-backend",
            "backend-plugin",
        )

        result = config.discover_plugins_list()

        assert result is True
        assert plugins_file.exists()

        data = yaml.safe_load(plugins_file.read_text())
        assert "plugins/todo" in data
        assert "plugins/todo-backend" in data
        for val in data.values():
            assert val is None

    def test_skips_when_file_exists(self, make_config, setup_test_env):
        """When plugins-list.yaml already exists, do nothing and return False."""
        config = make_config()
        config_dir = setup_test_env["config_dir"]

        plugins_file = Path(config_dir) / PLUGIN_LIST_FILE
        assert plugins_file.exists()

        original_content = plugins_file.read_text()
        result = config.discover_plugins_list()

        assert result is False
        assert plugins_file.read_text() == original_content

    def test_raises_when_repo_path_missing(self, make_config, setup_test_env):
        """Raises PluginFactoryError when repo_path does not exist."""
        config = make_config(repo_path="/nonexistent/path")
        config_dir = setup_test_env["config_dir"]

        plugins_file = Path(config_dir) / PLUGIN_LIST_FILE
        plugins_file.unlink()

        with pytest.raises(PluginFactoryError, match="Source code repository does not exist"):
            config.discover_plugins_list()

    def test_raises_when_workspace_missing(self, make_config, setup_test_env):
        """Raises PluginFactoryError when workspace does not exist under repo_path."""
        config = make_config(workspace_path="nonexistent/workspace")
        config_dir = setup_test_env["config_dir"]

        plugins_file = Path(config_dir) / PLUGIN_LIST_FILE
        plugins_file.unlink()

        with pytest.raises(PluginFactoryError, match="Plugin workspace does not exist"):
            config.discover_plugins_list()

    def test_empty_workspace_still_writes_file(self, make_config, setup_test_env):
        """An empty workspace writes a plugins-list.yaml with no entries."""
        config = make_config()
        config_dir = setup_test_env["config_dir"]

        plugins_file = Path(config_dir) / PLUGIN_LIST_FILE
        plugins_file.unlink()

        result = config.discover_plugins_list()

        assert result is True
        assert plugins_file.exists()
        assert plugins_file.read_text() == ""

    def test_build_args_are_always_empty(self, make_config, setup_test_env):
        """Phase 1 never produces build args, even for backend plugins."""
        config = make_config()
        config_dir = setup_test_env["config_dir"]

        plugins_file = Path(config_dir) / PLUGIN_LIST_FILE
        plugins_file.unlink()

        workspace = Path(config.repo_path)
        _make_plugin_dir(
            workspace,
            "plugins/backend",
            "@test/my-backend",
            "backend-plugin",
            dependencies={"@backstage/new-experimental": "^0.1.0"},
        )

        config.discover_plugins_list()

        content = plugins_file.read_text()
        assert "--embed-package" not in content
        assert "--shared-package" not in content

    def test_uses_explicit_config_dir_param(self, make_config, tmp_path):
        """When config_dir is passed explicitly, uses that instead of self.config_dir."""
        config = make_config()

        alt_config_dir = tmp_path / "alt-config"
        alt_config_dir.mkdir()

        workspace = Path(config.repo_path)
        _make_plugin_dir(workspace, "plugins/todo", "@test/plugin-todo", "frontend-plugin")

        result = config.discover_plugins_list(config_dir=str(alt_config_dir))

        assert result is True
        assert (alt_config_dir / PLUGIN_LIST_FILE).exists()


class TestPopulatePluginsBuildArgs:
    """Tests for PluginFactoryConfig.populate_plugins_build_args (Phase 2)."""

    def test_computes_build_args_for_existing_file(self, make_config, setup_test_env, monkeypatch):
        """Loads plugins-list.yaml, computes build args, writes back."""
        lockfile = Path(setup_test_env["tmp_path"]) / "host-yarn.lock"
        lockfile.write_text('"@backstage/core@npm:^1.0.0":\n  version: 1.0.0\n')
        monkeypatch.setattr(constants, "HOST_LOCKFILE", lockfile)

        config = make_config()
        config_dir = setup_test_env["config_dir"]

        workspace = Path(config.repo_path)
        _make_plugin_dir(
            workspace,
            "plugins/backend",
            "@test/my-backend",
            "backend-plugin",
            dependencies={"@backstage/new-experimental": "^0.1.0"},
        )
        _make_plugin_dir(
            workspace,
            "plugins/frontend",
            "@test/my-frontend",
            "frontend-plugin",
        )

        plugins_file = Path(config_dir) / PLUGIN_LIST_FILE
        plugins_file.write_text("plugins/backend:\nplugins/frontend:\n")

        config.populate_plugins_build_args()

        updated = yaml.safe_load(plugins_file.read_text())
        assert "--embed-package @backstage/new-experimental" in str(updated.get("plugins/backend", ""))
        assert updated.get("plugins/frontend") is None

    def test_raises_when_file_missing(self, make_config, setup_test_env):
        """Raises PluginFactoryError when plugins-list.yaml does not exist."""
        config = make_config()
        config_dir = setup_test_env["config_dir"]

        plugins_file = Path(config_dir) / PLUGIN_LIST_FILE
        plugins_file.unlink()

        with pytest.raises(PluginFactoryError, match="not found"):
            config.populate_plugins_build_args()

    def test_raises_when_workspace_missing(self, make_config, setup_test_env):
        """Raises PluginFactoryError when workspace does not exist."""
        config = make_config(workspace_path="nonexistent/workspace")

        with pytest.raises(PluginFactoryError, match="Plugin workspace does not exist"):
            config.populate_plugins_build_args()

    def test_uses_explicit_params(self, make_config, tmp_path, monkeypatch):
        """When params are passed explicitly, uses those instead of self defaults."""
        lockfile = tmp_path / "host-yarn.lock"
        lockfile.write_text("")
        monkeypatch.setattr(constants, "HOST_LOCKFILE", lockfile)

        config = make_config()

        alt_config_dir = tmp_path / "alt-config"
        alt_config_dir.mkdir()

        workspace = Path(config.repo_path)
        _make_plugin_dir(workspace, "plugins/todo", "@test/plugin-todo", "frontend-plugin")

        plugins_file = alt_config_dir / PLUGIN_LIST_FILE
        plugins_file.write_text("plugins/todo:\n")

        config.populate_plugins_build_args(config_dir=str(alt_config_dir))

        updated = yaml.safe_load(plugins_file.read_text())
        assert "plugins/todo" in updated


class TestTwoPhaseFlow:
    """Integration tests verifying the Phase 1 -> Phase 2 flow works end-to-end."""

    def test_discover_then_populate(self, make_config, setup_test_env, monkeypatch):
        """Phase 1 discovers plugins, Phase 2 computes build args."""
        lockfile = Path(setup_test_env["tmp_path"]) / "host-yarn.lock"
        lockfile.write_text('"@backstage/core@npm:^1.0.0":\n  version: 1.0.0\n')
        monkeypatch.setattr(constants, "HOST_LOCKFILE", lockfile)

        config = make_config()
        config_dir = setup_test_env["config_dir"]

        plugins_file = Path(config_dir) / PLUGIN_LIST_FILE
        plugins_file.unlink()

        workspace = Path(config.repo_path)
        _make_plugin_dir(
            workspace,
            "plugins/todo",
            "@test/plugin-todo",
            "frontend-plugin",
        )
        _make_plugin_dir(
            workspace,
            "plugins/todo-backend",
            "@test/plugin-todo-backend",
            "backend-plugin",
            dependencies={"@backstage/new-experimental": "^0.1.0"},
        )

        was_generated = config.discover_plugins_list()
        assert was_generated is True

        after_phase1 = plugins_file.read_text()
        assert "--embed-package" not in after_phase1

        config.populate_plugins_build_args()

        updated = yaml.safe_load(plugins_file.read_text())
        assert updated.get("plugins/todo") is None
        assert "--embed-package @backstage/new-experimental" in str(updated.get("plugins/todo-backend", ""))

    def test_user_provided_file_not_overwritten_by_phase1(self, make_config, setup_test_env):
        """Phase 1 does not touch a user-provided plugins-list.yaml."""
        config = make_config()
        config_dir = setup_test_env["config_dir"]

        plugins_file = Path(config_dir) / PLUGIN_LIST_FILE
        user_content = "plugins/custom-plugin: --user-args\n"
        plugins_file.write_text(user_content)

        was_generated = config.discover_plugins_list()
        assert was_generated is False
        assert plugins_file.read_text() == user_content
