"""
Custom exceptions for RHDH Plugin Factory.
"""

class PluginFactoryError(Exception):
    """Base exception for all plugin factory errors.

    Used directly for internal factory logic failures such as
    auto-generating configuration files, plugin list management,
    or other non-external operations that go wrong.

    Attributes:
        reason: A human-readable description of what went wrong.
    """

    def __init__(self, reason: str = ""):
        super().__init__(reason)
        self.reason = reason

class ConfigurationError(PluginFactoryError):
    """User-facing configuration validation errors.

    Raised when configuration is invalid or missing, such as
    missing environment variables, bad source.json, invalid log levels,
    or missing registry credentials.

    Attributes:
        reason: A human-readable description of the configuration problem.
    """

class ExecutionError(PluginFactoryError):
    """External command or script execution failure.

    Raised when an external tool (git, buildah, yarn, shell scripts)
    fails during execution.

    Attributes:
        reason: A human-readable description of the failure.
        step: A short description of what was being attempted
              (e.g., "git clone", "export plugins").
        returncode: The exit code of the failed process, if available.
    """

    def __init__(self, reason: str = "", step: str = "", returncode: int | None = None):
        super().__init__(reason)
        self.step = step
        self.returncode = returncode
