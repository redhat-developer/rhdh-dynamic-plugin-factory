# AWS ECS Example Configuration

This example demonstrates building AWS ECS plugins with patches for code fixes and embedded packages for additional dependencies.

## Table of Contents

- [AWS ECS Example Configuration](#aws-ecs-example-configuration)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [Example Config Directory Structure](#example-config-directory-structure)
    - [Configuration Files](#configuration-files)
  - [Understanding Patches](#understanding-patches)
    - [Patch Format](#patch-format)
    - [How Patches Work](#how-patches-work)
    - [Creating Patches](#creating-patches)
  - [Embed Packages](#embed-packages)
  - [Quick Start](#quick-start)
    - [Container Execution (Recommended)](#container-execution-recommended)
    - [Local Development](#local-development)
  - [Expected Output](#expected-output)
  - [Publishing the package](#publishing-the-package)
  - [Next Steps](#next-steps)

## Overview

This example builds the frontend and backend ECS plugins from the [awslabs/backstage-plugins-for-aws](https://github.com/awslabs/backstage-plugins-for-aws) repository. It includes the following configurations:

1. **Patches**: Small, targeted code changes applied via diff files
2. **Embed Packages**: Including additional dependency packages in the dynamic plugin export

## Example Config Directory Structure

```bash
example-config-aws-ecs/
├── backstage.json                    # Backstage configuration
├── patches/
│   └── 1-avoid-double-wildcards.patch  #  Path File
├── plugins-list.yaml                 # Plugins with embed-package arguments
└── source.json                       # Source repository configuration
```

### Configuration Files

- **`source.json`**: Specifies the AWS plugins repository and git reference to clone from
- **`plugins-list.yaml`**: Lists plugins with `--embed-package` arguments for shared dependencies
- **`backstage.json`**: Backstage configuration file
- **`patches/`**: Contains patch files

## Understanding Patches

Patches are **diff files** that apply small, targeted changes to the source code. Unlike overlays (which replace/adds entire files), patches modify specific lines.

### Patch Format

Patches use the standard unified diff format:

```diff
--- a/path/to/file
+++ b/path/to/file
@@ -line,count +line,count @@
 context line
-removed line
+added line
 context line
```

### How Patches Work

1. The factory clones the source repository
2. Before building, it applies all `.patch` files from `config/patches/` in alphabetical order
3. Each patch modifies specific lines in the source files
4. The patched source is then built and exported

**Warning**: Patches are destructive - they permanently modify files in the workspace directory. Please make sure to have source control if using a local repository.

### Creating Patches

To create your own patch:

1. Make changes to files in your workspace
2. Generate a patch file:

   ```bash
   git diff > my-fix.patch
   ```

3. Place the patch in `config/patches/`
4. Prefix with a number for ordering (e.g., `01-my-fix.patch`)

## Embed Packages

The `--embed-package` argument bundles shared dependencies directly into the dynamic plugin.

In this example, the ECS backend plugin embeds common AWS packages so that the backend application functions correctly.

```yaml
plugins/ecs/backend: --embed-package @aws/aws-core-plugin-for-backstage-common --embed-package @aws/aws-core-plugin-for-backstage-node
```

## Quick Start

### Container Execution (Recommended)

From the repository root, run:

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./examples/example-config-aws-ecs:/config:z \
  -v ./outputs:/outputs:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
  --workspace-path .
```

Note: `--workspace-path .` is used because this repository does not follow the backstage community plugins (BCP) repository structure where there are multiple yarn workspaces. Instead the plugins are stored in the main workspace, so root of the workspace is also the root of the repository in this example.

### Local Development

From the repository root, run:

```bash
python -m src.rhdh_dynamic_plugin_factory \
  --config-dir ./examples/example-config-aws-ecs \
  --workspace-path . \
  --repo-path ./source \
  --output-dir ./outputs
```

This will do the following:

1. The factory clones the AWS plugins repository to `./source`
2. The `1-avoid-double-wildcards.patch` is applied to fix workspace configuration
3. Dependencies are installed at the repository root
4. Frontend and backend ECS plugins are compiled
5. Shared AWS packages are embedded in the backend plugin
6. Plugins are exported as dynamic plugins using the RHDH CLI
7. Plugin tarballs and integrity files are created in `./outputs`

## Expected Output

After successful execution, you'll find these files in `./outputs`:

```bash
outputs/
├── aws-ecs-plugin-for-backstage-0.2.0.tgz
├── aws-ecs-plugin-for-backstage-0.2.0.tgz.integrity
├── aws-ecs-plugin-for-backstage-backend-0.3.0.tgz
└── aws-ecs-plugin-for-backstage-backend-0.3.0.tgz.integrity
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

- Try the [GitLab example](../example-config-gitlab/) to learn about overlays
- Review the [TODO example](../example-config-todo/) for a simpler use case
- Read the [main README](../../README.md) for more configuration options
- Explore other AWS plugins in the repository
