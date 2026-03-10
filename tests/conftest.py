"""
Shared pytest fixtures for RHDH Dynamic Plugin Factory tests.
"""

import argparse
import json
from pathlib import Path
import pytest
from unittest.mock import MagicMock
from dotenv import dotenv_values

from src.rhdh_dynamic_plugin_factory.config import PluginFactoryConfig


def _write_source_json(directory: Path, repo: str, repo_ref: str, workspace_path: str = ".") -> None:
    """Write a source.json file into the given directory, creating it if needed."""
    directory.mkdir(parents=True, exist_ok=True)
    data = {"repo": repo, "repo-ref": repo_ref, "workspace-path": workspace_path}
    (directory / "source.json").write_text(json.dumps(data))


@pytest.fixture
def write_source_json():
    """Factory fixture that returns a helper to write source.json files.

    Usage:
        write_source_json(directory, repo, repo_ref, workspace_path=".")
    """
    return _write_source_json


@pytest.fixture
def mock_logger():
    """Create a mocked logger to avoid output during tests."""
    logger = MagicMock()
    return logger


@pytest.fixture
def mock_args(tmp_path):
    """Create mock argparse.Namespace with default valid arguments.
    
    Uses Path objects for config_dir and repo_path to match argparse type=Path behavior.
    """
    args = argparse.Namespace(
        workspace_path=".",
        config_dir=tmp_path / "config",
        repo_path=tmp_path / "workspace",
        use_local=False,
        push_images=False,
        output_dir=str(tmp_path / "outputs"),
        verbose=False,
        source_repo=None,
        source_ref=None,
    )
    return args


@pytest.fixture
def valid_default_env(monkeypatch):
    """Load environment variables from the real default.env file."""
    
    # Load the real default.env file from project root since its path is hardcoded
    default_env_path = Path(__file__).parent.parent / "default.env"
    
    if default_env_path.exists():
        env_vars = dotenv_values(default_env_path)
        
        # Set environment variables from the file
        for key, value in env_vars.items():
            if value:  # Only set if value is not None or empty
                monkeypatch.setenv(key, value)
    
    return default_env_path


@pytest.fixture
def valid_source_json(tmp_path: Path):
    """Create a valid source.json file."""
    config_dir = tmp_path / "config"
    _write_source_json(
        config_dir,
        "https://github.com/awslabs/backstage-plugins-for-aws",
        "78df9399a81cfd95265cab53815f54210b1d7f50",
    )
    return config_dir / "source.json"


@pytest.fixture
def valid_plugins_list_yaml(tmp_path: Path):
    """Create a valid plugins-list.yaml file."""
    plugins_content = """plugins/ecs/frontend:
plugins/ecs/backend: --embed-package @aws/aws-core-plugin-for-backstage-common --embed-package @aws/aws-core-plugin-for-backstage-node
"""
    
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    plugins_file = config_dir / "plugins-list.yaml"
    plugins_file.write_text(plugins_content)
    
    return plugins_file


@pytest.fixture
def temp_workspace(tmp_path: Path):
    """Create a temporary workspace directory with realistic structure."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    
    # Create some basic workspace structure
    plugins_dir = workspace / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    
    # Create a sample plugin directory
    sample_plugin = plugins_dir / "sample-plugin"
    sample_plugin.mkdir(parents=True, exist_ok=True)
    
    # Create a package.json for the sample plugin
    package_json = {
        "name": "@test/sample-plugin",
        "version": "1.0.0",
        "backstage": {
            "role": "backend-plugin"
        }
    }
    (sample_plugin / "package.json").write_text(json.dumps(package_json, indent=2))
    
    return workspace


@pytest.fixture
def setup_test_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Set up a complete test environment with all required files and environment variables.
    
    This fixture combines multiple setups to provide a fully configured test environment.
    """
    # Create directory structure
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    
    # Create source.json
    _write_source_json(
        config_dir,
        "https://github.com/awslabs/backstage-plugins-for-aws",
        "78df9399a81cfd95265cab53815f54210b1d7f50",
    )
    
    # Create plugins-list.yaml
    plugins_content = """plugins/ecs/frontend:
plugins/ecs/backend: --embed-package @aws/aws-core-plugin-for-backstage-common
"""
    (config_dir / "plugins-list.yaml").write_text(plugins_content)
    
    # Set common environment variables
    monkeypatch.setenv("RHDH_CLI_VERSION", "1.7.2")
    
    return {
        "config_dir": str(config_dir),
        "source_dir": str(source_dir),
        "tmp_path": tmp_path
    }


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch):
    """Clean environment fixture that removes all relevant environment variables."""
    # Remove all relevant environment variables
    env_vars = [
        "RHDH_CLI_VERSION",
        "REGISTRY_URL",
        "REGISTRY_USERNAME",
        "REGISTRY_PASSWORD",
        "REGISTRY_NAMESPACE",
        "REGISTRY_INSECURE"
    ]
    
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    
    return monkeypatch


@pytest.fixture
def make_config(setup_test_env):
    """Factory fixture to create PluginFactoryConfig with sensible defaults.
    
    Usage:
        config = make_config()  # All defaults
        config = make_config(registry_url="quay.io")  # With override
        config = make_config(registry_url=None)  # Explicitly set to None
    """
    def _make_config(**overrides):
        defaults = {
            "config_dir": setup_test_env["config_dir"],
            "repo_path": setup_test_env["source_dir"],
            "rhdh_cli_version": "1.7.2",
            "workspace_path": ".",
        }
        defaults.update(overrides)
        return PluginFactoryConfig(**defaults)
    return _make_config

