# Multi-Workspace Example

This directory contains various example plugins to export in multi-workspace mode, where multiple workspaces are built in a single run.

## Directory Structure

```bash
example-config-multi-workspace/
├── todo/                       # Workspace: TODO plugins from community-plugins
│   ├── source.json             # repo, repo-ref, workspace-path for this workspace
│   └── plugins-list.yaml       # Plugins to build from the TODO workspace
└── aws-ecs/                    # Workspace: AWS ECS plugins
    ├── source.json             # repo, repo-ref, workspace-path for this workspace
    └── plugins-list.yaml       # Plugins to build from the AWS ECS workspace
```

Each subdirectory containing a `source.json` file is treated as an independent workspace. Directories without `source.json` are ignored.

## How It Works

1. The factory discovers workspace subdirectories by scanning for `source.json` files.
2. Workspaces sharing the same repository URL share a single bare clone (via `git worktree`).
3. Each workspace is processed sequentially -- failures in one workspace do not stop others.
4. Outputs are written to per-workspace subdirectories under `--output-dir`.

## Quick Start

### Using Containers

```bash
podman run --rm -it \
  --device /dev/fuse \
  -v ./examples/example-config-multi-workspace:/config:z \
  -v ./source:/source:z \
  -v ./outputs:/outputs:z \
  quay.io/rhdh-community/dynamic-plugins-factory:latest
```

Note: `--workspace-path`, `--source-repo`, and `--source-ref` cannot be used. Instead each workspace's `source.json` provides these values.

### Running Locally

```bash
python src/rhdh_dynamic_plugin_factory \
  --config-dir ./examples/example-config-multi-workspace \
  --repo-path ./source \
  --output-dir ./outputs
```

## Source Repository Structure

When cloning the remote repositories into the directory defined by `--repo-path`, it will be partitioned into separate git worktrees for each workspace alongside a `.clones` repository containing a bare clone of the source repositories of each workspace.

```bash
source/
├── .clones/
│   ├── backstage-plugins-for-aws
│   ├── community-plugins
├── todo/
│   └── ...
└── aws-ecs/
    └── ...
```

## Output Structure

After running, the output directory will contain per-workspace subdirectories:

```bash
outputs/
├── todo/
│   ├── backstage-community-plugin-todo-dynamic-X.Y.Z.tgz
│   ├── backstage-community-plugin-todo-backend-dynamic-X.Y.Z.tgz
│   └── ...
└── aws-ecs/
    ├── aws-ecs-plugin-frontend-dynamic-X.Y.Z.tgz
    ├── aws-ecs-plugin-backend-dynamic-X.Y.Z.tgz
    └── ...
```

## Environment Variables

You can add a root `.env` file to configure shared settings (e.g., registry credentials) inherited by all workspaces. Each workspace can also have its own `.env` to override specific values:

```bash
example-config-multi-workspace/
├── .env                        # Root: shared by all workspaces
├── todo/
│   ├── .env                    # Optional: overrides for todo workspace
│   ├── source.json
│   └── plugins-list.yaml
└── aws-ecs/
    ├── source.json
    └── plugins-list.yaml
```

The environmental variable priority is defined as follows from lowest priority to highest: `default.env` -> root `.env` -> workspace `.env`.
