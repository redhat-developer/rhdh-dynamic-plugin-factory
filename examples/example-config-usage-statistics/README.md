# Usage Statistics Example Configuration

This example demonstrates building the Usage Statistics plugins from a third-party repository.

## Table of Contents

- [Usage Statistics Example Configuration](#usage-statistics-example-configuration)
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

This example builds the frontend and backend Usage Statistics plugins from the [CodeVerse-GP/usage-statistics](https://github.com/CodeVerse-GP/usage-statistics) repository. It is a minimal configuration with no patches or overlays required.

## Example Config Directory Structure

```bash
example-config-usage-statistics/
├── plugins-list.yaml                # List of plugins to build
└── source.json                      # Source repository configuration
```

### Configuration Files

- **`source.json`**: Specifies the Usage Statistics repository and git reference to clone from. The `repo-ref` field is optional; when omitted, the repository's default branch is used. The `workspace-path` field can also be set here instead of using `--workspace-path`.
- **`plugins-list.yaml`**: Lists the path to the Usage Statistics frontend and backend plugins to build with respect to the workspace path

## Quick Start

### Container Execution (Recommended)

From the repository root, run:

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./examples/example-config-usage-statistics:/config:z \
  -v ./outputs:/outputs:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
```

Note: `workspace-path` is set to `.` in the `source.json` because this repository does not follow the backstage community plugins (BCP) repository structure where there are multiple yarn workspaces. Instead the plugins are stored in the main workspace, so root of the workspace is also the root of the repository in this example.

### Local Development

From the repository root, run:

```bash
python -m src.rhdh_dynamic_plugin_factory \
  --config-dir ./examples/example-config-usage-statistics \
  --repo-path ./source \
  --output-dir ./outputs
```

Or using CLI args instead of `source.json`:

```bash
python -m src.rhdh_dynamic_plugin_factory \
  --source-repo https://github.com/CodeVerse-GP/usage-statistics \
  --source-ref 66ab17d23837daa03e7755124f595308336fa3a7 \
  --config-dir ./examples/example-config-usage-statistics \
  --workspace-path . \
  --repo-path ./source \
  --output-dir ./outputs
```

This will do the following:

1. The factory clones the Usage Statistics repository to `./source`
2. Dependencies are installed at the repository root
3. Both frontend and backend Usage Statistics plugins are compiled
4. Plugins are exported as dynamic plugins using the RHDH CLI
5. Plugin tarballs and integrity files are created in `./outputs`

## Expected Output

After successful execution, you'll find these files in `./outputs`:

```bash
outputs/
├── usage-statistics-X.Y.Z.tgz
├── usage-statistics-X.Y.Z.tgz.integrity
├── usage-statistics-backend-X.Y.Z.tgz
└── usage-statistics-backend-X.Y.Z.tgz.integrity
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

- Review the [TODO example](../example-config-todo/) for a use case with custom scalprum-config
- Try the [Toolbox example](../example-config-toolbox/) to learn about patches and backend modules
- Try the [GitLab example](../example-config-gitlab/) to learn about overlays
- Read the [main README](../../README.md) for more configuration options
