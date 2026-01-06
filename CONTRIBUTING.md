# Contributing to RHDH Dynamic Plugin Factory

Thank you for your interest in contributing to the RHDH Dynamic Plugin Factory! This guide will help you get started with development, testing, and submitting contributions.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Environment](#development-environment)
- [Project Structure](#project-structure)
- [Running Tests](#running-tests)
- [Development Workflow](#development-workflow)
- [Code Quality Standards](#code-quality-standards)
- [Submitting Changes](#submitting-changes)

## Getting Started

### Fork and Clone

1. **Fork the repository** on GitHub by clicking the "Fork" button

2. **Clone your fork** locally:

```bash
git clone https://github.com/YOUR_USERNAME/rhdh-dynamic-plugin-factory
cd rhdh-dynamic-plugin-factory
```

**3. Add the upstream remote:**

```bash
git remote add upstream https://github.com/redhat-developer/rhdh-dynamic-plugin-factory
```

### Choose Your Development Environment

You can develop using either containers or local setup.

## Development Environment

### Option 1: Container-Based Development

Container-based development provides consistency and isolation.

#### Prerequisites

- Podman installed ([installation guide](https://podman.io/getting-started/installation))
- Podman Machine initialized (macOS/Windows):

  ```bash
  podman machine init
  podman machine start
  ```

#### Building the Development Image

```bash
podman build -t rhdh-dynamic-plugin-factory:dev .
```

#### Testing Your Changes

Run the factory with your local build:

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./config:/config:z \
  -v ./source:/source:z \
  -v ./outputs:/outputs:z \
  rhdh-dynamic-plugin-factory:dev \
  --workspace-path workspaces/todo \
  --no-push-images
```

Follow instructions in the main [Usage Docs](./README.md) for container usage and replace image with your locally built image.

### Option 2: Local Development Setup

#### Requirements

- **Python**: 3.8 or higher
- **Node.js**: 22 or higher (version specified in `default.env`)
- **Corepack**: To configure the yarn package managers on a project to project basis
- **Git**: For cloning repositories
- **Buildah**: Required for building and pushing container images
  - Linux: `dnf install buildah` or `apt install buildah`
  - macOS: Not directly supported (use Podman containers)
  - Windows: Not directly supported (use Podman containers)

#### Virtual Environment Setup

Create and activate a Python virtual environment:

```bash
python -m venv venv
source venv/bin/activate
```

#### Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt -r requirements.dev.txt
```

#### Environment Configuration

The `default.env` file contains default settings:

```bash
# View current settings
cat default.env

# Create a custom .env file (optional)
cp default.env .env
```

#### Verify Setup

Test that the CLI works:

```bash
python -m src.rhdh_dynamic_plugin_factory --help
```

### Local Execution Examples

Once you have the local environment set up, you can run the factory directly with Python.

#### Build plugins and save outputs locally

```bash
python -m src.rhdh_dynamic_plugin_factory \
  --config-dir ./config \
  --workspace-path workspaces/todo \
  --output-dir ./outputs
```

#### Build and push to registry

Create a `./config/.env` file with your registry credentials:

```bash
REGISTRY_URL=quay.io
REGISTRY_USERNAME=myuser
REGISTRY_PASSWORD=mytoken
REGISTRY_NAMESPACE=mynamespace
```

Then run:

```bash
python -m src.rhdh_dynamic_plugin_factory \
  --config-dir ./config \
  --workspace-path workspaces/announcements \
  --push-images
```

The factory will automatically read the registry credentials from `./config/.env`.

#### Using a local repository (skip cloning)

```bash
python -m src.rhdh_dynamic_plugin_factory \
  --config-dir ./config \
  --repo-path ./source \
  --workspace-path . \
  --output-dir ./outputs \
  --use-local
```

## Project Structure

```bash
rhdh-dynamic-plugin-factory/
├── src/rhdh_dynamic_plugin_factory/
│   ├── __init__.py              # Package initialization
│   ├── __main__.py              # Package entry point
│   ├── cli.py                   # CLI implementation and argument parsing
│   ├── config.py                # Configuration classes and validation
│   ├── logger.py                # Logging setup and utilities
│   └── utils.py                 # Utility functions
├── scripts/
│   ├── export-workspace.sh      # Plugin export script (called by CLI)
│   └── override-sources.sh      # Patch/overlay application script
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Pytest fixtures and configuration
│   ├── test_config.py           # Configuration tests
│   ├── test_plugin_list_config.py  # Plugin list parsing tests
│   └── test_source_config.py    # Source configuration tests
├── examples/                    # Example configuration sets
│   ├── example-config-todo/
│   ├── example-config-gitlab/
│   └── example-config-aws-ecs/
├── .cursor/rules/               # Development guidelines
│   ├── commit-standards.mdc
│   ├── documentation-standards.mdc
│   ├── planning-process.mdc
│   ├── python-code-quality.mdc
│   └── shell-code-quality.mdc
├── default.env                  # Default environment settings
├── Dockerfile                   # Container image definition
├── requirements.txt             # Python runtime dependencies
├── requirements.dev.txt         # Python development dependencies
├── pytest.ini                   # Pytest configuration
└── README.md                    # User documentation
```

### Key Components

- **`cli.py`**: Handles command-line arguments, orchestrates the build process
- **`config.py`**: Loads and validates configuration from files and environment
- **`logger.py`**: Configures structured logging with color output
- **`utils.py`**: Helper functions for file operations, subprocess execution
- **`export-workspace.sh`**: Shell script that calls the RHDH CLI to export plugins
- **`override-sources.sh`**: Applies patches and overlays to source code

## Running Tests

The project uses pytest for testing.

### Run All Tests

```bash
pytest tests/
```

### Run Tests with Verbose Output

```bash
pytest tests/ -v
```

### Run Tests for a Specific Module

```bash
pytest tests/test_config.py -v
```

### Run a Specific Test Class or Method

```bash
# Run a specific test class
pytest tests/test_config.py::TestPluginFactoryConfigLoadFromEnv -v

# Run a specific test method
pytest tests/test_config.py::TestPluginFactoryConfigLoadFromEnv::test_load_from_env_valid_configuration -v
```

### Run with Coverage Reporting

```bash
pytest tests/ --cov=src/rhdh_dynamic_plugin_factory --cov-report=term-missing
```

This will show which lines of code are not covered by tests.

### Run Tests in Watch Mode

For active development, you can use pytest-watch:

```bash
pip install pytest-watch
ptw tests/
```

### Writing Tests

When adding new features:

1. **Write tests first** (Test-Driven Development)
2. **Test both success and failure cases**
3. **Use descriptive test names**: `test_<what>_<condition>_<expected>`
4. **Use fixtures** from `conftest.py` for common setup
5. **Mock external dependencies** (file system, subprocess calls)

Example test structure:

```python
def test_config_loads_from_valid_file(tmp_path):
    """Test that configuration loads successfully from a valid file."""
    # Arrange
    config_file = tmp_path / "config.json"
    config_file.write_text('{"key": "value"}')
    
    # Act
    result = load_config(config_file)
    
    # Assert
    assert result["key"] == "value"
```

## Development Workflow

### 1. Create a Feature Branch

```bash
# Update your main branch
git checkout main
git pull upstream main

# Create a new feature branch
git checkout -b feature/my-new-feature
```

### 2. Make Your Changes

- Write code following the [Code Quality Standards](#code-quality-standards)
- Add or update tests
- Update documentation if needed

### 3. Run Tests and Linters

```bash
# Run tests
pytest tests/

# Check code coverage
pytest tests/ --cov=src/rhdh_dynamic_plugin_factory --cov-report=term-missing

# Check types (if using mypy)
mypy src/
```

### 4. Commit Your Changes

Follow the [Conventional Commits](https://www.conventionalcommits.org/) format:

```bash
git add .
git commit -m "feat: add support for custom plugin configurations"
```

Commit types:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Test additions or changes
- `refactor:` Code refactoring
- `chore:` Maintenance tasks
- `ci:` CI/CD changes

See `.cursor/rules/commit-standards.mdc` for detailed commit guidelines.

### 5. Push to Your Fork

```bash
git push origin feature/my-new-feature
```

### 6. Create a Pull Request

1. Go to your fork on GitHub
2. Click "Pull Request"
3. Select your branch and provide a clear description:
   - What changes were made
   - Why they were needed
   - Any breaking changes
   - Related issues

## Code Quality Standards

### Python Code Quality

Follow the guidelines in `.cursor/rules/python-code-quality.mdc`:

- **PEP 8**: Follow Python style guidelines
- **Type Hints**: Use type annotations for function signatures
- **Docstrings**: Use Google-style docstrings for all public functions/classes
- **Error Handling**: Use specific exception types, provide helpful error messages
- **Imports**: Group and sort imports (stdlib, third-party, local)

Example:

```python
def process_config(config_path: Path, validate: bool = True) -> Dict[str, Any]:
    """Process and validate a configuration file.
    
    Args:
        config_path: Path to the configuration file.
        validate: Whether to validate the configuration.
        
    Returns:
        Dictionary containing the processed configuration.
        
    Raises:
        FileNotFoundError: If the configuration file doesn't exist.
        ValueError: If the configuration is invalid.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    # Implementation here
    pass
```

### Shell Script Quality

Follow the guidelines in `.cursor/rules/shell-code-quality.mdc`:

- Follow Google Shell Style Guide
- Use `#!/usr/bin/env bash` shebang
- Enable strict mode: `set -euo pipefail`
- Quote all variables
- Use functions for reusable logic
- Add comments for complex operations

### Documentation Standards

Follow the guidelines in `.cursor/rules/documentation-standards.mdc`:

- Use Google-style docstrings
- Keep documentation up-to-date with code changes
- Include examples in docstrings when helpful
- Update README.md for user-facing changes
- Add comments for complex logic

## Submitting Changes

### Pull Request Checklist

Before submitting:

- [ ] Tests pass locally
- [ ] Code follows style guidelines
- [ ] Documentation is updated
- [ ] Commit messages follow conventional format
- [ ] No merge conflicts with main branch
- [ ] Changes are in a feature branch (not main)

### Review Process

1. Maintainers will review your PR
2. Address any feedback or requested changes
3. Once approved, a maintainer will merge your PR

### After Your PR is Merged

```bash
# Update your local repository
git checkout main
git pull upstream main

# Delete your feature branch (optional)
git branch -d feature/my-new-feature
```

## Getting Help

- **Issues**: Search existing [GitHub Issues](https://github.com/redhat-developer/rhdh-dynamic-plugin-factory/issues) or create a new one
- **Discussions**: Join the conversation in [GitHub Discussions](https://github.com/redhat-developer/rhdh-dynamic-plugin-factory/discussions)
- **Documentation**: Check the [README.md](./README.md) and example configurations

## License

By contributing to this project, you agree that your contributions will be licensed under the same license as the project (see [LICENSE](./LICENSE) file).

## Code of Conduct

This project follows a Code of Conduct to ensure an inclusive and welcoming environment for all contributors. Please be respectful and professional in all interactions.

Thank you for contributing to RHDH Dynamic Plugin Factory!
