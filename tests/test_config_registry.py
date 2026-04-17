"""
Unit tests for PluginFactoryConfig registry validation and buildah login.

Tests the registry configuration validation (_validate_registry_fields)
and the _buildah_login functionality.

Registry validation is no longer called in __post_init__; it is deferred
to workspace processing level.  These tests call the methods explicitly.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from src.rhdh_dynamic_plugin_factory.exceptions import (
    ConfigurationError,
    ExecutionError,
)


class TestRegistryValidation:
    """Tests for _validate_registry_fields (called explicitly, not in __post_init__)."""

    def test_no_validation_when_push_images_false(self, make_config):
        """Registry fields are not validated when push_images is False."""
        config = make_config()
        assert config.push_images is False

    def test_construction_with_push_images_no_registry_fields(self, make_config):
        """push_images=True with no registry fields does NOT raise at construction time."""
        config = make_config(push_images=True)
        assert config.push_images is True
        assert config.registry_url is None

    def test_missing_registry_url(self, make_config):
        """Missing REGISTRY_URL raises ConfigurationError."""
        config = make_config(
            push_images=True,
            registry_url=None,
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password="test-password",
        )
        with pytest.raises(ConfigurationError, match="REGISTRY_URL is required"):
            config._validate_registry_fields()

    def test_missing_registry_namespace(self, make_config):
        """Missing REGISTRY_NAMESPACE raises ConfigurationError."""
        config = make_config(
            push_images=True,
            registry_url="quay.io",
            registry_namespace=None,
            registry_username="test-user",
            registry_password="test-password",
        )
        with pytest.raises(ConfigurationError, match="REGISTRY_NAMESPACE is required"):
            config._validate_registry_fields()

    def test_no_auth_warns_but_does_not_raise(self, make_config):
        """No credentials and no auth file logs a warning but does NOT raise."""
        config = make_config(
            push_images=True,
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username=None,
            registry_password=None,
            registry_auth_file=None,
        )
        with patch.object(config, "logger") as mock_logger:
            config._validate_registry_fields()
            mock_logger.warning.assert_called_once()
            msg = mock_logger.warning.call_args[0][0]
            assert "REGISTRY_USERNAME" in msg
            assert "REGISTRY_AUTH_FILE" in msg

    def test_valid_with_username_password(self, make_config):
        """Username + password passes validation without warning."""
        config = make_config(
            push_images=True,
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password="test-password",
        )
        with patch.object(config, "logger") as mock_logger:
            config._validate_registry_fields()
            mock_logger.warning.assert_not_called()

    def test_valid_with_auth_file_only(self, make_config):
        """Auth file set with no username/password passes validation without warning."""
        config = make_config(
            push_images=True,
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username=None,
            registry_password=None,
            registry_auth_file="/auth.json",
        )
        with patch.object(config, "logger") as mock_logger:
            config._validate_registry_fields()
            mock_logger.warning.assert_not_called()

    def test_valid_with_both_auth_methods(self, make_config):
        """Both username/password AND auth file set passes validation without warning."""
        config = make_config(
            push_images=True,
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password="test-password",
            registry_auth_file="/auth.json",
        )
        with patch.object(config, "logger") as mock_logger:
            config._validate_registry_fields()
            mock_logger.warning.assert_not_called()

    def test_partial_credentials_warns(self, make_config):
        """Only username (no password, no auth file) logs warning."""
        config = make_config(
            push_images=True,
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password=None,
            registry_auth_file=None,
        )
        with patch.object(config, "logger") as mock_logger:
            config._validate_registry_fields()
            mock_logger.warning.assert_called_once()

    def test_partial_credentials_with_auth_file_no_warning(self, make_config):
        """Only username (no password) but auth file set -- no warning."""
        config = make_config(
            push_images=True,
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password=None,
            registry_auth_file="/auth.json",
        )
        with patch.object(config, "logger") as mock_logger:
            config._validate_registry_fields()
            mock_logger.warning.assert_not_called()

    def test_valid_registry_config(self, make_config):
        """Full registry configuration passes validation."""
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
        """Successful buildah login with valid credentials."""
        config = make_config(
            push_images=True,
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password="test-password",
            registry_insecure=False,
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            with patch.object(config, "logger") as mock_logger:
                config._buildah_login()

                mock_run.assert_called_once()
                call_args = mock_run.call_args

                expected_cmd = [
                    "buildah",
                    "login",
                    "--username",
                    "test-user",
                    "--password",
                    "test-password",
                    "quay.io",
                ]
                assert call_args[0][0] == expected_cmd
                assert call_args[1]["check"] is True
                assert call_args[1]["capture_output"] is True

                mock_logger.info.assert_called_with("Logged in to registry quay.io with buildah.")

    def test_failed_buildah_login(self, make_config):
        """Failed buildah login raises ExecutionError."""
        config = make_config(
            push_images=True,
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password="wrong-password",
            registry_insecure=False,
        )

        with patch("subprocess.run") as mock_run:
            mock_error = subprocess.CalledProcessError(
                returncode=1, cmd=["buildah", "login"], stderr=b"Authentication failed"
            )
            mock_run.side_effect = mock_error

            with pytest.raises(ExecutionError, match="Failed to login to registry quay.io") as exc_info:
                config._buildah_login()

            assert exc_info.value.step == "buildah login"
            assert exc_info.value.returncode == 1

    def test_insecure_registry_flag(self, make_config):
        """Insecure flag is added to buildah command when registry_insecure is True."""
        config = make_config(
            push_images=True,
            registry_url="localhost:5000",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password="test-password",
            registry_insecure=True,
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            config._buildah_login()

            mock_run.assert_called_once()
            call_args = mock_run.call_args

            expected_cmd = [
                "buildah",
                "login",
                "--username",
                "test-user",
                "--password",
                "test-password",
                "--tls-verify=false",
                "localhost:5000",
            ]
            assert call_args[0][0] == expected_cmd

    def test_secure_registry_default(self, make_config):
        """Insecure flag is NOT added when registry_insecure is False."""
        config = make_config(
            push_images=True,
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password="test-password",
            registry_insecure=False,
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            config._buildah_login()

            mock_run.assert_called_once()
            call_args = mock_run.call_args

            expected_cmd = [
                "buildah",
                "login",
                "--username",
                "test-user",
                "--password",
                "test-password",
                "quay.io",
            ]
            assert call_args[0][0] == expected_cmd
            assert "--tls-verify=false" not in call_args[0][0]

    def test_skip_login_when_auth_file_set(self, make_config):
        """Auth file set -- _buildah_login returns early, no subprocess call."""
        config = make_config(
            push_images=True,
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_auth_file="/auth.json",
        )

        with patch("subprocess.run") as mock_run:
            with patch.object(config, "logger") as mock_logger:
                config._buildah_login()
                mock_run.assert_not_called()
                mock_logger.info.assert_called_once()
                assert "/auth.json" in mock_logger.info.call_args[0][0]

    def test_skip_login_auth_file_with_username_password_present(self, make_config):
        """Auth file takes precedence -- login skipped even when credentials are set."""
        config = make_config(
            push_images=True,
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username="test-user",
            registry_password="test-password",
            registry_auth_file="/auth.json",
        )

        with patch("subprocess.run") as mock_run:
            config._buildah_login()
            mock_run.assert_not_called()

    def test_skip_login_when_no_credentials_and_no_auth_file(self, make_config):
        """No credentials and no auth file -- login skipped (pre-authenticated host)."""
        config = make_config(
            push_images=True,
            registry_url="quay.io",
            registry_namespace="test-namespace",
            registry_username=None,
            registry_password=None,
            registry_auth_file=None,
        )

        with patch("subprocess.run") as mock_run:
            with patch.object(config, "logger") as mock_logger:
                config._buildah_login()
                mock_run.assert_not_called()
                mock_logger.debug.assert_called_once()
                assert "relying on existing host auth" in mock_logger.debug.call_args[0][0]
