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
- **Git**: For cloning and checking out remote git repositories
- **Buildah**: For building and pushing container images (if using `--push-images`)

## Installation

You can use the RHDH Plugin Factory either locally or via a container image.

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

### Container Image Setup

#### Building the Image

Build the container image using Podman or Docker. Change `rhdh-dynamic-plugin-factory:latest` to your own image:

```bash
podman build -t rhdh-dynamic-plugin-factory:latest .
```

Or with Docker:

```bash
docker build -t rhdh-dynamic-plugin-factory:latest .
```

#### Container Requirements

The container requires specific capabilities and device access for building dynamic plugins:

- **Volume Mounts**: Mount your configuration, workspace, and output directories to the `/config`, `/workspace` and `/outputs` directories respectively
- **Device Access**: Mount `/dev/fuse` for filesystem operations
- **SELinux Context**: Use `:z` flag for volume mounts on SELinux-enabled systems when using `podman`

#### Basic Container Usage

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./config:/config:z \
  -v ./workspace:/workspace:z \
  -v ./outputs:/outputs:z \
  rhdh-dynamic-plugin-factory:latest \
```

**Key Differences from Local Usage:**

- Paths for `--config-dir`, `--repo-path`, and `--output-dir` don't need to be defined since they use the default values of `/config`, `/workspace` and `/outputs` respectively.
- Usage of volume mounts to map your local directories to these container paths
- The `--device /dev/fuse` flag is required for buildah operations inside the container
- Use `:z` or `:Z` SELinux labels when running on RHEL/Fedora/CentOS systems

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
WORKSPACE_PATH=<path_to_workspace_with_respect_to_plugin_repo_root>
```

`LOG_LEVEL` can be set to one of `DEBUG`, `INFO` (default), `WARN`, `ERROR`, or `CRITICAL`

`WORKSPACE_PATH` can be set in lieu of the `--workspace-path` argument

### Patches and Overlays

> WARNING: This is a destructive operation
>
> Patches and overlays **modify files directly** in the `--repo-path` directory. These operations are **destructive** and will permanently change the repository contents.
>
> - When using `--use-local` with a local repository, patches and overlays WILL modify your local files
> - Consider using version control OR cloning a fresh copy of your repository if you need to preserve the original state

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
| `--config-dir` | `/config` | Configuration directory containing `source.json`, `plugins-list.yaml`, patches, and overlays |
| `--repo-path` | `/workspace` | Path where plugin source code will be cloned/stored |
| `--workspace-path` | (required) | Path to the workspace from repository root (e.g., `workspaces/todo`) |
| `--output-dir` | `/outputs` | Directory for build artifacts (`.tgz` files and container images) |
| `--push-images` / `--no-push-images` | `true` | Whether to push container images to registry. Defaults to not pushing if no argument is provided |
| `--use-local` | `false` | Use local repository instead of cloning from source.json |
| `--log-level` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `--verbose` | `false` | Show verbose output with file and line numbers |

### Example Usage

#### Build plugins from backstage/community-plugins (todo workspace)

**Local Execution:**

```bash
python -m rhdh_dynamic_plugin_factory.cli \
  --config-dir ./config \
  --repo-path ./workspace \
  --workspace-path workspaces/todo \
  --output-dir ./outputs \
  --no-push-images \
  --log-level DEBUG
```

**Container Execution:**

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./config:/config:z \
  -v ./workspace:/workspace:z \
  -v ./outputs:/outputs:z \
  -e LOG_LEVEL=DEBUG \
  rhdh-dynamic-plugin-factory:latest \
  --workspace-path workspaces/todo \
  --no-push-images
```

Both methods will:

1. Load configurations from the local `./config` directory
2. Clone the repository specified in `./config/source.json` to `./workspace`
3. Apply patches and overlays from `./config/patches/` and `./config/<plugin-path>/overlay/` to `./workspace`
4. Install dependencies in `./workspace/workspaces/todo`
5. Export and package plugins listed in `./config/plugins-list.yaml`
6. Output artifacts to the local `./outputs/` directory
7. Skip pushing to registry (`--no-push-images`)

#### Build and push to registry

**Local Execution:**

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

**Container Execution:**

```bash
# Pass registry credentials as environment variables
podman run --rm -it \
  --device /dev/fuse \
  -v ./config:/config:z \
  -v ./workspace:/workspace:z \
  -v ./outputs:/outputs:z \
  -e REGISTRY_URL=quay.io \
  -e REGISTRY_USERNAME=myuser \
  -e REGISTRY_PASSWORD=mytoken \
  -e REGISTRY_NAMESPACE=mynamespace \
  rhdh-dynamic-plugin-factory:latest \
  --workspace-path workspaces/announcements \
  --push-images
```

**Note:** For security, consider providing registry configurations through the `config/.env` file

```bash
# Using environment file
podman run --rm -it \
  --device /dev/fuse \
  -v ./config:/config:z \
  -v ./workspace:/workspace:z \
  -v ./outputs:/outputs:z \
  --env-file ./config/.env \
  rhdh-dynamic-plugin-factory:latest \
  --repo-path /workspace \
  --workspace-path workspaces/announcements \
  --output-dir /outputs \
  --push-images
```

#### Using a local repository (skip cloning)

If you already have the source code locally, use the `--use-local` flag to skip cloning from `source.json` AND/OR not include `source.json` in the config folder:

**Local Execution:**

```bash
# Ensure workspace already exists at --repo-path
# The --use-local flag will skip cloning even if source.json exists

python -m rhdh_dynamic_plugin_factory.cli \
  --config-dir ./config \
  --repo-path ./existing-workspace \
  --workspace-path . \
  --output-dir ./outputs \
  --use-local \
  --no-push-images
```

**Container Execution:**

```bash
# Mount your existing workspace directory
podman run --rm -it \
  --device /dev/fuse \
  -v ./config:/config:z \
  -v /path/to/existing-workspace:/workspace:z \
  -v ./outputs:/outputs:z \
  rhdh-dynamic-plugin-factory:latest \
  --config-dir /config \
  --workspace-path . \
  --use-local \
  --no-push-images
```

**Note:** When using `--use-local`, patches and overlays will still be applied to your local repository. Make sure you have backups or are using version control before running the tool with a local repository.

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

### TODO Workspace Example

Located at [`examples/example-config-todo`](./examples/example-config-todo/)

This example contains a custom `scalprum-config.json` file and uses the standard backstage community plugins (BCP) workspace format.
The process is very similar if you also want to include a custom `backstage.json` or `app-config.dynamic.yaml` file.

**Local Execution:**

```bash
python -m rhdh_dynamic_plugin_factory.cli \
  --config-dir ./examples/example-config-todo \
  --repo-path ./workspace \
  --workspace-path workspaces/todo \
  --output-dir ./outputs \
  --no-push-images
```

**Container Execution:**

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./examples/example-config-todo:/config:z \
  -v ./workspace:/workspace:z \
  -v ./outputs:/outputs:z \
  rhdh-dynamic-plugin-factory:latest \
  --workspace-path workspaces/todo \
  --no-push-images
```

### Gitlab Workspace Example

Located at [`examples/example-config-gitlab`](./examples/example-config-gitlab/)

This example contains overlays used to override entire files contained in the gitlab workspace at <https://github.com/immobiliare/backstage-plugin-gitlab> which does not use the standard BCP workspace format. The `--workspace-path` is set to `.` (root of repository).

**Local Execution:**

```bash
python -m rhdh_dynamic_plugin_factory.cli \
  --config-dir ./examples/example-config-gitlab \
  --repo-path ./workspace \
  --workspace-path . \
  --output-dir ./outputs \
```

**Container Execution:**

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./examples/example-config-gitlab:/config:z \
  -v ./workspace:/workspace:z \
  -v ./outputs:/outputs:z \
  rhdh-dynamic-plugin-factory:latest \
  --workspace-path . \
```

### AWS ECS Workspace Example

Located at [`examples/example-config-aws-ecs`](./examples/example-config-aws-ecs/)

This example contains a `patches` folder used for small patches as well as custom export arguments for the `ecs` backend plugin in the [`plugins-list.yaml`](./examples/example-config-aws-ecs/plugins-list.yaml) to embed additional packages during the dynamic plugin export. This workspace also does not use the standard BCP workspace format.

**Local Execution:**

```bash
python -m rhdh_dynamic_plugin_factory.cli \
  --config-dir ./examples/example-config-aws-ecs \
  --repo-path ./workspace \
  --workspace-path . \
  --output-dir ./outputs \
```

**Container Execution:**

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./examples/example-config-aws-ecs:/config:z \
  -v ./workspace:/workspace:z \
  -v ./outputs:/outputs:z \
  rhdh-dynamic-plugin-factory:latest \
  --repo-path /workspace \
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
