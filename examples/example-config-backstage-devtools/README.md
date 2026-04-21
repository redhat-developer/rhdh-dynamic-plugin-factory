# Backstage DevTools Example Configuration

This example demonstrates building the DevTools plugins from the main Backstage repository.

## Table of Contents

- [Backstage DevTools Example Configuration](#backstage-devtools-example-configuration)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [Example Config Directory Structure](#example-config-directory-structure)
    - [Configuration Files](#configuration-files)
  - [Quick Start](#quick-start)
    - [Container Execution (Recommended)](#container-execution-recommended)
    - [Local Development](#local-development)
  - [Expected Output](#expected-output)
  - [Publishing the package](#publishing-the-package)
  - [Next Steps](#next-steps)

## Overview

This example builds the frontend and backend DevTools plugins from the [backstage/backstage](https://github.com/backstage/backstage) repository. It is a minimal configuration with no patches or overlays required.

## Example Config Directory Structure

```bash
example-config-backstage-devtools/
├── plugins-list.yaml                # List of plugins to build
└── source.json                      # Source repository configuration
```

### Configuration Files

- **`source.json`**: Specifies the Backstage repository and git reference to clone from. The `repo-ref` field is optional; when omitted, the repository's default branch is used. The `workspace-path` field can also be set here instead of using `--workspace-path`.
- **`plugins-list.yaml`**: Lists the path to the DevTools frontend and backend plugins to build with respect to the workspace path

## Quick Start

### Container Execution (Recommended)

From the repository root, run:

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./examples/example-config-backstage-devtools:/config:z \
  -v ./outputs:/outputs:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
```

Note: `workspace-path` is set to `.` in the `source.json` because the Backstage repository does not follow the backstage community plugins (BCP) repository structure where there are multiple yarn workspaces. Instead the plugins are stored in the main workspace, so root of the workspace is also the root of the repository in this example.

### Local Development

From the repository root, run:

```bash
python -m src.rhdh_dynamic_plugin_factory \
  --config-dir ./examples/example-config-backstage-devtools \
  --repo-path ./source \
  --output-dir ./outputs
```

Or using CLI args instead of `source.json`:

```bash
python -m src.rhdh_dynamic_plugin_factory \
  --source-repo https://github.com/backstage/backstage \
  --source-ref 6b60bd75fd1d448a16c2c28dbb3e9a10c1e8a722 \
  --config-dir ./examples/example-config-backstage-devtools \
  --workspace-path . \
  --repo-path ./source \
  --output-dir ./outputs
```

This will do the following:

1. The factory clones the Backstage repository to `./source`
2. Dependencies are installed at the repository root
3. Both frontend and backend DevTools plugins are compiled
4. Plugins are exported as dynamic plugins using the RHDH CLI
5. Plugin tarballs and integrity files are created in `./outputs`

## Expected Output

After successful execution, you'll find these files in `./outputs`:

```bash
outputs/
├── backstage-plugin-devtools-X.Y.Z.tgz
├── backstage-plugin-devtools-X.Y.Z.tgz.integrity
├── backstage-plugin-devtools-backend-X.Y.Z.tgz
└── backstage-plugin-devtools-backend-X.Y.Z.tgz.integrity
```

Note: Version numbers may vary depending on the plugin versions in the source repository.

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

- Review the [TODO example](../example-config-todo/) for a simpler use case with custom scalprum-config
- Try the [Toolbox example](../example-config-toolbox/) to learn about patches and backend modules
- Try the [AWS ECS example](../example-config-aws-ecs/) to learn about patches and embed packages
- Read the [main README](../../README.md) for more configuration options
