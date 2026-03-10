"""
Unit tests for PluginListConfig class.

Tests the plugin list configuration loading and management.
"""

import json
import yaml
import pytest

from src.rhdh_dynamic_plugin_factory.plugin_list_config import PluginListConfig
from src.rhdh_dynamic_plugin_factory import constants


class TestPluginListConfigFromFile:
    """Tests for PluginListConfig.from_file method."""
    
    def test_from_file_valid_yaml(self, tmp_path):
        """Test loading valid YAML with plugins."""
        yaml_content = """plugins/ecs/frontend:
plugins/ecs/backend: --embed-package @aws/aws-core-plugin-for-backstage-common --embed-package @aws/aws-core-plugin-for-backstage-node
plugins/codebuild/backend:
"""
        
        plugins_file = tmp_path / "plugins-list.yaml"
        plugins_file.write_text(yaml_content)
        
        config = PluginListConfig.from_file(plugins_file)
        plugins = config.get_plugins()
        
        assert len(plugins) == 3
        assert "plugins/ecs/frontend" in plugins
        assert plugins["plugins/ecs/frontend"] == ""
        assert "plugins/ecs/backend" in plugins
        assert plugins["plugins/ecs/backend"] == "--embed-package @aws/aws-core-plugin-for-backstage-common --embed-package @aws/aws-core-plugin-for-backstage-node"
        assert "plugins/codebuild/backend" in plugins
        assert plugins["plugins/codebuild/backend"] == ""
    
    def test_from_file_empty_yaml(self, tmp_path):
        """Test loading empty YAML file returns empty plugins dict."""
        plugins_file = tmp_path / "plugins-list.yaml"
        plugins_file.write_text("")
        
        config = PluginListConfig.from_file(plugins_file)
        plugins = config.get_plugins()
        
        assert plugins == {}
    
    def test_from_file_yaml_with_null_values(self, tmp_path):
        """Test that null values are converted to empty strings."""
        yaml_content = """plugins/test1:
plugins/test2:
"""
        
        plugins_file = tmp_path / "plugins-list.yaml"
        plugins_file.write_text(yaml_content)
        
        config = PluginListConfig.from_file(plugins_file)
        plugins = config.get_plugins()
        
        assert plugins["plugins/test1"] == ""
        assert plugins["plugins/test2"] == ""
    
    def test_from_file_invalid_yaml(self, tmp_path):
        """Test that invalid YAML raises appropriate error."""
        yaml_content = """
        invalid: yaml: content
        [ unmatched
        """
        
        plugins_file = tmp_path / "plugins-list.yaml"
        plugins_file.write_text(yaml_content)
        
        with pytest.raises(yaml.YAMLError):
            PluginListConfig.from_file(plugins_file)
    
    def test_from_file_nonexistent_file(self, tmp_path):
        """Test that nonexistent file raises FileNotFoundError."""
        plugins_file = tmp_path / "nonexistent.yaml"
        
        with pytest.raises(FileNotFoundError):
            PluginListConfig.from_file(plugins_file)


class TestPluginListConfigGetPlugins:
    """Tests for PluginListConfig.get_plugins method."""
    
    def test_get_plugins_returns_copy(self):
        """Test that get_plugins returns a copy of the plugins dict."""
        plugins_dict = {
            "plugins/test1": "--arg1",
            "plugins/test2": ""
        }
        
        config = PluginListConfig(plugins_dict)
        retrieved_plugins = config.get_plugins()
        
        # Modify the retrieved dict
        retrieved_plugins["plugins/test3"] = "--arg3"
        
        # Original should be unchanged
        assert "plugins/test3" not in config.plugins
        assert len(config.plugins) == 2


class TestPluginListConfigAddPlugin:
    """Tests for PluginListConfig.add_plugin method."""
    
    def test_add_plugin_new(self):
        """Test adding a new plugin."""
        config = PluginListConfig({})
        
        config.add_plugin("plugins/test", "--arg1 --arg2")
        
        assert "plugins/test" in config.plugins
        assert config.plugins["plugins/test"] == "--arg1 --arg2"
    
    def test_add_plugin_with_empty_args(self):
        """Test adding a plugin with empty build args."""
        config = PluginListConfig({})
        
        config.add_plugin("plugins/test")
        
        assert "plugins/test" in config.plugins
        assert config.plugins["plugins/test"] == ""
    
    def test_add_plugin_overwrites_existing(self):
        """Test that adding an existing plugin overwrites it."""
        config = PluginListConfig({"plugins/test": "--old-arg"})
        
        config.add_plugin("plugins/test", "--new-arg")
        
        assert config.plugins["plugins/test"] == "--new-arg"


class TestPluginListConfigRemovePlugin:
    """Tests for PluginListConfig.remove_plugin method."""
    
    def test_remove_plugin_existing(self):
        """Test removing an existing plugin."""
        config = PluginListConfig({
            "plugins/test1": "--arg1",
            "plugins/test2": "--arg2"
        })
        
        config.remove_plugin("plugins/test1")
        
        assert "plugins/test1" not in config.plugins
        assert "plugins/test2" in config.plugins
    
    def test_remove_plugin_nonexistent(self):
        """Test that removing nonexistent plugin doesn't raise error."""
        config = PluginListConfig({"plugins/test1": "--arg1"})
        
        # Should not raise
        config.remove_plugin("plugins/nonexistent")
        
        # Original plugin should still be there
        assert "plugins/test1" in config.plugins


class TestPluginListConfigToFile:
    """Tests for PluginListConfig.to_file method."""

    def test_to_file_with_args(self, tmp_path):
        """Test writing plugins with build args."""
        config = PluginListConfig({
            "plugins/ecs/frontend": "",
            "plugins/ecs/backend": "--embed-package @aws/aws-core-plugin-for-backstage-common",
        })
        out = tmp_path / "plugins-list.yaml"
        config.to_file(out)

        lines = out.read_text().splitlines()
        assert lines[0] == "plugins/ecs/frontend:"
        assert lines[1] == "plugins/ecs/backend: --embed-package @aws/aws-core-plugin-for-backstage-common"

    def test_to_file_empty_plugins(self, tmp_path):
        """Test writing empty plugins dict produces empty file."""
        config = PluginListConfig({})
        out = tmp_path / "plugins-list.yaml"
        config.to_file(out)

        assert out.read_text() == ""

    def test_to_file_roundtrip(self, tmp_path):
        """Test that to_file output can be read back by from_file."""
        original = PluginListConfig({
            "plugins/todo": "",
            "plugins/todo-backend": "",
            "plugins/ecs/backend": "--embed-package @aws/common --embed-package @aws/node",
        })
        out = tmp_path / "plugins-list.yaml"
        original.to_file(out)

        loaded = PluginListConfig.from_file(out)
        assert loaded.get_plugins() == original.get_plugins()

    def test_to_file_null_values_format(self, tmp_path):
        """Test that empty args produce 'key:' (YAML null) not 'key: \"\"'."""
        config = PluginListConfig({"plugins/test": ""})
        out = tmp_path / "plugins-list.yaml"
        config.to_file(out)

        content = out.read_text()
        assert "plugins/test:" in content
        assert "''" not in content
        assert '""' not in content


def _make_plugin_dir(base, rel_path, name, role, dependencies=None):
    """Helper to create a plugin directory with a package.json."""
    plugin_dir = base / rel_path
    plugin_dir.mkdir(parents=True, exist_ok=True)
    pkg = {"name": name, "version": "1.0.0", "backstage": {"role": role}}
    if dependencies:
        pkg["dependencies"] = dependencies
    (plugin_dir / "package.json").write_text(json.dumps(pkg))
    return plugin_dir


def _make_node_module(base, dep_name, dependencies=None,
                      optional_dependencies=None):
    """Helper to create a workspace-root node_modules/<dep>/package.json entry."""
    nm_dir = base / "node_modules" / dep_name
    nm_dir.mkdir(parents=True, exist_ok=True)
    pkg = {"name": dep_name, "version": "1.0.0"}
    if dependencies:
        pkg["dependencies"] = dependencies
    if optional_dependencies:
        pkg["optionalDependencies"] = optional_dependencies
    (nm_dir / "package.json").write_text(json.dumps(pkg))
    return nm_dir


class TestPluginListConfigCreateDefault:
    """Tests for PluginListConfig.create_default method."""

    def test_discovers_backend_plugin(self, tmp_path):
        """Test discovering a backend plugin."""
        _make_plugin_dir(tmp_path, "plugins/todo-backend", "@backstage/plugin-todo-backend", "backend-plugin")

        config = PluginListConfig.create_default(tmp_path)
        plugins = config.get_plugins()

        assert "plugins/todo-backend" in plugins
        assert plugins["plugins/todo-backend"] == ""

    def test_discovers_frontend_plugin(self, tmp_path):
        """Test discovering a frontend plugin."""
        _make_plugin_dir(tmp_path, "plugins/todo", "@backstage/plugin-todo", "frontend-plugin")

        config = PluginListConfig.create_default(tmp_path)

        assert "plugins/todo" in config.get_plugins()

    def test_discovers_plugin_modules(self, tmp_path):
        """Test discovering frontend and backend plugin modules."""
        _make_plugin_dir(tmp_path, "plugins/auth-backend-module-github", "@backstage/plugin-auth-backend-module-github", "backend-plugin-module")
        _make_plugin_dir(tmp_path, "plugins/catalog-react-module", "@backstage/plugin-catalog-react-module", "frontend-plugin-module")

        config = PluginListConfig.create_default(tmp_path)
        plugins = config.get_plugins()

        assert "plugins/auth-backend-module-github" in plugins
        assert "plugins/catalog-react-module" in plugins

    def test_ignores_non_plugin_roles(self, tmp_path):
        """Test that packages with roles like 'node-library' or 'common-library' are skipped."""
        _make_plugin_dir(tmp_path, "packages/backend-defaults", "@backstage/backend-defaults", "node-library")
        _make_plugin_dir(tmp_path, "packages/catalog-common", "@backstage/catalog-common", "common-library")

        config = PluginListConfig.create_default(tmp_path)

        assert config.get_plugins() == {}

    def test_ignores_package_without_backstage_field(self, tmp_path):
        """Test that package.json without backstage field is skipped."""
        pkg_dir = tmp_path / "packages" / "some-lib"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text(json.dumps({"name": "some-lib", "version": "1.0.0"}))

        config = PluginListConfig.create_default(tmp_path)

        assert config.get_plugins() == {}

    def test_skips_node_modules(self, tmp_path):
        """Test that plugins inside node_modules are not discovered."""
        nm = tmp_path / "node_modules" / "@backstage" / "plugin-todo"
        nm.mkdir(parents=True)
        (nm / "package.json").write_text(json.dumps({
            "name": "@backstage/plugin-todo",
            "backstage": {"role": "frontend-plugin"},
        }))

        config = PluginListConfig.create_default(tmp_path)

        assert config.get_plugins() == {}

    def test_skips_hidden_directories(self, tmp_path):
        """Test that plugins inside hidden directories are not discovered."""
        hidden = tmp_path / ".hidden" / "plugin-todo"
        hidden.mkdir(parents=True)
        (hidden / "package.json").write_text(json.dumps({
            "name": "@test/plugin-todo",
            "backstage": {"role": "frontend-plugin"},
        }))

        config = PluginListConfig.create_default(tmp_path)

        assert config.get_plugins() == {}

    def test_skips_dist_directories(self, tmp_path):
        """Test that dist and dist-dynamic directories are skipped."""
        for d in ["dist", "dist-dynamic"]:
            dist = tmp_path / d / "plugin-todo"
            dist.mkdir(parents=True)
            (dist / "package.json").write_text(json.dumps({
                "name": "@test/plugin-todo",
                "backstage": {"role": "frontend-plugin"},
            }))

        config = PluginListConfig.create_default(tmp_path)

        assert config.get_plugins() == {}

    def test_discovers_nested_plugins(self, tmp_path):
        """Test discovering plugins in nested directory structures like plugins/ecs/backend."""
        _make_plugin_dir(tmp_path, "plugins/ecs/frontend", "@aws/ecs-frontend", "frontend-plugin")
        _make_plugin_dir(tmp_path, "plugins/ecs/backend", "@aws/ecs-backend", "backend-plugin")

        config = PluginListConfig.create_default(tmp_path)
        plugins = config.get_plugins()

        assert len(plugins) == 2
        assert "plugins/ecs/frontend" in plugins
        assert "plugins/ecs/backend" in plugins

    def test_results_sorted_alphabetically(self, tmp_path):
        """Test that discovered plugins are sorted by path."""
        _make_plugin_dir(tmp_path, "plugins/z-plugin", "@test/z-plugin", "frontend-plugin")
        _make_plugin_dir(tmp_path, "plugins/a-plugin", "@test/a-plugin", "backend-plugin")
        _make_plugin_dir(tmp_path, "plugins/m-plugin", "@test/m-plugin", "frontend-plugin")

        config = PluginListConfig.create_default(tmp_path)
        paths = list(config.get_plugins().keys())

        assert paths == ["plugins/a-plugin", "plugins/m-plugin", "plugins/z-plugin"]

    def test_empty_workspace(self, tmp_path):
        """Test scanning an empty workspace returns no plugins."""
        config = PluginListConfig.create_default(tmp_path)

        assert config.get_plugins() == {}

    def test_malformed_package_json_skipped(self, tmp_path):
        """Test that a malformed package.json does not crash discovery."""
        bad_dir = tmp_path / "plugins" / "broken"
        bad_dir.mkdir(parents=True)
        (bad_dir / "package.json").write_text("{ not valid json")

        _make_plugin_dir(tmp_path, "plugins/good", "@test/good", "backend-plugin")

        config = PluginListConfig.create_default(tmp_path)
        plugins = config.get_plugins()

        assert len(plugins) == 1
        assert "plugins/good" in plugins

    def test_todo_workspace_structure(self, tmp_path):
        """Test a workspace matching the community-plugins todo example."""
        _make_plugin_dir(tmp_path, "plugins/todo", "@backstage-community/plugin-todo", "frontend-plugin")
        _make_plugin_dir(tmp_path, "plugins/todo-backend", "@backstage-community/plugin-todo-backend", "backend-plugin")

        config = PluginListConfig.create_default(tmp_path)
        plugins = config.get_plugins()

        assert plugins == {"plugins/todo": "", "plugins/todo-backend": ""}

    def test_aws_ecs_workspace_structure(self, tmp_path):
        """Test a workspace matching the AWS ECS plugins example (nested dirs)."""
        _make_plugin_dir(tmp_path, "plugins/ecs/frontend", "@aws/amazon-ecs-plugin-for-backstage", "frontend-plugin")
        _make_plugin_dir(tmp_path, "plugins/ecs/backend", "@aws/amazon-ecs-plugin-for-backstage-backend", "backend-plugin")
        _make_plugin_dir(tmp_path, "plugins/ecs/common", "@aws/aws-core-plugin-for-backstage-common", "common-library")

        config = PluginListConfig.create_default(tmp_path)
        plugins = config.get_plugins()

        assert len(plugins) == 2
        assert "plugins/ecs/frontend" in plugins
        assert "plugins/ecs/backend" in plugins


class TestParseHostBackstagePackages:
    """Tests for PluginListConfig._parse_host_backstage_packages."""

    def test_single_entry(self, tmp_path):
        lockfile = tmp_path / "yarn.lock"
        lockfile.write_text(
            '"@backstage/catalog-model@npm:^1.7.2":\n  version: 1.7.2\n'
        )
        result = PluginListConfig._parse_host_backstage_packages(lockfile)
        assert result == {"@backstage/catalog-model"}

    def test_multi_version_entry(self, tmp_path):
        lockfile = tmp_path / "yarn.lock"
        lockfile.write_text(
            '"@backstage/catalog-model@npm:^1.7.2, @backstage/catalog-model@npm:^1.7.3":\n'
            "  version: 1.9.0\n"
        )
        result = PluginListConfig._parse_host_backstage_packages(lockfile)
        assert result == {"@backstage/catalog-model"}

    def test_multiple_packages(self, tmp_path):
        lockfile = tmp_path / "yarn.lock"
        lockfile.write_text(
            '"@backstage/catalog-model@npm:^1.7.2":\n  version: 1.7.2\n\n'
            '"@backstage/errors@npm:^1.2.7":\n  version: 1.2.7\n'
        )
        result = PluginListConfig._parse_host_backstage_packages(lockfile)
        assert result == {"@backstage/catalog-model", "@backstage/errors"}

    def test_non_backstage_entries_ignored(self, tmp_path):
        lockfile = tmp_path / "yarn.lock"
        lockfile.write_text(
            '"@aws/sdk@npm:^1.0.0":\n  version: 1.0.0\n\n'
            '"@backstage/errors@npm:^1.2.7":\n  version: 1.2.7\n'
        )
        result = PluginListConfig._parse_host_backstage_packages(lockfile)
        assert result == {"@backstage/errors"}

    def test_missing_file_returns_empty(self, tmp_path):
        lockfile = tmp_path / "nonexistent.lock"
        result = PluginListConfig._parse_host_backstage_packages(lockfile)
        assert result == set()

    def test_backstage_in_dependency_lines_ignored(self, tmp_path):
        """Only top-level key lines (starting with quotes) are parsed, not indented dep lines."""
        lockfile = tmp_path / "yarn.lock"
        lockfile.write_text(
            '"@some/package@npm:^1.0.0":\n'
            '  version: 1.0.0\n'
            '  dependencies:\n'
            '    "@backstage/types": "npm:^1.2.1"\n'
        )
        result = PluginListConfig._parse_host_backstage_packages(lockfile)
        assert result == set()


class TestGetSiblingNames:
    """Tests for PluginListConfig._get_sibling_names."""

    def test_backend_plugin(self):
        result = PluginListConfig._get_sibling_names(
            "@scope/my-plugin-backend", "backend-plugin"
        )
        assert result == {"@scope/my-plugin-common", "@scope/my-plugin-node"}

    def test_backend_plugin_module(self):
        result = PluginListConfig._get_sibling_names(
            "@scope/my-plugin-backend-module-github", "backend-plugin-module"
        )
        assert result == {"@scope/my-plugin-common", "@scope/my-plugin-node"}

    def test_frontend_plugin_returns_empty(self):
        result = PluginListConfig._get_sibling_names(
            "@scope/my-plugin", "frontend-plugin"
        )
        assert result == set()

    def test_frontend_plugin_module_returns_empty(self):
        result = PluginListConfig._get_sibling_names(
            "@scope/my-plugin-module", "frontend-plugin-module"
        )
        assert result == set()

    def test_name_without_matching_suffix(self):
        """If the name doesn't end with -backend, no siblings are derived."""
        result = PluginListConfig._get_sibling_names(
            "@scope/weird-name", "backend-plugin"
        )
        assert result == set()

    def test_scoped_package_preserves_scope(self):
        result = PluginListConfig._get_sibling_names(
            "@red-hat-developer-hub/backstage-plugin-bulk-import-backend",
            "backend-plugin",
        )
        assert result == {
            "@red-hat-developer-hub/backstage-plugin-bulk-import-common",
            "@red-hat-developer-hub/backstage-plugin-bulk-import-node",
        }


class TestResolveNodeModule:
    """Tests for PluginListConfig._resolve_node_module_package_json."""

    def test_finds_package_in_root_node_modules(self, tmp_path):
        _make_node_module(tmp_path, "@aws/common")
        result = PluginListConfig._resolve_node_module_package_json(tmp_path, "@aws/common")
        assert result is not None
        assert result.is_file()

    def test_not_found_returns_none(self, tmp_path):
        result = PluginListConfig._resolve_node_module_package_json(tmp_path, "@aws/missing")
        assert result is None

    def test_scoped_package(self, tmp_path):
        _make_node_module(tmp_path, "@aws/aws-core-plugin-for-backstage-common")
        result = PluginListConfig._resolve_node_module_package_json(
            tmp_path, "@aws/aws-core-plugin-for-backstage-common",
        )
        assert result is not None


class TestComputeBackendBuildArgs:
    """Tests for PluginListConfig._compute_backend_build_args."""

    def test_dep_with_backstage_sub_deps_in_host(self, tmp_path):
        """Third-party dep has @backstage/* sub-deps in host -> embed only, no unshare."""
        _make_plugin_dir(
            tmp_path, "plugins/backend", "@test/my-backend", "backend-plugin",
            dependencies={"@aws/common": "^1.0.0", "@backstage/core": "^1.0.0"},
        )
        _make_node_module(
            tmp_path, "@aws/common",
            dependencies={"@backstage/catalog-model": "^1.7.0"},
        )

        host = {"@backstage/catalog-model", "@backstage/core"}
        result = PluginListConfig._compute_backend_build_args(
            tmp_path, "plugins/backend",
            tmp_path / "plugins/backend/package.json", host,
        )
        assert "--embed-package @aws/common" in result
        assert "--shared-package" not in result

    def test_dep_with_backstage_sub_deps_not_in_host(self, tmp_path):
        """Third-party dep has @backstage/* sub-deps NOT in host -> embed + unshare."""
        _make_plugin_dir(
            tmp_path, "plugins/backend", "@test/my-backend", "backend-plugin",
            dependencies={"@custom/lib": "^1.0.0"},
        )
        _make_node_module(
            tmp_path, "@custom/lib",
            dependencies={"@backstage/new-pkg": "^1.0.0"},
        )

        result = PluginListConfig._compute_backend_build_args(
            tmp_path, "plugins/backend",
            tmp_path / "plugins/backend/package.json", {"@backstage/core"},
        )
        assert "--embed-package @custom/lib" in result
        assert "--shared-package !@backstage/new-pkg" in result

    def test_no_backstage_sub_deps(self, tmp_path):
        """Third-party dep with no @backstage/* sub-deps -> no args."""
        _make_plugin_dir(
            tmp_path, "plugins/backend", "@test/my-backend", "backend-plugin",
            dependencies={"lodash": "^4.0.0"},
        )
        _make_node_module(
            tmp_path, "lodash",
            dependencies={"underscore": "^1.0.0"},
        )

        result = PluginListConfig._compute_backend_build_args(
            tmp_path, "plugins/backend",
            tmp_path / "plugins/backend/package.json", set(),
        )
        assert result == ""

    def test_sibling_deps_skipped(self, tmp_path):
        """Sibling deps (-common, -node) are not embedded even if they have @backstage/* sub-deps."""
        _make_plugin_dir(
            tmp_path, "plugins/backend", "@test/my-plugin-backend", "backend-plugin",
            dependencies={
                "@test/my-plugin-common": "^1.0.0",
                "@test/my-plugin-node": "^1.0.0",
            },
        )
        _make_node_module(
            tmp_path, "@test/my-plugin-common",
            dependencies={"@backstage/catalog-model": "^1.0.0"},
        )

        result = PluginListConfig._compute_backend_build_args(
            tmp_path, "plugins/backend",
            tmp_path / "plugins/backend/package.json", set(),
        )
        assert result == ""

    def test_backstage_direct_dep_missing_from_host(self, tmp_path):
        """@backstage/* direct dep NOT in host -> embed + unshare."""
        _make_plugin_dir(
            tmp_path, "plugins/backend", "@test/my-backend", "backend-plugin",
            dependencies={"@backstage/new-experimental": "^0.1.0"},
        )

        result = PluginListConfig._compute_backend_build_args(
            tmp_path, "plugins/backend",
            tmp_path / "plugins/backend/package.json",
            {"@backstage/core", "@backstage/errors"},
        )
        assert "--embed-package @backstage/new-experimental" in result
        assert "--shared-package !@backstage/new-experimental" in result

    def test_backstage_direct_dep_present_in_host(self, tmp_path):
        """@backstage/* direct dep in host -> no action (it stays shared)."""
        _make_plugin_dir(
            tmp_path, "plugins/backend", "@test/my-backend", "backend-plugin",
            dependencies={"@backstage/catalog-model": "^1.7.0"},
        )

        result = PluginListConfig._compute_backend_build_args(
            tmp_path, "plugins/backend",
            tmp_path / "plugins/backend/package.json",
            {"@backstage/catalog-model"},
        )
        assert result == ""

    def test_mixed_scenario(self, tmp_path):
        """Multiple deps with different outcomes combined correctly."""
        _make_plugin_dir(
            tmp_path, "plugins/backend", "@test/my-plugin-backend", "backend-plugin",
            dependencies={
                "@backstage/catalog-model": "^1.7.0",
                "@backstage/new-pkg": "^0.1.0",
                "@test/my-plugin-common": "^1.0.0",
                "@custom/lib": "^1.0.0",
                "lodash": "^4.0.0",
            },
        )
        _make_node_module(
            tmp_path, "@custom/lib",
            dependencies={"@backstage/errors": "^1.2.0", "@backstage/missing": "^0.1.0"},
        )
        _make_node_module(tmp_path, "lodash")

        host = {"@backstage/catalog-model", "@backstage/errors"}
        result = PluginListConfig._compute_backend_build_args(
            tmp_path, "plugins/backend",
            tmp_path / "plugins/backend/package.json", host,
        )
        assert "--embed-package @backstage/new-pkg" in result
        assert "--embed-package @custom/lib" in result
        assert "--shared-package !@backstage/new-pkg" in result
        assert "--shared-package !@backstage/missing" in result
        assert "lodash" not in result
        assert "@test/my-plugin-common" not in result

    def test_unresolvable_dep_skipped(self, tmp_path):
        """Dep not found in node_modules is silently skipped."""
        _make_plugin_dir(
            tmp_path, "plugins/backend", "@test/my-backend", "backend-plugin",
            dependencies={"@missing/package": "^1.0.0"},
        )

        result = PluginListConfig._compute_backend_build_args(
            tmp_path, "plugins/backend",
            tmp_path / "plugins/backend/package.json", set(),
        )
        assert result == ""

    def test_malformed_dep_package_json_skipped(self, tmp_path):
        """Dep with invalid package.json in node_modules is skipped."""
        _make_plugin_dir(
            tmp_path, "plugins/backend", "@test/my-backend", "backend-plugin",
            dependencies={"bad-dep": "^1.0.0"},
        )
        nm_dir = tmp_path / "node_modules/bad-dep"
        nm_dir.mkdir(parents=True)
        (nm_dir / "package.json").write_text("{ broken json")

        result = PluginListConfig._compute_backend_build_args(
            tmp_path, "plugins/backend",
            tmp_path / "plugins/backend/package.json", set(),
        )
        assert result == ""


class TestCreateDefaultWithEmbedArgs:
    """End-to-end tests for create_default with Phase 2 embed/unshare detection."""

    def test_aws_ecs_like_workspace(self, tmp_path, monkeypatch):
        """Backend plugin with third-party dep that has @backstage/* sub-deps."""
        lockfile = tmp_path / "host-yarn.lock"
        lockfile.write_text(
            '"@backstage/catalog-model@npm:^1.7.2":\n  version: 1.9.0\n\n'
            '"@backstage/errors@npm:^1.2.7":\n  version: 1.2.7\n'
        )
        monkeypatch.setattr(constants, "HOST_LOCKFILE", lockfile)

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        _make_plugin_dir(
            workspace, "plugins/ecs/frontend",
            "@aws/amazon-ecs-plugin-for-backstage", "frontend-plugin",
        )
        _make_plugin_dir(
            workspace, "plugins/ecs/backend",
            "@aws/amazon-ecs-plugin-for-backstage-backend", "backend-plugin",
            dependencies={
                "@aws/aws-core-plugin-for-backstage-common": "^0.2.0",
                "@backstage/catalog-model": "^1.7.0",
            },
        )
        _make_node_module(
            workspace, "@aws/aws-core-plugin-for-backstage-common",
            dependencies={"@backstage/catalog-model": "^1.7.0"},
        )

        config = PluginListConfig.create_default(workspace)
        plugins = config.get_plugins()

        assert plugins["plugins/ecs/frontend"] == ""
        assert "--embed-package @aws/aws-core-plugin-for-backstage-common" in plugins["plugins/ecs/backend"]
        assert "--shared-package" not in plugins["plugins/ecs/backend"]

    def test_frontend_plugins_get_no_args(self, tmp_path, monkeypatch):
        lockfile = tmp_path / "host-yarn.lock"
        lockfile.write_text("")
        monkeypatch.setattr(constants, "HOST_LOCKFILE", lockfile)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _make_plugin_dir(
            workspace, "plugins/todo",
            "@backstage-community/plugin-todo", "frontend-plugin",
        )

        config = PluginListConfig.create_default(workspace)
        assert config.get_plugins()["plugins/todo"] == ""

    def test_backend_no_deps_no_args(self, tmp_path, monkeypatch):
        lockfile = tmp_path / "host-yarn.lock"
        lockfile.write_text('"@backstage/core@npm:^1.0.0":\n  version: 1.0.0\n')
        monkeypatch.setattr(constants, "HOST_LOCKFILE", lockfile)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _make_plugin_dir(
            workspace, "plugins/todo-backend",
            "@backstage-community/plugin-todo-backend", "backend-plugin",
        )

        config = PluginListConfig.create_default(workspace)
        assert config.get_plugins()["plugins/todo-backend"] == ""

    def test_backstage_dep_not_in_host_unshared_and_embedded(self, tmp_path, monkeypatch):
        """@backstage/* direct dep missing from host gets both embed and unshare."""
        lockfile = tmp_path / "host-yarn.lock"
        lockfile.write_text('"@backstage/core@npm:^1.0.0":\n  version: 1.0.0\n')
        monkeypatch.setattr(constants, "HOST_LOCKFILE", lockfile)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _make_plugin_dir(
            workspace, "plugins/my-backend",
            "@test/my-backend", "backend-plugin",
            dependencies={"@backstage/new-experimental": "^0.1.0"},
        )

        config = PluginListConfig.create_default(workspace)
        args = config.get_plugins()["plugins/my-backend"]
        assert "--embed-package @backstage/new-experimental" in args
        assert "--shared-package !@backstage/new-experimental" in args

    def test_missing_host_lockfile_still_works(self, tmp_path, monkeypatch):
        """When host lockfile is missing, all @backstage/* deps are treated as absent."""
        monkeypatch.setattr(
            constants, "HOST_LOCKFILE", tmp_path / "nonexistent.lock"
        )

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _make_plugin_dir(
            workspace, "plugins/backend",
            "@test/my-backend", "backend-plugin",
            dependencies={"@backstage/catalog-model": "^1.7.0"},
        )

        config = PluginListConfig.create_default(workspace)
        args = config.get_plugins()["plugins/backend"]
        assert "--embed-package @backstage/catalog-model" in args
        assert "--shared-package !@backstage/catalog-model" in args


class TestIsNativeModule:
    """Tests for PluginListConfig._is_native_module."""

    def test_bindings_dependency(self):
        assert PluginListConfig._is_native_module(
            {"dependencies": {"bindings": "^1.5.0"}}
        )

    def test_prebuild_dependency(self):
        assert PluginListConfig._is_native_module(
            {"dependencies": {"prebuild": "^1.0.0"}}
        )

    def test_nan_dependency(self):
        assert PluginListConfig._is_native_module(
            {"dependencies": {"nan": "^2.0.0"}}
        )

    def test_node_pre_gyp_dependency(self):
        assert PluginListConfig._is_native_module(
            {"dependencies": {"node-pre-gyp": "^0.15.0"}}
        )

    def test_node_gyp_build_dependency(self):
        assert PluginListConfig._is_native_module(
            {"dependencies": {"node-gyp-build": "^4.0.0"}}
        )

    def test_gypfile_field(self):
        assert PluginListConfig._is_native_module({"gypfile": True})

    def test_binary_field(self):
        assert PluginListConfig._is_native_module(
            {"binary": {"module_name": "addon"}}
        )

    def test_non_native_package(self):
        assert not PluginListConfig._is_native_module(
            {"dependencies": {"lodash": "^4.0.0"}}
        )

    def test_empty_package(self):
        assert not PluginListConfig._is_native_module({})

    def test_no_dependencies_key(self):
        assert not PluginListConfig._is_native_module({"name": "foo", "version": "1.0.0"})


class TestGatherNativeModules:
    """Tests for PluginListConfig._gather_native_modules."""

    def test_finds_native_transitive_dep(self, tmp_path):
        """A private dep depends on a native module -> that module is found."""
        _make_node_module(
            tmp_path, "ssh2",
            dependencies={"cpu-features": "^0.0.9"},
        )
        _make_node_module(
            tmp_path, "cpu-features",
            dependencies={"node-gyp-build": "^4.0.0"},
        )

        result = PluginListConfig._gather_native_modules(tmp_path, {"ssh2"})
        assert result == {"cpu-features"}

    def test_no_native_deps(self, tmp_path):
        _make_node_module(
            tmp_path, "lodash",
            dependencies={"underscore": "^1.0.0"},
        )
        _make_node_module(tmp_path, "underscore")

        result = PluginListConfig._gather_native_modules(tmp_path, {"lodash"})
        assert result == set()

    def test_cycle_avoidance(self, tmp_path):
        """Circular dependencies don't cause infinite recursion."""
        _make_node_module(
            tmp_path, "a",
            dependencies={"b": "^1.0.0"},
        )
        _make_node_module(
            tmp_path, "b",
            dependencies={"a": "^1.0.0"},
        )

        result = PluginListConfig._gather_native_modules(tmp_path, {"a"})
        assert result == set()

    def test_unresolvable_dep_skipped(self, tmp_path):
        result = PluginListConfig._gather_native_modules(tmp_path, {"nonexistent"})
        assert result == set()

    def test_direct_dep_is_native(self, tmp_path):
        """The private dep itself is native."""
        _make_node_module(
            tmp_path, "cpu-features",
            dependencies={"node-gyp-build": "^4.0.0"},
        )

        result = PluginListConfig._gather_native_modules(tmp_path, {"cpu-features"})
        assert result == {"cpu-features"}

    def test_multiple_native_deps(self, tmp_path):
        """Multiple native modules found across different branches."""
        _make_node_module(
            tmp_path, "parent",
            dependencies={"native-a": "^1.0.0", "native-b": "^1.0.0"},
        )
        _make_node_module(
            tmp_path, "native-a",
            dependencies={"nan": "^2.0.0"},
        )
        _make_node_module(
            tmp_path, "native-b",
            dependencies={"bindings": "^1.5.0"},
        )

        result = PluginListConfig._gather_native_modules(tmp_path, {"parent"})
        assert result == {"native-a", "native-b"}

    def test_native_in_optional_dependencies(self, tmp_path):
        """Native modules reachable via optionalDependencies are found."""
        _make_node_module(
            tmp_path, "ssh2",
            optional_dependencies={"cpu-features": "~0.0.10"},
        )
        _make_node_module(
            tmp_path, "cpu-features",
            dependencies={"nan": "^2.19.0"},
        )

        result = PluginListConfig._gather_native_modules(tmp_path, {"ssh2"})
        assert result == {"cpu-features"}

    def test_mixed_deps_and_optional_deps(self, tmp_path):
        """Walker follows both dependencies and optionalDependencies."""
        _make_node_module(
            tmp_path, "docker-modem",
            dependencies={"readable-stream": "^3.0.0"},
            optional_dependencies={"ssh2": "^1.15.0"},
        )
        _make_node_module(tmp_path, "readable-stream")
        _make_node_module(
            tmp_path, "ssh2",
            optional_dependencies={"cpu-features": "~0.0.10"},
        )
        _make_node_module(
            tmp_path, "cpu-features",
            dependencies={"nan": "^2.19.0"},
        )

        result = PluginListConfig._gather_native_modules(tmp_path, {"docker-modem"})
        assert result == {"cpu-features"}


class TestComputeBackendBuildArgsWithNative:
    """Tests for --suppress-native-package in _compute_backend_build_args."""

    def test_private_dep_with_native_transitive(self, tmp_path):
        """Private dep has a native transitive dep -> suppress it."""
        _make_plugin_dir(
            tmp_path, "plugins/backend", "@test/my-backend", "backend-plugin",
            dependencies={"ssh2": "^1.0.0"},
        )
        _make_node_module(
            tmp_path, "ssh2",
            dependencies={"cpu-features": "^0.0.9"},
        )
        _make_node_module(
            tmp_path, "cpu-features",
            dependencies={"node-gyp-build": "^4.0.0"},
        )

        result = PluginListConfig._compute_backend_build_args(
            tmp_path, "plugins/backend",
            tmp_path / "plugins/backend/package.json", set(),
        )
        assert "--suppress-native-package cpu-features" in result

    def test_no_native_deps_no_suppress(self, tmp_path):
        """Private dep with no native transitive deps -> no suppress flags."""
        _make_plugin_dir(
            tmp_path, "plugins/backend", "@test/my-backend", "backend-plugin",
            dependencies={"lodash": "^4.0.0"},
        )
        _make_node_module(tmp_path, "lodash")

        result = PluginListConfig._compute_backend_build_args(
            tmp_path, "plugins/backend",
            tmp_path / "plugins/backend/package.json", set(),
        )
        assert "--suppress-native-package" not in result

    def test_combined_embed_and_suppress(self, tmp_path):
        """Embed, unshare, AND suppress flags all present."""
        _make_plugin_dir(
            tmp_path, "plugins/backend", "@test/my-backend", "backend-plugin",
            dependencies={
                "@custom/lib": "^1.0.0",
                "ssh2": "^1.0.0",
            },
        )
        _make_node_module(
            tmp_path, "@custom/lib",
            dependencies={"@backstage/catalog-model": "^1.7.0"},
        )
        _make_node_module(
            tmp_path, "ssh2",
            dependencies={"cpu-features": "^0.0.9"},
        )
        _make_node_module(
            tmp_path, "cpu-features",
            dependencies={"node-gyp-build": "^4.0.0"},
        )

        host = {"@backstage/catalog-model"}
        result = PluginListConfig._compute_backend_build_args(
            tmp_path, "plugins/backend",
            tmp_path / "plugins/backend/package.json", host,
        )
        assert "--embed-package @custom/lib" in result
        assert "--suppress-native-package cpu-features" in result

    def test_args_ordering(self, tmp_path):
        """Flags are ordered: --embed-package, --shared-package, --suppress-native-package."""
        _make_plugin_dir(
            tmp_path, "plugins/backend", "@test/my-backend", "backend-plugin",
            dependencies={
                "@backstage/new-pkg": "^0.1.0",
                "@custom/lib": "^1.0.0",
                "ssh2": "^1.0.0",
            },
        )
        _make_node_module(
            tmp_path, "@custom/lib",
            dependencies={"@backstage/missing": "^0.1.0"},
        )
        _make_node_module(
            tmp_path, "ssh2",
            dependencies={"cpu-features": "^0.0.9"},
        )
        _make_node_module(
            tmp_path, "cpu-features",
            dependencies={"node-gyp-build": "^4.0.0"},
        )

        result = PluginListConfig._compute_backend_build_args(
            tmp_path, "plugins/backend",
            tmp_path / "plugins/backend/package.json", set(),
        )
        embed_idx = result.index("--embed-package")
        shared_idx = result.index("--shared-package")
        suppress_idx = result.index("--suppress-native-package")
        assert embed_idx < shared_idx < suppress_idx


class TestComputeBackendBuildArgsEmbeddedBackstageNative:
    """Native modules in embedded @backstage/* deps should be suppressed."""

    def test_embedded_backstage_dep_with_native_transitive(self, tmp_path):
        """An @backstage/* dep not in host gets embedded; its transitive native dep is suppressed.

        Mirrors the real chain: backend-common -> dockerode -> docker-modem
        -> ssh2 -[optional]-> cpu-features (native).
        """
        _make_plugin_dir(
            tmp_path, "plugins/backend", "@test/my-backend", "backend-plugin",
            dependencies={"@backstage/backend-common": "^1.0.0"},
        )
        _make_node_module(
            tmp_path, "@backstage/backend-common",
            dependencies={"dockerode": "^4.0.0"},
        )
        _make_node_module(
            tmp_path, "dockerode",
            dependencies={"docker-modem": "^3.0.0"},
        )
        _make_node_module(
            tmp_path, "docker-modem",
            optional_dependencies={"ssh2": "^1.15.0"},
        )
        _make_node_module(
            tmp_path, "ssh2",
            optional_dependencies={"cpu-features": "~0.0.10"},
        )
        _make_node_module(
            tmp_path, "cpu-features",
            dependencies={"nan": "^2.19.0"},
        )

        result = PluginListConfig._compute_backend_build_args(
            tmp_path, "plugins/backend",
            tmp_path / "plugins/backend/package.json", set(),
        )
        assert "--embed-package @backstage/backend-common" in result
        assert "--shared-package !@backstage/backend-common" in result
        assert "--suppress-native-package cpu-features" in result


class TestComputeBackendBuildArgsSiblingNative:
    """Native modules in auto-embedded sibling deps should be suppressed."""

    def test_sibling_node_dep_with_native_transitive(self, tmp_path):
        """Mirrors the real techdocs-backend chain:
        sibling techdocs-node -> dockerode -> docker-modem -> ssh2 -> cpu-features.
        """
        _make_plugin_dir(
            tmp_path, "plugins/techdocs-backend",
            "@backstage/plugin-techdocs-backend", "backend-plugin",
            dependencies={
                "@backstage/plugin-techdocs-node": "workspace:^",
                "express": "^4.22.0",
            },
        )
        _make_node_module(
            tmp_path, "@backstage/plugin-techdocs-node",
            dependencies={"dockerode": "^4.0.0"},
        )
        _make_node_module(
            tmp_path, "dockerode",
            dependencies={"docker-modem": "^3.0.0"},
        )
        _make_node_module(
            tmp_path, "docker-modem",
            optional_dependencies={"ssh2": "^1.15.0"},
        )
        _make_node_module(
            tmp_path, "ssh2",
            optional_dependencies={"cpu-features": "~0.0.10"},
        )
        _make_node_module(
            tmp_path, "cpu-features",
            dependencies={"nan": "^2.19.0"},
        )
        _make_node_module(tmp_path, "express")

        result = PluginListConfig._compute_backend_build_args(
            tmp_path, "plugins/techdocs-backend",
            tmp_path / "plugins/techdocs-backend/package.json", set(),
        )
        assert "--suppress-native-package cpu-features" in result
        assert "--embed-package" not in result

    def test_sibling_without_native_deps_no_suppress(self, tmp_path):
        """Sibling with no native transitive deps produces no suppress flags."""
        _make_plugin_dir(
            tmp_path, "plugins/todo-backend",
            "@test/plugin-todo-backend", "backend-plugin",
            dependencies={
                "@test/plugin-todo-common": "^1.0.0",
                "@test/plugin-todo-node": "^1.0.0",
            },
        )
        _make_node_module(
            tmp_path, "@test/plugin-todo-common",
            dependencies={"lodash": "^4.0.0"},
        )
        _make_node_module(
            tmp_path, "@test/plugin-todo-node",
            dependencies={"express": "^4.0.0"},
        )
        _make_node_module(tmp_path, "lodash")
        _make_node_module(tmp_path, "express")

        result = PluginListConfig._compute_backend_build_args(
            tmp_path, "plugins/todo-backend",
            tmp_path / "plugins/todo-backend/package.json", set(),
        )
        assert result == ""

    def test_sibling_not_in_node_modules_skipped(self, tmp_path):
        """Unresolvable sibling (not in node_modules) is silently skipped."""
        _make_plugin_dir(
            tmp_path, "plugins/my-backend",
            "@test/my-plugin-backend", "backend-plugin",
            dependencies={"lodash": "^4.0.0"},
        )
        _make_node_module(tmp_path, "lodash")

        result = PluginListConfig._compute_backend_build_args(
            tmp_path, "plugins/my-backend",
            tmp_path / "plugins/my-backend/package.json", set(),
        )
        assert result == ""


class TestCreateDefaultWithNativeSuppression:
    """End-to-end tests for create_default with native module suppression."""

    def test_native_dep_detected_end_to_end(self, tmp_path, monkeypatch):
        lockfile = tmp_path / "host-yarn.lock"
        lockfile.write_text('"@backstage/core@npm:^1.0.0":\n  version: 1.0.0\n')
        monkeypatch.setattr(constants, "HOST_LOCKFILE", lockfile)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _make_plugin_dir(
            workspace, "plugins/backend",
            "@test/my-backend", "backend-plugin",
            dependencies={"ssh2": "^1.0.0"},
        )
        _make_node_module(
            workspace, "ssh2",
            dependencies={"cpu-features": "^0.0.9"},
        )
        _make_node_module(
            workspace, "cpu-features",
            dependencies={"node-gyp-build": "^4.0.0"},
        )

        config = PluginListConfig.create_default(workspace)
        args = config.get_plugins()["plugins/backend"]
        assert "--suppress-native-package cpu-features" in args


class TestPluginListConfigPopulateBuildArgs:
    """Tests for PluginListConfig.populate_build_args method."""

    def test_backend_plugin_gets_args_computed(self, tmp_path, monkeypatch):
        """Backend plugin with empty args gets build args populated."""
        lockfile = tmp_path / "host-yarn.lock"
        lockfile.write_text('"@backstage/core@npm:^1.0.0":\n  version: 1.0.0\n')
        monkeypatch.setattr(constants, "HOST_LOCKFILE", lockfile)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _make_plugin_dir(
            workspace, "plugins/backend",
            "@test/my-backend", "backend-plugin",
            dependencies={"@backstage/new-experimental": "^0.1.0"},
        )

        cfg = PluginListConfig({"plugins/backend": ""})
        cfg.populate_build_args(workspace)

        args = cfg.get_plugins()["plugins/backend"]
        assert "--embed-package @backstage/new-experimental" in args
        assert "--shared-package !@backstage/new-experimental" in args

    def test_frontend_plugin_stays_empty(self, tmp_path, monkeypatch):
        """Frontend plugin with empty args stays empty after population."""
        lockfile = tmp_path / "host-yarn.lock"
        lockfile.write_text("")
        monkeypatch.setattr(constants, "HOST_LOCKFILE", lockfile)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _make_plugin_dir(
            workspace, "plugins/todo",
            "@test/plugin-todo", "frontend-plugin",
        )

        cfg = PluginListConfig({"plugins/todo": ""})
        cfg.populate_build_args(workspace)

        assert cfg.get_plugins()["plugins/todo"] == ""

    def test_existing_args_overwritten(self, tmp_path, monkeypatch):
        """Stale build args are overwritten with freshly computed ones."""
        lockfile = tmp_path / "host-yarn.lock"
        lockfile.write_text('"@backstage/core@npm:^1.0.0":\n  version: 1.0.0\n')
        monkeypatch.setattr(constants, "HOST_LOCKFILE", lockfile)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _make_plugin_dir(
            workspace, "plugins/backend",
            "@test/my-backend", "backend-plugin",
            dependencies={"@backstage/new-pkg": "^0.1.0"},
        )

        cfg = PluginListConfig({"plugins/backend": "--embed-package @old/stale-dep"})
        cfg.populate_build_args(workspace)

        args = cfg.get_plugins()["plugins/backend"]
        assert "@old/stale-dep" not in args
        assert "--embed-package @backstage/new-pkg" in args

    def test_nonexistent_plugin_warns_and_keeps_empty(self, tmp_path, monkeypatch):
        """Plugin path not found in workspace logs a warning and stays with empty args."""
        lockfile = tmp_path / "host-yarn.lock"
        lockfile.write_text("")
        monkeypatch.setattr(constants, "HOST_LOCKFILE", lockfile)

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        cfg = PluginListConfig({"plugins/nonexistent": "--old-arg"})
        cfg.populate_build_args(workspace)

        assert cfg.get_plugins()["plugins/nonexistent"] == ""

    def test_plugin_without_backstage_role_stays_empty(self, tmp_path, monkeypatch):
        """Plugin without backstage.role field stays with empty args."""
        lockfile = tmp_path / "host-yarn.lock"
        lockfile.write_text("")
        monkeypatch.setattr(constants, "HOST_LOCKFILE", lockfile)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        pkg_dir = workspace / "plugins" / "no-role"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text(
            json.dumps({"name": "@test/no-role", "version": "1.0.0"})
        )

        cfg = PluginListConfig({"plugins/no-role": ""})
        cfg.populate_build_args(workspace)

        assert cfg.get_plugins()["plugins/no-role"] == ""

    def test_mixed_scenario(self, tmp_path, monkeypatch):
        """Backend, frontend, and invalid paths handled together."""
        lockfile = tmp_path / "host-yarn.lock"
        lockfile.write_text('"@backstage/core@npm:^1.0.0":\n  version: 1.0.0\n')
        monkeypatch.setattr(constants, "HOST_LOCKFILE", lockfile)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _make_plugin_dir(
            workspace, "plugins/backend",
            "@test/my-backend", "backend-plugin",
            dependencies={"@backstage/new-pkg": "^0.1.0"},
        )
        _make_plugin_dir(
            workspace, "plugins/frontend",
            "@test/my-frontend", "frontend-plugin",
        )

        cfg = PluginListConfig({
            "plugins/backend": "",
            "plugins/frontend": "",
            "plugins/missing": "--old",
        })
        cfg.populate_build_args(workspace)
        plugins = cfg.get_plugins()

        assert "--embed-package @backstage/new-pkg" in plugins["plugins/backend"]
        assert plugins["plugins/frontend"] == ""
        assert plugins["plugins/missing"] == ""

    def test_roundtrip_from_file(self, tmp_path, monkeypatch):
        """from_file -> populate_build_args -> to_file roundtrip."""
        lockfile = tmp_path / "host-yarn.lock"
        lockfile.write_text('"@backstage/core@npm:^1.0.0":\n  version: 1.0.0\n')
        monkeypatch.setattr(constants, "HOST_LOCKFILE", lockfile)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _make_plugin_dir(
            workspace, "plugins/todo",
            "@test/plugin-todo", "frontend-plugin",
        )
        _make_plugin_dir(
            workspace, "plugins/todo-backend",
            "@test/plugin-todo-backend", "backend-plugin",
            dependencies={"@backstage/new-experimental": "^0.1.0"},
        )

        input_file = tmp_path / "plugins-list.yaml"
        input_file.write_text("plugins/todo:\nplugins/todo-backend:\n")

        cfg = PluginListConfig.from_file(input_file)
        cfg.populate_build_args(workspace)
        output_file = tmp_path / "plugins-list-out.yaml"
        cfg.to_file(output_file)

        reloaded = PluginListConfig.from_file(output_file)
        plugins = reloaded.get_plugins()
        assert plugins["plugins/todo"] == ""
        assert "--embed-package @backstage/new-experimental" in plugins["plugins/todo-backend"]

    def test_returns_self(self, tmp_path, monkeypatch):
        """populate_build_args returns self for method chaining."""
        lockfile = tmp_path / "host-yarn.lock"
        lockfile.write_text("")
        monkeypatch.setattr(constants, "HOST_LOCKFILE", lockfile)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _make_plugin_dir(
            workspace, "plugins/todo",
            "@test/plugin-todo", "frontend-plugin",
        )

        cfg = PluginListConfig({"plugins/todo": ""})
        result = cfg.populate_build_args(workspace)
        assert result is cfg

    def test_backend_no_deps_stays_empty(self, tmp_path, monkeypatch):
        """Backend plugin with no deps that need embedding stays with empty args."""
        lockfile = tmp_path / "host-yarn.lock"
        lockfile.write_text('"@backstage/core@npm:^1.0.0":\n  version: 1.0.0\n')
        monkeypatch.setattr(constants, "HOST_LOCKFILE", lockfile)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        _make_plugin_dir(
            workspace, "plugins/simple-backend",
            "@test/simple-backend", "backend-plugin",
        )

        cfg = PluginListConfig({"plugins/simple-backend": ""})
        cfg.populate_build_args(workspace)

        assert cfg.get_plugins()["plugins/simple-backend"] == ""


class TestLogBuildArgsDiff:
    """Tests for PluginListConfig._log_build_args_diff."""

    def test_changed_plugins_logged(self):
        before = {"plugins/a": "", "plugins/b": "--old"}
        after = {"plugins/a": "--new", "plugins/b": "--new"}
        PluginListConfig._log_build_args_diff(before, after)

    def test_unchanged_plugins_logged(self):
        before = {"plugins/a": "--same"}
        after = {"plugins/a": "--same"}
        PluginListConfig._log_build_args_diff(before, after)

    def test_mixed_changed_and_unchanged(self):
        before = {"plugins/a": "", "plugins/b": "--keep"}
        after = {"plugins/a": "--new", "plugins/b": "--keep"}
        PluginListConfig._log_build_args_diff(before, after)
