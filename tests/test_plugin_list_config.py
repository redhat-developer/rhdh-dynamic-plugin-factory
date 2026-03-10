"""
Unit tests for PluginListConfig class.

Tests the plugin list configuration loading and management.
"""

import json
import yaml
import pytest

from src.rhdh_dynamic_plugin_factory.config import PluginListConfig


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


def _make_plugin_dir(base, rel_path, name, role):
    """Helper to create a plugin directory with a package.json."""
    plugin_dir = base / rel_path
    plugin_dir.mkdir(parents=True, exist_ok=True)
    pkg = {"name": name, "version": "1.0.0", "backstage": {"role": role}}
    (plugin_dir / "package.json").write_text(json.dumps(pkg))
    return plugin_dir


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
        # Also has common/node packages that should be ignored (not plugin roles)
        _make_plugin_dir(tmp_path, "plugins/ecs/common", "@aws/aws-core-plugin-for-backstage-common", "common-library")

        config = PluginListConfig.create_default(tmp_path)
        plugins = config.get_plugins()

        assert len(plugins) == 2
        assert "plugins/ecs/frontend" in plugins
        assert "plugins/ecs/backend" in plugins
