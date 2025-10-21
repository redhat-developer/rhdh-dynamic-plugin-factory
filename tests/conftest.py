"""
Shared pytest fixtures for RHDH Dynamic Plugin Factory tests.
"""

import argparse
import json
from pathlib import Path
import pytest
from unittest.mock import MagicMock
from dotenv import dotenv_values


@pytest.fixture
def mock_logger():
    """Create a mocked logger to avoid output during tests."""
    logger = MagicMock()
    return logger


@pytest.fixture
def mock_args(tmp_path):
    """Create mock argparse.Namespace with default valid arguments."""
    args = argparse.Namespace(
        workspace_path=".",
        config_dir=tmp_path / "config",
        repo_path=tmp_path / "workspace",
        log_level="INFO",
        use_local=False,
        push_images=False,
        output_dir=tmp_path / "outputs",
        verbose=False
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
def valid_source_json(tmp_path):
    """Create a valid source.json file."""
    source_data = {
        "repo": "https://github.com/awslabs/backstage-plugins-for-aws",
        "repo-ref": "78df9399a81cfd95265cab53815f54210b1d7f50",
        "repo-flat": True,
        "repo-backstage-version": "1.42.5"
    }
    
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    source_file = config_dir / "source.json"
    source_file.write_text(json.dumps(source_data, indent=2))
    
    return source_file


@pytest.fixture
def valid_plugins_list_yaml(tmp_path):
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
def temp_workspace(tmp_path):
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
def setup_test_env(tmp_path, monkeypatch, valid_default_env):
    """
    Set up a complete test environment with all required files and environment variables.
    
    This fixture combines multiple setups to provide a fully configured test environment.
    """
    # Create directory structure
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    
    # Create source.json
    source_data = {
        "repo": "https://github.com/awslabs/backstage-plugins-for-aws",
        "repo-ref": "78df9399a81cfd95265cab53815f54210b1d7f50",
        "repo-flat": True,
        "repo-backstage-version": "1.42.5"
    }
    (config_dir / "source.json").write_text(json.dumps(source_data, indent=2))
    
    # Create plugins-list.yaml
    plugins_content = """plugins/ecs/frontend:
plugins/ecs/backend: --embed-package @aws/aws-core-plugin-for-backstage-common
"""
    (config_dir / "plugins-list.yaml").write_text(plugins_content)
    
    # Return paths
    return {
        "config_dir": config_dir,
        "workspace_dir": workspace_dir,
        "tmp_path": tmp_path
    }


@pytest.fixture
def clean_env(monkeypatch):
    """Clean environment fixture that removes all relevant environment variables."""
    # Remove all relevant environment variables
    env_vars = [
        "RHDH_CLI_VERSION",
        "LOG_LEVEL",
        "WORKSPACE_PATH",
        "REGISTRY_URL",
        "REGISTRY_USERNAME",
        "REGISTRY_PASSWORD",
        "REGISTRY_NAMESPACE",
        "REGISTRY_INSECURE"
    ]
    
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    
    return monkeypatch

