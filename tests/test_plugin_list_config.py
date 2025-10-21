"""
Unit tests for PluginListConfig class.

Tests the plugin list configuration loading and management.
"""

from pathlib import Path

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
