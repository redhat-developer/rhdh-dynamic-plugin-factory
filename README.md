# RHDH Dynamic Plugin Factory

A comprehensive tool for building and exporting dynamic plugins for Red Hat Developer Hub (RHDH) from Backstage plugin source code.

## Overview

The RHDH Plugin Factory automates the process of converting Backstage plugins into RHDH dynamic plugins. It provides:

- **Source Repository Management**: Clone and checkout plugin source repositories
- **Patch & Overlay System**: Apply custom modifications to plugin source code before exporting
- **Dependency Management**: Automated yarn installation with TypeScript compilation
- **Dynamic Plugin Packaging**: Build, export and package plugins using the RHDH CLI
- **Container Image Publishing**: Optionally push to container registries (Quay, OpenShift, etc.)

## Prerequisites

### Local Development

- **Python**: 3.8 or higher
- **Node.js**: 22 or higher (specified in `default.env`)
- **Yarn**: Latest version via Corepack
- **Git**
- **Buildah**: For building and pushing container images (if using `--push-images`)

## Installation

### Local Setup

1. **Clone the repository**:

   ```bash
   git clone https://github.com/redhat-developer/rhdh-dynamic-plugin-factory
   cd rhdh-dynamic-plugin-factory
   ```

2. **Install Python dependencies**:

   ```bash
   pip install -r requirements.txt -r requirements.dev.txt
   ```

3. **Set up custom environment variables**:

   ```bash
   # The default.env file contains required version settings
   # Copy and customize if needed
   cp default.env .env
   ```

## Configuration

### Directory Structure

The factory expects the following directory structure:

```bash
./
├── config/                                   # Configuration directory (set with --config-dir)
│   ├── .env                                  # Optional: Override environment variables
│   ├── source.json                           # Source repository configuration
│   ├── plugins-list.yaml                     # List of plugins to build
│   ├── patches/                              # Optional: Patch files to apply
│   └── <path-to-plugin-in-workspace>/overlays/   # Optional: Files to overlay on plugin source
├── workspace/                                # Source code location (set with --repo-path)
└── outputs/                                  # Build output directory (set with --output-dir)
```

### Configuration Files

#### 1. `default.env` (Provided)

This file contains required version settings and defaults for Node, Yarn and the RHDH CLI:

```bash
# Node.js and tooling versions
NODE_VERSION="22"
YARN_VERSION="3.8.7"
RHDH_CLI_VERSION="1.7.2"
```

#### 2. `config/source.json` (Required for remote repositories)

Defines the source repository to clone:

```json
{
  "repo": "https://github.com/backstage/community-plugins",
  "repo-ref": "main",
  "repo-backstage-version": "1.39.1",
  "repo-flat": false
}
```

**Fields:**

- `repo`: Repository URL (HTTPS or SSH)
- `repo-ref`: Git reference (branch, tag, or commit SHA)
- `repo-backstage-version`: Backstage version used by the source repository
- `repo-flat`: Whether the repository has a flat structure (default: `false`)

#### 3. `config/plugins-list.yaml` (Required)

Lists plugins to build with optional build arguments:

```yaml
# Simple plugins (no additional arguments)
plugins/todo:
plugins/todo-backend:
```

```yaml
# Plugins with embed packages
plugins/scaffolder-backend: --embed-package @backstage/plugin-scaffolder-backend-module-github
```

```yaml
# Multiple embed packages
plugins/search-backend: |
  --embed-package @backstage/plugin-search-backend-module-catalog
  --embed-package @backstage/plugin-search-backend-module-techdocs
```

#### 4. `config/.env` (Optional)

Override default settings to publish to a remote image registry:

```bash
# Registry configuration (required only with --push-images)
REGISTRY_URL=quay.io
REGISTRY_USERNAME=your_username
REGISTRY_PASSWORD=your_password
REGISTRY_NAMESPACE=your_namespace
REGISTRY_INSECURE=false

# Logging
LOG_LEVEL=DEBUG
```

`LOG_LEVEL` can be set to one of `DEBUG`, `INFO` (default), `WARN`, `ERROR`, or `CRITICAL`

### Patches and Overlays

#### Patches Directory (`config/patches/`)

Place `.patch` files to apply modifications to the source code:

```bash
config/
└── patches/
    └── 001-fix-dependency.patch
```

Patches are applied using the `override-sources.sh` script before building.

#### Overlays Directory (`config/<path-to-plugin-root-with-respect-to-workspace>/overlays/`)

Place files that should be copied over the source code:

```bash
config/
  └── plugins/
      └── my-plugin/
          └── overlay/
              └── custom-config.ts
```

## Usage

### Basic Command Structure

```bash
python -m rhdh_dynamic_plugin_factory.cli [OPTIONS]
```

### Command-Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--config-dir` | `./config` | Configuration directory containing `source.json`, `plugins-list.yaml`, patches, and overlays |
| `--repo-path` | `./workspace` | Path where plugin source code will be cloned/stored |
| `--workspace-path` | (required) | Path to the workspace from repository root (e.g., `workspaces/todo`) |
| `--output-dir` | `./outputs` | Directory for build artifacts (`.tgz` files and container images) |
| `--push-images` / `--no-push-images` | `true` | Whether to push container images to registry |
| `--log-level` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `--verbose` | `false` | Show verbose output with file and line numbers |

### Example Usage (Local)

#### Locally build plugins from backstage/community-plugins (todo workspace)

Assumes our cwd is the root of this repository

```bash
python -m rhdh_dynamic_plugin_factory.cli \
  --config-dir ./config \
  --repo-path ./workspace \
  --workspace-path workspaces/todo \
  --output-dir ./outputs \
  --no-push-images \
  --log-level DEBUG
```

This command will:

1. Load configurations from `./config/`
2. Clone the repository specified in `config/source.json` to `./workspace`
3. Apply patches and overlays from `./config/patches/` and `./config/<plugin-path>/overlay/`
4. Install dependencies in `./workspace/workspaces/todo`
5. Build plugins listed in `config/plugins-list.yaml`
6. Export artifacts to `./outputs/`
7. Skip pushing to registry (`--no-push-images`)

#### Build and push to registry

Currently only supports quay.io

```bash
# Set registry credentials in config/.env or environment
export REGISTRY_URL=quay.io
export REGISTRY_USERNAME=myuser
export REGISTRY_PASSWORD=mytoken
export REGISTRY_NAMESPACE=mynamespace

python -m rhdh_dynamic_plugin_factory.cli \
  --config-dir ./config \
  --repo-path ./workspace \
  --workspace-path workspaces/announcements \
  --output-dir ./outputs \
  --push-images
```

#### Using a local repository (skip cloning)

TODO: Add CLI option to set priority for this option when `source.json` exists

If you already have the source code locally:

```bash
# Remove or don't create source.json in config/
# Ensure workspace already exists at --repo-path

python -m rhdh_dynamic_plugin_factory.cli \
  --config-dir ./config \
  --repo-path ./existing-workspace \
  --workspace-path . \
  --output-dir ./outputs \
  --no-push-images
```

## Output

### Build Artifacts

The factory also produces the following outputs in the directory specified by `--output-dir`:

```bash
outputs/
├── plugin-name-dynamic-1.0.0.tgz           # Plugin tarball
├── plugin-name-dynamic-1.0.0.tgz.integrity # Integrity checksum
└── ...
```

### Container Images

When `--push-images` is enabled, images are tagged as:

```bash
${REGISTRY_URL}/${REGISTRY_NAMESPACE}/plugin-name-dynamic:1.0.0
```

## Examples

See the `examples` directory for complete configuration examples:

- **TODO Workspace**: Located at [`examples/example-config-todo`](./examples/example-config-todo/)
  - This example contains a custom `scalprum-config.json` file and uses the standard backstage community plugins (BCP) workspace format
  - Example Command to locally export:

    ```bash
    python src/rhdh_dynamic_plugin_factory --config-dir ./examples/example-config-todo --repo-path ./workspace --no-push-images --workspace-path workspaces/todo --output-dir ./outputs
    ```

- **Gitlab Workspace**: Located at [`examples/example-config-gitlab`](./examples/example-config-gitlab/)
  - This example contains a overlays used to override entire files contained in the gitlab workspace in <https://github.com/immobiliare/backstage-plugin-gitlab> which does not use the standard BCP workspace format.
  - In the example command, we will need to modify `--workspace-path` to point to the root of the workspace which in this case is `.`:
  
    ```bash
    python src/rhdh_dynamic_plugin_factory --config-dir ./config --repo-path ./workspace --no-push-images --workspace-path . --output-dir ./outputs
    ```

- **AWS ECS Workspace**: Located at [`examples/example-config-aws-ecs`](./examples/example-config-aws-ecs/)
  - This example contains a `patches` folder used for small patches as well as custom export arguments for the `ecs` backend plugin in the [`plugins-list.yaml`](./examples/example-config-aws-ecs/plugins-list.yaml) to embed additional packages during the dynamic plugin export
  - This workspace also does not use the standard BCP workspace format so we will have a similar command as above:

    ```bash
    python src/rhdh_dynamic_plugin_factory --config-dir ./config --repo-path ./workspace --no-push-images --workspace-path . --output-dir ./outputs
    ```

## Development

### Project Structure

```bash
rhdh-dynamic-plugin-factory/
├── src/rhdh_dynamic_plugin_factory/
│   ├── __main__.py              # Package entry point
│   ├── cli.py                   # CLI implementation
│   ├── config.py                # Configuration classes
│   └── logger.py                # Logging setup
├── scripts/
│   ├── export-workspace.sh      # Plugin export script
│   └── override-sources.sh      # Patch/overlay script
├── examples/                    # Example configuration sets
├── default.env                  # Default environment settings
├── requirements.txt             # Python dependencies
└── requirements.dev.txt         # Development dependencies
```

### Running Tests

TODO: Add Unit Tests

## Resources

TODO: Add Further Readings
