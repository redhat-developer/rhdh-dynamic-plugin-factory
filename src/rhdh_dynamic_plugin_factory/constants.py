"""
Shared constants for RHDH Plugin Factory.
"""

import re
from pathlib import Path

PLUGIN_LIST_FILE: str = "plugins-list.yaml"
SOURCE_CONFIG_FILE: str = "source.json"
PKG_JSON: str = "package.json"

VALID_BACKSTAGE_PLUGIN_ROLES: set[str] = {
    "frontend-plugin",
    "backend-plugin",
    "frontend-plugin-module",
    "backend-plugin-module",
}

BACKEND_ROLES: set[str] = {
    "backend-plugin",
    "backend-plugin-module",
}

SKIP_DIRS: set[str] = {
    "node_modules",
    "dist",
    "dist-dynamic",
    ".git",
    "__fixtures__",
}

HOST_LOCKFILE: Path = Path(__file__).parent.parent.parent / "resources" / "rhdh" / "yarn.lock"

LOCKFILE_BACKSTAGE_RE: re.Pattern = re.compile(r'"(@backstage/[\w.-]+)@npm:')

LOCKFILE_PACKAGE_RE: re.Pattern = re.compile(r'"((?:@[\w.-]+/)?[\w.-]+)@npm:')

NATIVE_DEP_MARKERS: frozenset[str] = frozenset[str](
    {
        "bindings",
        "prebuild",
        "nan",
        "node-pre-gyp",
        "node-gyp-build",
    }
)
