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
      - [Single-Workspace Layout](#single-workspace-layout)
      - [Multi-Workspace Layout](#multi-workspace-layout)
    - [Configuration Files](#configuration-files)
      - [1. `default.env` (Provided)](#1-defaultenv-provided)
      - [2. `config/source.json` (Required for remote repositories, unless using `--source-repo`)](#2-configsourcejson-required-for-remote-repositories-unless-using---source-repo)
      - [3. `config/plugins-list.yaml` (Optional -- auto-generated if absent)](#3-configplugins-listyaml-optional----auto-generated-if-absent)
      - [4. `config/.env` (Optional)](#4-configenv-optional)
    - [Plugin List Auto-Generation](#plugin-list-auto-generation)
      - [How Auto-Generation Works](#how-auto-generation-works)
      - [Build Argument Types](#build-argument-types)
      - [Using `--generate-build-args`](#using---generate-build-args)
    - [Patches and Overlays](#patches-and-overlays)
      - [Patches Directory (`config/patches/`)](#patches-directory-configpatches)
      - [Overlays Directory (`config/<path-to-plugin-root-with-respect-to-workspace>/overlays/`)](#overlays-directory-configpath-to-plugin-root-with-respect-to-workspaceoverlays)
  - [Usage](#usage)
    - [Command-Line Options](#command-line-options)
    - [Understanding Volume Mounts](#understanding-volume-mounts)
    - [Container Usage Examples](#container-usage-examples)
      - [Minimal example using `source.json`](#minimal-example-using-sourcejson)
      - [Minimal example using CLI args (no `source.json` needed)](#minimal-example-using-cli-args-no-sourcejson-needed)
      - [Build plugins and save outputs locally](#build-plugins-and-save-outputs-locally)
      - [Build and push to registry](#build-and-push-to-registry)
      - [Using a local repository (skip cloning)](#using-a-local-repository-skip-cloning)
    - [Multi-Workspace Mode](#multi-workspace-mode)
      - [How It Works](#how-it-works)
      - [Multi-Workspace CLI Restrictions](#multi-workspace-cli-restrictions)
      - [Multi-Workspace Example](#multi-workspace-example)
  - [Output](#output)
    - [Build Artifacts](#build-artifacts)
      - [Single Workspace Mode Outputs](#single-workspace-mode-outputs)
      - [Multi-Workspace Mode Outputs](#multi-workspace-mode-outputs)
    - [Container Images](#container-images)
  - [Examples](#examples)
    - [Quick Example: TODO Workspace](#quick-example-todo-workspace)
  - [Troubleshooting \& Common Issues](#troubleshooting--common-issues)
    - [Frontend Plugin Not Loading](#frontend-plugin-not-loading)
    - [Backend Module Not Loading (Missing Dependencies)](#backend-module-not-loading-missing-dependencies)
    - [Skopeo Fails During Plugin Installation](#skopeo-fails-during-plugin-installation)
    - [Quay.io Repository Publishing Issues](#quayio-repository-publishing-issues)
    - [Plugin Export Fails Entry Point Validation Check](#plugin-export-fails-entry-point-validation-check)
  - [Local Development \& Contributing](#local-development--contributing)
  - [Resources](#resources)

## Overview

The RHDH Plugin Factory automates the process of converting Backstage plugins into RHDH dynamic plugins. It provides:

- **Source Repository Management**: Clone and checkout plugin source repositories
- **Multi-Workspace Support**: Export plugins from multiple workspaces across different repositories in a single run
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

Or, without a `source.json`, specify the repository directly:

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./config:/config:z \
  -v ./source:/source:z \
  -v ./outputs:/outputs:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
  --source-repo <repository-url> \
  --workspace-path <path-to-workspace>
```

**Note:** The `--config-dir`, `--repo-path`, and `--output-dir` options use default values of `/config`, `/source`, and `/outputs` respectively, which map to your local directories through volume mounts.

### Running Locally Without Containers

For local execution without containers, see [CONTRIBUTING.md](./CONTRIBUTING.md).

## Configuration

### Directory Structure

The factory supports two directory layouts depending on whether you are building plugins from a single workspace or multiple workspaces.

#### Single-Workspace Layout

```bash
./
├── config/                                   # Configuration directory (--config-dir)
│   ├── .env                                  # Optional: Override environment variables + registry credentials
│   ├── source.json                           # Source repository configuration (not needed with --source-repo)
│   ├── plugins-list.yaml                     # List of plugins to build
│   ├── patches/                              # Optional: Patch files to apply
│   └── <path-to-plugin-in-workspace>/overlays/   # Optional: Files to overlay on plugin source
├── source/                                   # Source code location (--repo-path)
└── outputs/                                  # Build output directory (--output-dir)
```

#### Multi-Workspace Layout

When the config directory contains subdirectories with `source.json` files, the factory enters multi-workspace mode. Each subdirectory represents an independent workspace with similar directory layout as a single workspace directory:

```bash
./
├── config/                                   # Configuration directory (--config-dir)
│   ├── .env                                  # Optional: Root env, inherited by all workspaces
│   ├── todo/                                 # Workspace "todo"
│   │   ├── source.json                       # Required: repo, repo-ref, workspace-path
│   │   ├── plugins-list.yaml                 # Plugins to build for this workspace
│   │   ├── .env                              # Optional: Workspace-specific env overrides
│   │   └── patches/                          # Optional: Patches for this workspace
│   └── aws-ecs/                              # Workspace "aws-ecs"
│       ├── source.json
│       ├── plugins-list.yaml
│       └── patches/
├── source/                                   # Source code location (--repo-path)
│   ├── .clones/                              # Bare clones (one per unique repo URL)
│   │   ├── backstage-plugins-for-aws/        
│   │   └── community-plugins/               
│   ├── todo/                                 # Worktree for "todo" workspace
│   └── aws-ecs/                              # Worktree for "aws-ecs" workspace
└── outputs/                                  # Build output directory (--output-dir)
    ├── todo/                                 # Outputs for "todo" workspace
    └── aws-ecs/                              # Outputs for "aws-ecs" workspace
```

Note: `source/` in this case refers to the default source code location if not provided by `--repo-path` and is not to be mistaken with the workspace containing the plugins to export. Refer to [Key Terminology](#--workspace-path-vs---repo-path) for more details.

### Configuration Files

#### 1. `default.env` (Provided)

The version of the `rhdh-cli` being used can be set via the `RHDH_CLI_VERSION`, and is set to `latest` by default. Override it in your `.env` file to change the version if you need to use an older cli.

```bash
# Tooling versions
RHDH_CLI_VERSION="latest"
```

#### 2. `config/source.json` (Required for remote repositories, unless using `--source-repo`)

Defines the source repository to clone:

```json
{
  "repo": "https://github.com/backstage/community-plugins",
  "repo-ref": "main",
  "workspace-path": "workspaces/todo"
}
```

**Fields:**

- `repo`: Repository URL (HTTPS or SSH)
- `repo-ref` *(optional)*: Git reference (branch, tag, or commit SHA). When omitted, the repository's default branch is used.
- `workspace-path` *(optional)*: Path to the workspace from the repository root. Can be used instead of the `--workspace-path` CLI argument. The CLI argument takes precedence if both are provided.

> **Note:** `source.json` is not needed when using the `--source-repo` CLI argument, which provides an alternative way to specify the repository directly from the command line. See [Command-Line Options](#command-line-options) for details.

#### 3. `config/plugins-list.yaml` (Optional -- auto-generated if absent)

A YAML map of plugin paths (relative to the workspace root) to build, along with optional build arguments:

```yaml
# Simple plugins (no additional arguments)
plugins/todo:
plugins/todo-backend:
```

```yaml
# Plugins with build arguments
plugins/scaffolder-backend: --embed-package @backstage/plugin-scaffolder-backend-module-github
```

If this file is not provided, the factory will auto-generate it by scanning the **entire workspace** and attempting to export **all** discovered frontend/backend plugins. See [Plugin List Auto-Generation](#plugin-list-auto-generation) for details on how discovery and build-arg computation work, and how to use `--generate-build-args` to auto-compute build arguments for only specific plugins.

#### 4. `config/.env` (Optional)

Override default settings to publish to a remote image registry:

```bash
# Registry configuration (required only with --push-images)
REGISTRY_URL=quay.io
REGISTRY_USERNAME=your_username
REGISTRY_PASSWORD=your_password
REGISTRY_NAMESPACE=your_namespace
REGISTRY_INSECURE=false

```

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

WARNING: `--env-file` will NOT strip quotations from the environmental variables. This means `REGISTRY_URL="quay.io"` will literally resolve to `"quay.io"` instead of `quay.io` which will cause issues with image publishing.

### Plugin List Auto-Generation

If no `plugins-list.yaml` file is provided for a workspace, the factory will scan the **entire** workspace, discover **all** frontend/backend plugins, compute build arguments for backend plugins and generate a `plugins-list.yaml` with the required build arguments.

If you only want to take advantage of the build argument auto-generation for specific plugin(s), you can provide a barebones `plugins-list.yaml` containing your desired plugin(s) and the [`--generate-build-args` argument](#using---generate-build-args).

#### How Auto-Generation Works

When `plugins-list.yaml` is absent, the factory recursively scans the workspace for `package.json` files. A package is included if it has a `backstage.role` field set to one of:

- `frontend-plugin`
- `backend-plugin`
- `frontend-plugin-module`
- `backend-plugin-module`

For **frontend** plugins (and frontend plugin modules), no build arguments are needed.

For **backend** plugins (and backend plugin modules), the factory performs dependency analysis against the bundled RHDH host lockfile (`yarn.lock`) to determine which dependencies need additional build arguments during export.

#### Build Argument Types

The following build arguments can be automatically computed for backend plugins or manually defined:

| Argument                          | Purpose                                                                                                                                                                                                                                  |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--embed-package <pkg>`           | Bundles a dependency into the dynamic plugin. Applied to `@backstage/`* packages not provided by the RHDH host, and to non-`@backstage` packages that have transitive `@backstage/*` dependencies.                                       |
| `--shared-package !<pkg>`         | Marks an embedded `@backstage/*` package as unshared so the plugin uses its own bundled copy instead of the host's version.                                                                                                              |
| `--shared-package <pkg>`          | Marks a dependency to be exported as a peerDependency to use the package already present in the RHDH host.                                                                                                                               |
| `--suppress-native-package <pkg>` | Suppresses native Node.js modules that cannot be bundled. Detected by the presence of markers such as `bindings`, `prebuild`, `nan`, `node-gyp-build` in the package's dependencies, or `gypfile`/`binary` fields in its `package.json`. |
| `--allow-native-package <pkg>`    | Experimental argument to allow bundling of specified native module.                                                                                                                                                                      |

#### Using `--generate-build-args`

For larger workspaces that contain multiple plugins, using the auto generation feature will result in many unnecessary plugins being included in the `plugins-list.yaml`. To recompute build arguments for specific plugin(s), you will need to provide a barebones `plugins-list.yaml` with your desired plugin(s), and use the `--generate-build-args` argument.

```yaml
# Barebones plugins-list.yaml -- list only the plugins you want to export
plugins/todo:
plugins/todo-backend:
```

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./config:/config:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
  --workspace-path workspaces/todo \
  --generate-build-args
```

If the `--generate-build-args` argument is not provided when a `plugins-list.yaml` already exists, the factory will use it as-is and **will not** rescan or modify it.

> **Warning:** `--generate-build-args` overwrites the build arguments in your existing `plugins-list.yaml`. Make a backup if you have manually tuned values you want to preserve.

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

| Option                               | Default            | Description                                                                                                                                                                                                                                                  |
| ------------------------------------ | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `--config-dir`                       | `/config`          | Configuration directory containing `source.json`, `plugins-list.yaml`, patches, and overlays                                                                                                                                                                 |
| `--repo-path`                        | `/source`          | Path where plugin source code will be cloned/stored                                                                                                                                                                                                          |
| `--workspace-path`                   | *(see below)*      | Path to the workspace from repository root (e.g., `workspaces/todo`). Can also be set via `source.json`'s `workspace-path` field.                                                                                                                            |
| `--source-repo`                      | `None`             | Git repository URL. When provided, `source.json` is not required and the repository is cloned from this URL.                                                                                                                                                 |
| `--source-ref`                       | `None`             | Git ref (branch/tag/commit) to check out. Defaults to the repository's default branch. Requires `--source-repo`.                                                                                                                                             |
| `--output-dir`                       | `/outputs`         | Directory for build artifacts (`.tgz` files and integrity hash files)                                                                                                                                                                                        |
| `--push-images` / `--no-push-images` | `--no-push-images` | Whether to push container images to registry. Defaults to not pushing if no argument is provided                                                                                                                                                             |
| `--use-local`                        | `false`            | Use local repository instead of cloning from source.json                                                                                                                                                                                                     |
| `--log-level`                        | `INFO`             | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`                                                                                                                                                                                               |
| `--verbose`                          | `false`            | Show verbose output with file and line numbers                                                                                                                                                                                                               |
| `--clean`                            | `false`            | Automatically removes content of `--repo-path` directory when cloning from `source.json`. Ignored if `--use-local` is used.                                                                                                                                  |
| `--generate-build-args`              | `false`            | When `plugins-list.yaml` exists, recompute build arguments for all listed plugins using dependency analysis. See [Plugin List Auto-Generation](#plugin-list-auto-generation). **WARNING: This overwrites your `plugins-list.yaml` with updated build args.** |

**Workspace path resolution:** In single-workspace use cases, the workspace path can be provided via the `--workspace-path` CLI argument, or the `workspace-path` field in `source.json`. The CLI argument takes highest precedence, followed by the `source.json`. For the multi-workspace case, only the `workspace-path` field in `source.json` is supported.

**Using `--source-repo` instead of `source.json`:** For single-workspace use cases only, you can skip creating a `source.json` file entirely by using `--source-repo` (and optionally `--source-ref`) on the command line. When `--source-repo` is provided, `source.json` is ignored even if present. If `--source-ref` is omitted, the repository's default branch is used.

### Understanding Volume Mounts

When using the container, you can mount directories based on your needs:

| Volume Mount              | Required?    | Purpose                 | When to Use                                                                                         |
| ------------------------- | ------------ | ----------------------- | --------------------------------------------------------------------------------------------------- |
| `-v ./config:/config:z`   | **Required** | Configuration files     | Always - contains your `plugins-list.yaml`, `source.json`, patches, and overlays                    |
| `-v ./source:/source:z`   | Optional     | Source code location    | Only if using `--use-local` OR if you want to preserve/inspect the cloned/patched remote repository |
| `-v ./outputs:/outputs:z` | Optional     | Stores build artifacts  | Only if you want the output `.tgz` files saved locally (otherwise they stay in the container)       |

**Important**: These volume mount paths (`/config`, `/source`, `/outputs`) correspond to the default values of `--config-dir`, `--repo-path`, and `--output-dir`. If you override these arguments with custom paths, adjust your volume mounts accordingly.

**Note**: Use the `:z` flag for systems with SELinux enabled (RHEL/Fedora/CentOS). On other systems, you can omit it.

### Container Usage Examples

The following examples demonstrate common use cases with the container image. All examples assume you have the necessary configuration files (`source.json`, `plugins-list.yaml`, and optionally patches/overlays) in your configuration directory. See the [Configuration](#configuration) section for details.

#### Minimal example using `source.json`

This minimal example builds the TODO plugins without saving the workspace or output files locally. The repository, ref, and workspace path are all defined in the example's `source.json`:

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./examples/example-config-todo:/config:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
  --workspace-path workspaces/todo
```

This will clone the repository, build the plugins, and NOT push the result to a remote repository.

#### Minimal example using CLI args (no `source.json` needed)

You can skip `source.json` entirely by specifying the repository via CLI arguments:

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./config:/config:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
  --source-repo https://github.com/backstage/community-plugins \
  --source-ref main \
  --workspace-path workspaces/todo
```

If `--source-ref` is omitted, the repository's default branch is used automatically.

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

**Important**: If the destination repository is a `quay.io` repository and does not exist, the factory will attempt to create a private repository. This may lead to issues described [below](#quayio-repository-publishing-issues). If you are having issues, please create the repositories before running the factory.

If you do need to manually create the quay repository, the expected naming scheme for the repository is `quay.io/${REGISTRY_NAMESPACE}/${REPO_NAME}` where `${REPO_NAME}` is the `name` field of the `package.json` for the plugin except with `@` removed and instances of `/` replaced with `-`.

Ex: `@red-hat-developer-hub/backstage-plugin-quickstart` -> `red-hat-developer-hub-backstage-plugin-quickstart`

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

### Multi-Workspace Mode

When the config directory contains subdirectories with `source.json` files, the factory automatically enters multi-workspace mode. This allows you to build plugins from multiple workspaces across different (or the same) repositories in a single run. Each workspace will have the same directory layout as a normal single workspace config directory.

#### How It Works

1. **Workspace Discovery**: The factory scans `--config-dir` for subdirectories containing `source.json`. Directories without `source.json` are ignored.
2. **Repository Cloning**: Workspaces sharing the same repository URL share a single bare clone. Each workspace gets its own isolated [git worktree](https://git-scm.com/docs/git-worktree) at its specified ref which are stored in the `--repo-path` directory.
3. **Environment Isolation**: Each workspace's `.env` file is loaded independently. The order in which environmental variables are loaded is as follows: `default.env` -> root `config/.env` -> workspace `.env`, with full env isolation between workspaces.
4. **Error Collection**: A failure in one workspace does not stop processing of other workspaces. Errors are collected and reported in a summary at the end.

#### Multi-Workspace CLI Restrictions

The following CLI arguments are **not allowed** in multi-workspace mode since each workspace defines its own source configuration:

- `--source-repo`
- `--source-ref`
- `--workspace-path`

#### Multi-Workspace Example

Create workspace subdirectories under your config directory:

```bash
config/
├── .env                    # Shared env (e.g., registry credentials)
├── todo/
│   ├── source.json         # {"repo": "https://github.com/backstage/community-plugins", "repo-ref": "main", "workspace-path": "workspaces/todo"}
│   └── plugins-list.yaml
└── gitlab/
    ├── source.json         # {"repo": "https://github.com/immobiliare/backstage-plugin-gitlab", "repo-ref": "main", "workspace-path": "."}
    ├── plugins-list.yaml
    └── .env                # Optional workspace level environmental variable overrides
```

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./config:/config:z \
  -v ./source:/source:z \
  -v ./outputs:/outputs:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest
```

The factory will process each workspace sequentially, creating worktrees under `/source/` and outputs under `/outputs/`.

## Output

### Build Artifacts

#### Single Workspace Mode Outputs

The factory also produces the following outputs in the directory specified by `--output-dir`:

```bash
outputs/
├── plugin-name-dynamic-1.0.0.tgz           # Plugin tarball
├── plugin-name-dynamic-1.0.0.tgz.integrity # Integrity checksum
└── ...
```

#### Multi-Workspace Mode Outputs

In multi-workspace mode, the `--output-dir` directory will be partitioned into separate subdirectories, one for each workspace:

```bash
outputs
├── aws-ecs
│   ├── aws-amazon-ecs-plugin-for-backstage-backend-dynamic-0.9.0.tgz
│   ├── aws-amazon-ecs-plugin-for-backstage-backend-dynamic-0.9.0.tgz.integrity
│   ├── aws-amazon-ecs-plugin-for-backstage-dynamic-0.6.2.tgz
│   └── aws-amazon-ecs-plugin-for-backstage-dynamic-0.6.2.tgz.integrity
└── todo
    ├── backstage-community-plugin-todo-backend-dynamic-0.15.0.tgz
    ├── backstage-community-plugin-todo-backend-dynamic-0.15.0.tgz.integrity
    ├── backstage-community-plugin-todo-dynamic-0.14.0.tgz
    └── backstage-community-plugin-todo-dynamic-0.14.0.tgz.integrity
```

### Container Images

When `--push-images` is enabled, images are tagged as:

```bash
${REGISTRY_URL}/${REGISTRY_NAMESPACE}/plugin-name-dynamic:1.0.0
```

NOTE: If the repository name (ex: plugin-name-dynamic) in the namespace specified by `REGISTRY_NAMESPACE` does not exist, the dynamic plugin factory will create a new registry. Depending on the registry specified by `REGISTRY_URL`, the newly created repository may be private. This will be the case for `quay.io`.

## Examples

The `examples` directory contains ready-to-use configuration examples demonstrating different use cases and features.

| Example             | Description                                                   | Details                                                            |
| ------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------ |
| **TODO**            | Basic single-workspace with custom scalprum-config            | [View README](./examples/example-config-todo/README.md)            |
| **GitLab**          | Overlays for non Backstage Community Plugins workspace format | [View README](./examples/example-config-gitlab/README.md)          |
| **AWS ECS**         | Patches and embed packages in plugins-list.yaml               | [View README](./examples/example-config-aws-ecs/README.md)         |
| **Multi-Workspace** | Multiple workspaces from different repos in a single run      | [View README](./examples/example-config-multi-workspace/README.md) |

### Quick Example: TODO Workspace

Build the TODO plugin from Backstage community plugins using the example config:

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./examples/example-config-todo:/config:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
  --workspace-path workspaces/todo \
  --no-push-images
```

Or build the same plugin using only CLI arguments (only a `plugins-list.yaml` in the config directory is needed):

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./examples/example-config-todo:/config:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
  --source-repo https://github.com/backstage/community-plugins \
  --workspace-path workspaces/todo \
  --no-push-images
```

This example includes:

- Custom `scalprum-config.json` configuration
- A source repository using the standard Backstage Community Plugins workspace format
- Both frontend and backend plugins in the workspace

For detailed instructions, package verification steps, and additional examples, see the individual README files linked in the table above.

## Troubleshooting & Common Issues

This section covers common issues encountered when building, publishing, and installing dynamic plugins generated with the factory.

### Frontend Plugin Not Loading

When dynamically installing frontend plugins, they may fail to load or display incorrectly in RHDH.

To begin debugging, open your browser's developer console (F12) and check for loading errors. These errors are typically informative and indicate the root cause.

**Example Error:**

```text
Plugin backstage-community.plugin-entity-feedback is not configured properly: PluginRoot.default not found, ignoring mountPoint: "entity.page.feedback/cards"
```

In most cases, the issue arise from missing or incorrect plugin configuration for the frontend wiring for the plugin.

To fix this, ensure all required mount points, routes, and bindings are correctly defined. Refer to the [RHDH frontend wiring documentation](https://github.com/redhat-developer/rhdh/blob/main/docs/dynamic-plugins/frontend-plugin-wiring.md) for more details on how to do this.

### Backend Module Not Loading (Missing Dependencies)

When dynamically installing backend plugins, they may fail to load due to a `MODULE_NOT_FOUND` error.

**Example Error:**

```text
backstage error an error occurred while loading dynamic backend plugin '@internal/backstage-plugin-catalog-backend-module-github-org-transformer-dynamic' from 'file:///opt/app-root/src/dynamic-plugins-root/backstage-plugin-catalog-backend-module-github-org-transformer' Cannot find module '@backstage/plugin-catalog-backend-module-github'
Require stack:
- /opt/app-root/src/dynamic-plugins-root/backstage-plugin-catalog-backend-module-github-org-transformer/dist/module.cjs.js
- /opt/app-root/src/dynamic-plugins-root/backstage-plugin-catalog-backend-module-github-org-transformer/dist/index.cjs.js
  code="MODULE_NOT_FOUND" requireStack=["/opt/app-root/src/dynamic-plugins-root/backstage-plugin-catalog-backend-module-github-org-transformer ...
```

This indicates the backend plugin has dependencies that were not bundled in the dynamic plugin package when exporting with the factory.

To solve this, embed the missing dependency/dependencies using the `--embed-package` flag in your `plugins-list.yaml`:

```yaml
plugins/my-backend-plugin: --embed-package @backstage/plugin-catalog-backend-module-github --embed-package <any-other-required-modules>
```

**Note:** By default, the `rhdh-cli` only embeds `-common` and `-node` packages from your backend plugin's dependencies. Any non-`@backstage` dependencies not included in your RHDH instance must be explicitly embedded.

**Note:** The `MODULE_NOT_FOUND` error is thrown for the first missing module. It might not be the only missing module, so be sure to verify all the relevant private dependencies are embedded during the export.

### Skopeo Fails During Plugin Installation

During plugin installation via helm chart or operator, it may fail with a Skopeo error such as:

```text
subprocess.CalledProcessError: Command '['/usr/bin/skopeo', 'inspect', '--raw', 'docker://quay.io/my-test-organization/red-hat-developer-hub-backstage-plugin-scaffolder-backend-module-orchestrator:1.3.1']' returned non-zero exit status 1
```

The main cause of this issue are:

1. The repository is private and authentication is not configured, in which case you should set it to public or configure the proper authentication to pull from the repository.
2. The repository does not exist (see [Quay.io Repository Publishing Issues](#quayio-repository-publishing-issues) below), if so, you may need to manually create the repository and rebuild/publish with the factory (see [Build and Push to Registry](#build-and-push-to-registry) for the expected repository naming scheme)

### Quay.io Repository Publishing Issues

The factory logs may indicate successful image publication, but the image does not appear in your Quay.io repository.

This may be due to Quay.io silently failing to publish images since your account has reached its private repository quota limit. When pushing to a non-existent repository, Quay.io automatically creates a private repository. If your account or organization has exhausted its private repository allocation, the creation may silently fails.

To mitigate this, you may need to pre-create the repositories on `quay.io` before publishing to avoid having the factory attempt to create the repositories. Alternatively, you can upgrade your `quay.io` plan to increase the private repository allocation.

### Plugin Export Fails Entry Point Validation Check

The build argument auto-generation handles native modules as follows:

In some cases a plugin may fail the entry point validation check because the RHDH CLI attempts to load the plugin and a required native module has been suppressed. If the failure is due to a native module removed via `--suppress-native-package`, you can that argument with `--shared-package` for that specific module in your `plugins-list.yaml` since the native module most likely already exists in the `rhdh` container.

If the export still fails due to a dependency depending on this native module, you will need to embed it via `--embed-packages`. The error logs will indicate which dependency should be embedded.

Example Error Log:

```bash
Error: Following shared package(s) should not be part of the plugin private dependencies:                                
- better-sqlite3                                                                                                         
        
Either unshare them with the --shared-package !<package> option, or use the --embed-package to embed the following   packages which use shared dependencies:                                                                                  
- @langchain/langgraph-checkpoint-sqlite  
```

If the plugin fails to startup properly after installation due to the native module not being installed in the `rhdh` container, you will need to use experimental `--allow-native-package` arg instead to package the native module with the plugin instead.

Note: Be sure to re-run the factory in a clean `--repo-path` environment since this can result in `yarn install --immutable` failing due to `yarn.lock` files present from previous factory runs.

Example Entry Point Validation Error:

Auto-generated `plugins-list.yaml` entry that will fail:

```yaml
plugins/scaffolder-backend: --suppress-native-package isolated-vm --suppress-native-package napi-build-utils
```

```bash
Validating plugin entry points                                                                                           
    adding typescript extension support to enable entry point validation

Error: Unable to validate plugin entry points: Error: The package "isolated-vm" has been marked as
         a native module and removed from this dynamic plugin package                                      
         "@backstage/plugin-scaffolder-backend-dynamic", as native modules are not currently supported by  
         dynamic plugins
```

Fixed `plugins-list.yaml` entry:

```yaml
plugins/scaffolder-backend: --shared-package isolated-vm --suppress-native-package napi-build-utils
```

## Local Development & Contributing

For users who want to run the factory locally without containers or contribute to the project, see [CONTRIBUTING.md](./CONTRIBUTING.md).

## Resources

To learn more about how dynamic plugins work refer to the [dynamic plugins documentation](https://github.com/redhat-developer/rhdh/blob/main/docs/dynamic-plugins/index.md) in the RHDH Repository
