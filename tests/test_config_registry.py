"""
Unit tests for PluginFactoryConfig registry validation and buildah login.

Tests the registry configuration validation in __post_init__ and
the _buildah_login functionality.
"""

import subprocess
from unittest.mock import patch, MagicMock
import pytest

from src.rhdh_dynamic_plugin_factory.config import PluginFactoryConfig
from src.rhdh_dynamic_plugin_factory.exceptions import ConfigurationError, ExecutionError


class TestRegistryValidation:
    """Tests for registry validation in __post_init__ when push_images is True."""
    
    def test_no_validation_when_push_images_false(self, make_config):
        """Test that registry fields are not validated when push_images is False."""
        # Should not raise exceptions even with no registry fields set
        config = make_config()
        assert config.push_images is False
    
    def test_missing_registry_url(self, make_config):
        """Test that missing REGISTRY_URL raises ConfigurationError when push_images is True."""
        with pytest.raises(ConfigurationError, match="REGISTRY_URL environment variable is required"):
            make_config(
                push_images=True,
                registry_url=None,
                registry_namespace="test-namespace",
                registry_username="test-user",
                registry_password="test-password",
            )
    
    def test_missing_registry_namespace(self, make_config):
        """Test that missing REGISTRY_NAMESPACE raises ConfigurationError when push_images is True."""
        with pytest.raises(ConfigurationError, match="REGISTRY_NAMESPACE environment variable is required"):
            make_config(
                push_images=True,
                registry_url="quay.io",
                registry_namespace=None,
                registry_username="test-user",
                registry_password="test-password",
            )
    
    def test_missing_registry_credentials(self, make_config):
        """Test that missing credentials raise ConfigurationError when push_images is True."""
        with pytest.raises(ConfigurationError, match="REGISTRY_USERNAME and REGISTRY_PASSWORD environment variables are required"):
            make_config(
                push_images=True,
                registry_url="quay.io",
                registry_namespace="test-namespace",
                registry_username=None,
                registry_password=None,
            )
    
    def test_missing_registry_username(self, make_config):
        """Test that missing username raises ConfigurationError when push_images is True."""
        with pytest.raises(ConfigurationError, match="REGISTRY_USERNAME and REGISTRY_PASSWORD environment variables are required"):
            make_config(
                push_images=True,
                registry_url="quay.io",
                registry_namespace="test-namespace",
                registry_username=None,
                registry_password="test-password",
            )
    
    def test_missing_registry_password(self, make_config):
        """Test that missing password raises ConfigurationError when push_images is True."""
        with pytest.raises(ConfigurationError, match="REGISTRY_USERNAME and REGISTRY_PASSWORD environment variables are required"):
            make_config(
                push_images=True,
                registry_url="quay.io",
                registry_namespace="test-namespace",
                registry_username="test-user",
                registry_password=None,
            )
    
    def test_valid_registry_config(self, make_config):
        """Test that valid registry configuration passes validation."""
        config = make_config(
            push_images=True,
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password="test-password",
        )
        assert config.push_images is True
        assert config.registry_url == "quay.io"


class TestBuildahLogin:
    """Tests for PluginFactoryConfig._buildah_login method."""
    
    def test_successful_buildah_login(self, make_config):
        """Test successful buildah login with valid credentials."""
        config = make_config(
            push_images=True,
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password="test-password",
            registry_insecure=False,
        )
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            with patch.object(config, 'logger') as mock_logger:
                config._buildah_login()
                
                mock_run.assert_called_once()
                call_args = mock_run.call_args
                
                expected_cmd = [
                    "buildah", "login",
                    "--username", "test-user",
                    "--password", "test-password",
                    "quay.io"
                ]
                assert call_args[0][0] == expected_cmd
                assert call_args[1]['check'] is True
                assert call_args[1]['stdout'] == subprocess.PIPE
                assert call_args[1]['stderr'] == subprocess.PIPE
                
                mock_logger.info.assert_called_with(
                    "Logged in to registry quay.io with buildah."
                )
    
    def test_failed_buildah_login(self, make_config):
        """Test that failed buildah login raises ExecutionError."""
        config = make_config(
            push_images=True,
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password="wrong-password",
            registry_insecure=False,
        )
        
        with patch('subprocess.run') as mock_run:
            mock_error = subprocess.CalledProcessError(
                returncode=1,
                cmd=['buildah', 'login'],
                stderr=b"Authentication failed"
            )
            mock_run.side_effect = mock_error
            
            with pytest.raises(ExecutionError, match="Failed to login to registry quay.io") as exc_info:
                config._buildah_login()
            
            assert exc_info.value.step == "buildah login"
            assert exc_info.value.returncode == 1
    
    def test_insecure_registry_flag(self, make_config):
        """Test that insecure flag is added to buildah command when registry_insecure is True."""
        config = make_config(
            push_images=True,
            registry_url="localhost:5000",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password="test-password",
            registry_insecure=True,
        )
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            config._buildah_login()
            
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            
            expected_cmd = [
                "buildah", "login",
                "--username", "test-user",
                "--password", "test-password",
                "--tls-verify=false",
                "localhost:5000"
            ]
            assert call_args[0][0] == expected_cmd
    
    def test_secure_registry_default(self, make_config):
        """Test that insecure flag is NOT added when registry_insecure is False."""
        config = make_config(
            push_images=True,
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password="test-password",
            registry_insecure=False,
        )
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            config._buildah_login()
            
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            
            expected_cmd = [
                "buildah", "login",
                "--username", "test-user",
                "--password", "test-password",
                "quay.io"
            ]
            assert call_args[0][0] == expected_cmd
            assert "--tls-verify=false" not in call_args[0][0]
