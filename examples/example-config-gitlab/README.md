# GitLab Example Configuration

This example demonstrates building GitLab plugins from a non-standard repository structure using overlays to modify source files.

## Table of Contents

- [GitLab Example Configuration](#gitlab-example-configuration)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [Example Config Directory Structure](#example-config-directory-structure)
    - [Configuration Files](#configuration-files)
  - [Understanding Overlays](#understanding-overlays)
    - [How Overlays Work](#how-overlays-work)
  - [Quick Start](#quick-start)
    - [Container Execution (Recommended)](#container-execution-recommended)
    - [Local Development](#local-development)
  - [Expected Output](#expected-output)
  - [Publishing the package](#publishing-the-package)
  - [Next Steps](#next-steps)

## Overview

This example builds the frontend and backend GitLab plugins from the [immobiliare/backstage-plugin-gitlab](https://github.com/immobiliare/backstage-plugin-gitlab) repository. It uses overlays to replace specific source files with custom versions needed for proper dynamic plugin export.

## Example Config Directory Structure

```bash
example-config-gitlab/
├── packages/
│   └── gitlab-backend/
│       └── overlay/
│           └── src/
│               ├── bundle.ts         # Custom bundle configuration
│               └── index.ts          # Custom plugin export
├── plugins-list.yaml                 # List of plugins to build
└── source.json                       # Source repository configuration
```

### Configuration Files

- **`source.json`**: Specifies the GitLab plugin repository and git eference to clone from
- **`plugins-list.yaml`**: List of path to the GitLab frontend and backend packages to build
- **`packages/gitlab-backend/overlay/`**: Contains replacement source files

## Understanding Overlays

Overlays allow you to replace/add entire files in the plugin source code before building.

The overlay directory structure mirrors the plugin's source structure. Files in the overlay are copied over the original files at build time.

### How Overlays Work

1. The factory clones the source repository
2. Before building, it copies files from `config/<plugin-path>/overlay/` to the corresponding paths in `<workspace-path>/<plugin-path>/`
3. The overlaid files replace the original files completely if one exists, otherwise it will add the file
4. The modified source is then built and exported

**Warning**: Overlays are destructive - they permanently modify files in the workspace directory. Please make sure to have source control if using a local repository.

## Quick Start

### Container Execution (Recommended)

From the repository root, run:

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./examples/example-config-gitlab:/config:z \
  -v ./outputs:/outputs:z \
  -f ./source:/source:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
  --workspace-path .
```

Note: `--workspace-path .` is used because this repository does not follow the backstage community plugins (BCP) repository structure where there are multiple yarn workspaces. Instead the plugins are stored in the main workspace, so root of the workspace is also the root of the repository in this example.

### Local Development

From the repository root, run:

```bash
python -m src.rhdh_dynamic_plugin_factory \
  --config-dir ./examples/example-config-gitlab \
  --workspace-path . \
  --repo-path ./source \
  --output-dir ./outputs
```

This will do the following:

1. The factory clones the GitLab plugin repository to `./source`
2. Custom `bundle.ts` and `index.ts` files are copied to `./source/packages/gitlab-backend/src/`
3. Dependencies are installed at the repository source
4. Both frontend and backend plugins are compiled
5. Plugins are exported as dynamic plugins using the RHDH CLI
6. Plugin tarballs and integrity files are created in `./outputs`

## Expected Output

After successful execution, you'll find these files in `./outputs`:

```bash
outputs/
├── backstage-plugin-gitlab-6.13.0.tgz
├── backstage-plugin-gitlab-6.13.0.tgz.integrity
├── backstage-plugin-gitlab-backend-6.13.0.tgz
└── backstage-plugin-gitlab-backend-6.13.0.tgz.integrity
```

Note: Version numbers correspond to the tag specified in `source.json`.

## Publishing the package

If you want to publish the package, you will need to add a `--push-image` argument and provide the following environmental variables in the `/config/.env` file:

```bash
REGISTRY_URL="quay.io"
REGISTRY_USERNAME="your-username"
REGISTRY_PASSWORD="your-password" 
REGISTRY_NAMESPACE="your-namespace"
REGISTRY_INSECURE="false"
```

## Next Steps

- Try the [AWS ECS example](../example-config-aws-ecs/) to learn about patches
- Review the [TODO example](../example-config-todo/) for a simpler use case
- Read the [main README](../../README.md) for more configuration options
