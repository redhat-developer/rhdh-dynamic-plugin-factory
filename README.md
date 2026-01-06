# RHDH Dynamic Plugin Factory

A comprehensive tool for building and exporting dynamic plugins for Red Hat Developer Hub (RHDH) from Backstage plugin source code.

## Table of Contents

- [RHDH Dynamic Plugin Factory](#rhdh-dynamic-plugin-factory)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [Key Terminology](#key-terminology)
    - [Backstage Workspace Structure](#backstage-workspace-structure)
    - [`--workspace-path` vs `--repo-path`](#--workspace-path-vs---repo-path)
  - [Installation](#installation)
    - [Using Pre-built Container Images](#using-pre-built-container-images)
    - [Container Requirements](#container-requirements)
    - [Basic Container Usage](#basic-container-usage)
    - [Running Locally Without Containers](#running-locally-without-containers)
  - [Configuration](#configuration)
    - [Directory Structure](#directory-structure)
    - [Configuration Files](#configuration-files)
      - [1. `default.env` (Provided)](#1-defaultenv-provided)
      - [2. `config/source.json` (Required for remote repositories)](#2-configsourcejson-required-for-remote-repositories)
      - [3. `config/plugins-list.yaml` (Required)](#3-configplugins-listyaml-required)
      - [4. `config/.env` (Optional)](#4-configenv-optional)
    - [Patches and Overlays](#patches-and-overlays)
      - [Patches Directory (`config/patches/`)](#patches-directory-configpatches)
      - [Overlays Directory (`config/<path-to-plugin-root-with-respect-to-workspace>/overlays/`)](#overlays-directory-configpath-to-plugin-root-with-respect-to-workspaceoverlays)
  - [Usage](#usage)
    - [Command-Line Options](#command-line-options)
    - [Understanding Volume Mounts](#understanding-volume-mounts)
    - [Container Usage Examples](#container-usage-examples)
      - [Minimal example (no local files saved)](#minimal-example-no-local-files-saved)
      - [Build plugins and save outputs locally](#build-plugins-and-save-outputs-locally)
      - [Build and push to registry](#build-and-push-to-registry)
      - [Using a local repository (skip cloning)](#using-a-local-repository-skip-cloning)
  - [Output](#output)
    - [Build Artifacts](#build-artifacts)
    - [Container Images](#container-images)
  - [Examples](#examples)
    - [Quick Example: TODO Workspace](#quick-example-todo-workspace)
  - [Local Development \& Contributing](#local-development--contributing)
  - [Resources](#resources)

## Overview

The RHDH Plugin Factory automates the process of converting Backstage plugins into RHDH dynamic plugins. It provides:

- **Source Repository Management**: Clone and checkout plugin source repositories
- **Patch & Overlay System**: Apply custom modifications to plugin source code before exporting
- **Dependency Management**: Automated yarn installation with TypeScript compilation
- **Dynamic Plugin Packaging**: Build, export and package plugins using the RHDH CLI
- **Container Image Publishing**: Optionally push to container registries (Quay, OpenShift, etc.)

## Key Terminology

A backstage plugin workspace is a [yarn workspace](https://yarnpkg.com/features/workspaces) within a Backstage repository that contains plugins to export. Note that there are cases where the backstage repository itself is the plugin workspace.

### Backstage Workspace Structure

A Backstage plugin workspace is a yarn workspace (either a root workspace or nested within a monorepo) that typically follows this structure:

```text
<backstage-workspace>/
├── package.json          # Workspace root package.json (defines the yarn workspace)
├── plugins/              # Contains the plugins to export as dynamic plugins
│   ├── my-plugin/
│   └── my-plugin-backend/
└── packages/             # Optional: Contains frontend/backend apps for local development
    ├── app/              # (Usually unused for dynamic plugin export)
    └── backend/
```

Examples:

- In the [Backstage Community Plugins](https://github.com/backstage/community-plugins) repository, each directory under `workspaces/` is a Backstage workspace (e.g., `workspaces/todo`, `workspaces/announcements`)
- A standalone Backstage repository may have its workspace be the repository itself such as in the case of the [PagerDuty plugins](https://github.com/PagerDuty/backstage-plugins)

### `--workspace-path` vs `--repo-path`

These two options work together to locate your plugin workspace:

- `--repo-path`: Where the backstage repository containing the plugin workspace is located (the cloned repository destination or your local repo)
  - Note: this is automatically resolved to `/source` if not provided
  - *Most* of the time this is NOT the same as the plugin workspace containing the plugins you want to export, the exception is when the backstage plugin repository itself is a standalone plugin workspace.
- `--workspace-path`: The relative path from the repository root to the workspace containing your plugins

Ex: To build plugins from the TODO workspace in the community-plugins repository:

```text
--repo-path /source                       # Repository cloned to the /source directory
--workspace-path workspaces/todo          # Workspace is at /source/workspaces/todo
```

The factory will then search for plugins defined in the `plugins-list.yaml` file with respect to the workspace `<repo-path>/<workspace-path>/`

## Installation

The RHDH Plugin Factory is distributed as a pre-built container image. It is recommended to use Podman for all platforms.

### Using Pre-built Container Images

Pre-built container images are published to `quay.io/rhdh-community/dynamic-plugins-factory` with tags corresponding to the version of RHDH they were designed for:

```bash
# Pull the latest version
podman pull quay.io/rhdh-community/dynamic-plugins-factory:latest
```

```bash
# Or pull a specific RHDH version
podman pull quay.io/rhdh-community/dynamic-plugins-factory:1.8
```

### Container Requirements

The container requires specific capabilities and device access for building dynamic plugins:

- **Volume Mounts**: Mount your configuration, plugin repository, and/or output directory to the `/config`, `/source` and `/outputs` directories respectively
- **Device Access**: Mount `/dev/fuse` for filesystem operations (required for buildah)
- **SELinux Context**: Use `:z` flag for volume mounts on SELinux-enabled systems (RHEL/Fedora/CentOS)

The `--device /dev/fuse` flag passes the FUSE device from the Linux environment (native on Linux, or from Podman Machine's VM on macOS/Windows) to the container, enabling buildah operations.

### Basic Container Usage

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./config:/config:z \
  -v ./source:/source:z \
  -v ./outputs:/outputs:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
  --workspace-path <path-to-workspace>
```

**Note:** The `--config-dir`, `--repo-path`, and `--output-dir` options use default values of `/config`, `/source`, and `/outputs` respectively, which map to your local directories through volume mounts.

### Running Locally Without Containers

For local execution without containers, see [CONTRIBUTING.md](./CONTRIBUTING.md).

## Configuration

### Directory Structure

The factory expects the following directory structure:

```bash
./
├── config/                                   # Configuration directory (Can be set with --config-dir)
│   ├── .env                                  # Optional (if not pushing): Override environment variables + provide registry credentials
│   ├── source.json                           # Source repository configuration
│   ├── plugins-list.yaml                     # List of plugins to build
│   ├── patches/                              # Optional: Patch files to apply
│   └── <path-to-plugin-in-workspace>/overlays/   # Optional: Files to overlay on plugin source
├── source/                                   # Source code location (Can be set with --repo-path)
└── outputs/                                  # Build output directory (Can be set with --output-dir)
```

Note: `source/` in this case refers to the default source code location if not provided by `--repo-path` and is not to be mistaken with the workspace containing the plugins to export. Refer to [Key Terminology](#--workspace-path-vs---repo-path) for more details.

### Configuration Files

#### 1. `default.env` (Provided)

This file contains required version settings and defaults for RHDH CLI:

```bash
# Tooling versions
RHDH_CLI_VERSION="1.8.0"
```

#### 2. `config/source.json` (Required for remote repositories)

Defines the source repository to clone:

```json
{
  "repo": "https://github.com/backstage/community-plugins",
  "repo-ref": "main",
}
```

**Fields:**

- `repo`: Repository URL (HTTPS or SSH)
- `repo-ref`: Git reference (branch, tag, or commit SHA)

#### 3. `config/plugins-list.yaml` (Required)

A list of plugin paths (with respect to root of workspace) to plugins to build along with optional build arguments:

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

Alternatively,  you can pass the `.env` file directly through podman using the `--env-file` argument instead of placing a `.env` file in the config directory:

```bash
podman run --rm -it \
  --device /dev/fuse \
  --env-file ./my-env-file.env \
  -v ./config:/config:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
  --workspace-path workspaces/todo \
  --push-images
```

This approach keeps your credentials separate from the config directory and can be useful for CI/CD pipelines or when you want to reuse the same environment file across different configurations.

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

See the [AWS ECS plugin example config](./examples/example-config-aws-ecs/README.md) for an example on how patches are applied

#### Overlays Directory (`config/<path-to-plugin-root-with-respect-to-workspace>/overlays/`)

Place files that should be copied over the source code:

```bash
config/
└── plugins/
    └── my-plugin/
        └── overlay/
            └── custom-config.ts
```

See the [TODO plugin example config](./examples/example-config-todo/README.md) and [Gitlab plugin example config](./examples/example-config-gitlab/README.md) for an example on using overlays.

## Usage

### Command-Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `--config-dir` | `/config` | Configuration directory containing `source.json`, `plugins-list.yaml`, patches, and overlays |
| `--repo-path` | `/source` | Path where plugin source code will be cloned/stored |
| `--workspace-path` | (required) | Path to the workspace from repository root (e.g., `workspaces/todo`) |
| `--output-dir` | `/outputs` | Directory for build artifacts (`.tgz` files and container images) |
| `--push-images` / `--no-push-images` | `--no-push-images` | Whether to push container images to registry. Defaults to not pushing if no argument is provided |
| `--use-local` | `false` | Use local repository instead of cloning from source.json |
| `--log-level` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `--verbose` | `false` | Show verbose output with file and line numbers |

### Understanding Volume Mounts

When using the container, you can mount directories based on your needs:

| Volume Mount | Required? | Purpose | When to Use |
|--------------|-----------|---------|-------------|
| `-v ./config:/config:z` | **Required** | Configuration files | Always - contains your `plugins-list.yaml`, `source.json`, patches, and overlays |
| `-v ./source:/source:z` | Optional | Source code location | Only if using `--use-local` OR if you want to preserve/inspect the cloned/patched remote repository |
| `-v ./outputs:/outputs:z` | Optional | Stores bBuild artifacts | Only if you want the output `.tgz` files saved locally (otherwise they stay in the container) |

**Important**: These volume mount paths (`/config`, `/source`, `/outputs`) correspond to the default values of `--config-dir`, `--repo-path`, and `--output-dir`. If you override these arguments with custom paths, adjust your volume mounts accordingly.

**Note**: Use the `:z` flag for systems with SELinux enabled (RHEL/Fedora/CentOS). On other systems, you can omit it.

### Container Usage Examples

The following examples demonstrate common use cases with the container image. All examples assume you have the necessary configuration files (`source.json`, `plugins-list.yaml`, and optionally patches/overlays) in your configuration directory. See the [Configuration](#configuration) section for details.

#### Minimal example (no local files saved)

This minimal example builds the TODO plugins without saving the workspace or output files locally:

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./examples/example-config-todo:/config:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
  --workspace-path workspaces/todo
```

This will clone the repository, build the plugins, and NOT push the result to a remote repository.

#### Build plugins and save outputs locally

This example builds plugins and saves the `.tgz` files to your local `./outputs/` directory:

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./config:/config:z \
  -v ./outputs:/outputs:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
  --workspace-path workspaces/todo
```

This will clone the repository specified in `./config/source.json`, build the plugins listed in `./config/plugins-list.yaml`, and save the `.tgz` files to `./outputs/`.

#### Build and push to registry

This example builds plugins and pushes them directly to a container registry (no local `.tgz` files saved).

First, create a `./config/.env` file with your registry credentials:

```bash
REGISTRY_URL=quay.io
REGISTRY_USERNAME=myuser
REGISTRY_PASSWORD=mytoken
REGISTRY_NAMESPACE=mynamespace
```

Then run the factory with `--push-images`:

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./config:/config:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
  --workspace-path workspaces/announcements \
  --push-images
```

The factory will automatically read the load the environmental variables from `./config/.env`.

#### Using a local repository (skip cloning)

If you already have the source code locally, use the `--use-local` flag and mount your existing workspace:

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./config:/config:z \
  -v /path/to/existing-source-code:/source:z \
  -v ./outputs:/outputs:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
  --workspace-path path/to/workspace \
  --use-local
```

**Note:** When using `--use-local`, patches and overlays will still be applied to your local repository. Make sure you have backups or are using version control.

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

NOTE: If the repository name (ex: plugin-name-dynamic) in the namespace specified by `REGISTRY_NAMESPACE` does not exist, the dynamic plugin factory will create a new registry. Depending on the registry specified by `REGISTRY_URL`, the newly created repository may be private. This will be the case for `quay.io`.

## Examples

The `examples` directory contains ready-to-use configuration examples demonstrating different use cases and features.

| Example | Description | Details |
|---------|-------------|---------|
| **TODO** | Basic workspace with custom scalprum-config | [View README](./examples/example-config-todo/) |
| **GitLab** | Overlays for non Backstage Community Plugins workspace format | [View README](./examples/example-config-gitlab/) |
| **AWS ECS** | Patches and embed packages in plugins-list.yaml | [View README](./examples/example-config-aws-ecs/) |

### Quick Example: TODO Workspace

Build the TODO plugin from Backstage community plugins:

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./examples/example-config-todo:/config:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
  --workspace-path workspaces/todo \
  --no-push-images
```

This example includes:

- Custom `scalprum-config.json` configuration
- A source repository using the standard Backstage Community Plugins workspace format
- Both frontend and backend plugins in the workspace

For detailed instructions, package verification steps, and additional examples, see the individual README files linked in the table above.

## Local Development & Contributing

For users who want to run the factory locally without containers or contribute to the project, see [CONTRIBUTING.md](./CONTRIBUTING.md).

## Resources

To learn more about how dynamic plugins work refer to the [dynamic plugins documentation](https://github.com/redhat-developer/rhdh/blob/main/docs/dynamic-plugins/index.md) in the RHDH Repository
