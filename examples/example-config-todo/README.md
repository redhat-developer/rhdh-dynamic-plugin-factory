# TODO Example Configuration

This example demonstrates building the TODO plugin from the Backstage Community Plugins repository with a custom `scalprum-config.json` configuration.

## Table of Contents

- [TODO Example Configuration](#todo-example-configuration)
  - [Table of Contents](#table-of-contents)
  - [Overview](#overview)
  - [Example Config Directory Structure](#example-config-directory-structure)
    - [Configuration Files](#configuration-files)
  - [Quick Start](#quick-start)
    - [Container Execution (Recommended)](#container-execution-recommended)
    - [Local Development](#local-development)
  - [Expected Output](#expected-output)
  - [Publishing the package](#publishing-the-package)
  - [Package Verification](#package-verification)
    - [Testing with RHDH Local](#testing-with-rhdh-local)
      - [Prerequisites](#prerequisites)
      - [Step 1: Configure Dynamic Plugins](#step-1-configure-dynamic-plugins)
      - [Step 2: Import a Catalog Entity](#step-2-import-a-catalog-entity)
      - [Step 3: Start RHDH Local](#step-3-start-rhdh-local)
      - [Step 4: Verify the Plugin](#step-4-verify-the-plugin)
      - [Step 5: Clean Up](#step-5-clean-up)
  - [Next Steps](#next-steps)

## Overview

This example builds both the frontend and backend TODO plugins from the Backstage Community Plugins repository. It includes a custom Scalprum configuration file to control the dynamic plugin export behavior.

## Example Config Directory Structure

```bash
example-config-todo/
├── plugins/
│   └── todo/
│       └── scalprum-config.json    # Custom Scalprum configuration to overlay
├── plugins-list.yaml                # List of plugins to build
└── source.json                      # Source repository configuration
```

### Configuration Files

- **`source.json`**: Specifies the Backstage Community Plugins repository and git reference to clone from
- **`plugins-list.yaml`**: Lists the path to the TODO frontend and backend plugins to build with respect to the workspace path
- **`plugins/todo/scalprum-config.json`**: Custom Scalprum configuration that will be overlaid on top of the plugin source directory

## Quick Start

### Container Execution (Recommended)

From the repository root, run:

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./examples/example-config-todo:/config:z \
  -v ./outputs:/outputs:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest \
  --workspace-path workspaces/todo
```

### Local Development

From the repository root, run:

```bash
python -m src.rhdh_dynamic_plugin_factory \
  --config-dir ./examples/example-config-todo \
  --repo-path ./source \
  --workspace-path workspaces/todo \
  --output-dir ./outputs
```

This will do the following:

1. The factory clones the Backstage Community Plugins repository to `./source`
2. The custom `scalprum-config.json` is overlaid on top of the plugin source directory
3. Dependencies are installed in the TODO workspace
4. Both frontend and backend plugins are exported and packaged using the RHDH CLI with the arguments defined in `./config/plugins-list.yaml` which in this case is no additional arguments
5. Plugin tarballs and integrity files are created in `./outputs`

## Expected Output

After successful execution, you'll find these files in `./outputs`:

```bash
outputs/
├── backstage-community-plugin-todo-0.12.0.tgz
├── backstage-community-plugin-todo-0.12.0.tgz.integrity
├── backstage-community-plugin-todo-backend-0.13.0.tgz
└── backstage-community-plugin-todo-backend-0.13.0.tgz.integrity
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

## Package Verification

### Testing with RHDH Local

You can verify the plugins work correctly by installing them in an RHDH instance. Here's how to test with [RHDH Local](https://github.com/redhat-developer/rhdh-local):

#### Prerequisites

- [RHDH Local](https://github.com/redhat-developer/rhdh-local) repository cloned
- [Podman](https://podman.io/) installed
- Plugins built and published to a container registry

#### Step 1: Configure Dynamic Plugins

Create a `dynamic-plugins.override.yaml` file in the RHDH Local config directory:

```yaml
includes:
  - dynamic-plugins.default.yaml
plugins:
  - package: oci://quay.io/{REGISTRY_NAMESPACE}/backstage-community-plugin-todo:0.12.0!backstage-community-plugin-todo
    disabled: false
    pluginConfig:
      dynamicPlugins:
        frontend:
          backstage-community.plugin-todo:
            mountPoints:
              - mountPoint: entity.page.todo/cards
                importName: EntityTodoContent
            entityTabs:
              - path: /todo
                title: Todo
                mountPoint: entity.page.todo
  - package: oci://quay.io/{REGISTRY_NAMESPACE}/backstage-community-plugin-todo-backend:0.13.0!backstage-community-plugin-todo-backend 
    disabled: false
```

Replace `{REGISTRY_NAMESPACE}` with your registry namespace.

**Note**: If you pushed to a private repository, make it public or configure Podman credentials.

#### Step 2: Import a Catalog Entity

Create or edit `config/app-config/app-config.local.yaml` to import the Backstage repository:

```yaml
catalog:
  locations:
    - type: url
      target: https://github.com/backstage/backstage/blob/master/catalog-info.yaml
      rules: 
        - allow: [Component]
```

#### Step 3: Start RHDH Local

```bash
podman compose up -d
```

#### Step 4: Verify the Plugin

1. Open your browser to <http://localhost:7007>
2. Navigate to the Backstage component located at <http://localhost:7007/catalog/default/component/backstage>
3. Click on the **Todo** tab
4. You should see a table containing all `TODO` comments from the Backstage source code

#### Step 5: Clean Up

```bash
podman compose down --volumes
```

## Next Steps

- Try the [GitLab example](../example-config-gitlab/) to learn about overlays
- Try the [AWS ECS example](../example-config-aws-ecs/) to learn about patches and embed packages
- Read the [main README](../../README.md) for more configuration options
