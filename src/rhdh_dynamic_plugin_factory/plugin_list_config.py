"""
Plugin list configuration for RHDH Plugin Factory.

Handles loading, saving, and build-argument computation for plugins-list.yaml files.
"""

from logging import Logger
from pathlib import Path
import re
from typing import Dict, Optional, ClassVar
import yaml
import json

from . import constants
from .logger import get_logger


class PluginListConfig:
    """Configuration for plugin list (YAML format)."""

    logger: ClassVar[Logger] = get_logger("plugin_list")
    _host_packages_cache: ClassVar[set[str] | None] = None

    def __init__(self, plugins: Dict[str, str]):
        """
        Initialize plugin list configuration.
        
        Args:
            plugins: Dictionary mapping plugin paths to build arguments
        """
        self.plugins = plugins
    
    @classmethod
    def from_file(cls, plugin_list_file: Path) -> "PluginListConfig":
        """Load plugin list from YAML file."""
        
        with open(plugin_list_file, 'r') as f:
            data = yaml.safe_load(f) or {}
            
        plugins = {}
        for key, value in data.items():
            if value is None:
                plugins[key] = ""
            else:
                plugins[key] = str(value)
        
        return cls(plugins)
    
    def to_file(self, plugin_list_file: Path) -> None:
        """Save plugin list to YAML file.

        Writes manually rather than via yaml.dump so that entries with no
        build args appear as ``key:`` (YAML null) instead of ``key: ''``.

        Args:
            plugin_list_file: Destination path for the YAML file.
        """
        with open(plugin_list_file, 'w') as f:
            for path, args in self.plugins.items():
                if args:
                    f.write(f"{path}: {args}\n")
                else:
                    f.write(f"{path}:\n")
    
    def get_plugins(self) -> Dict[str, str]:
        return self.plugins.copy()
    
    def add_plugin(self, plugin_path: str, build_args: str = "") -> None:
        self.plugins[plugin_path] = build_args
    
    def remove_plugin(self, plugin_path: str) -> None:
        self.plugins.pop(plugin_path, None)

    def populate_build_args(self, workspace_path: Path) -> "PluginListConfig":
        """(Re)compute build arguments for every plugin in the list.

        Uses the same dependency analysis as :meth:`create_default` but only
        for the plugins already present in ``self.plugins``.  All existing
        build args are overwritten with freshly computed values.

        A before/after diff is logged for each plugin whose args changed so
        the user has a record to revert from if needed.

        Args:
            workspace_path: Absolute path to the workspace root
                (must already have ``node_modules`` installed).

        Returns:
            ``self``, mutated in place.
        """
        original = self.plugins.copy()
        host_packages = self._get_host_packages()

        for plugin_dir in self.plugins:
            pkg_json_path = workspace_path / plugin_dir / constants.PKG_JSON
            if not pkg_json_path.is_file():
                self.logger.warning(
                    f"Plugin package.json not found in workspace: {plugin_dir} "
                    f"(expected at {pkg_json_path})"
                )
                self.plugins[plugin_dir] = ""
                continue

            role = self._read_backstage_role(pkg_json_path)
            if not role or role not in constants.VALID_BACKSTAGE_PLUGIN_ROLES:
                self.logger.warning(
                    f"Plugin {plugin_dir} has no valid backstage.role — skipping build-arg computation. "
                    f"Found role: {role}. Valid roles are: {', '.join(constants.VALID_BACKSTAGE_PLUGIN_ROLES)}"
                )
                self.plugins[plugin_dir] = ""
                continue

            self.plugins[plugin_dir] = self._compute_plugin_build_args(
                workspace_path, plugin_dir, pkg_json_path, host_packages,
            )

        self._log_build_args_diff(original, self.plugins)
        return self

    @classmethod
    def _log_build_args_diff(
        cls, before: Dict[str, str], after: Dict[str, str],
    ) -> None:
        """Log a before/after comparison for plugins whose build args changed."""
        changed: list[str] = []
        unchanged: list[str] = []

        for plugin_dir in after:
            old = before.get(plugin_dir, "")
            new = after[plugin_dir]
            if old != new:
                changed.append(plugin_dir)
            else:
                unchanged.append(plugin_dir)

        if changed:
            cls.logger.info(
                f"Build args updated for {len(changed)} of "
                f"{len(after)} plugin(s):"
            )
            for plugin_dir in changed:
                old = before.get(plugin_dir, "")
                new = after[plugin_dir]
                cls.logger.info(f"  {plugin_dir}:")
                cls.logger.info(f"    before: {old or '(empty)'}")
                cls.logger.info(f"    after:  {new or '(empty)'}")

        if unchanged:
            cls.logger.info(
                f"Build args unchanged for {len(unchanged)} plugin(s):"
            )
            for plugin_dir in unchanged:
                cls.logger.info(
                    f"  {plugin_dir}: {after[plugin_dir] or '(empty)'}"
                )

    @classmethod
    def _compute_plugin_build_args(
        cls,
        workspace_path: Path,
        plugin_dir: str,
        pkg_json_path: Path,
        host_packages: set[str],
    ) -> str:
        """Compute build args for a single plugin based on its backstage role.

        Returns the CLI argument string for backend plugins, or empty
        string for frontend plugins.  Returns empty string if the role
        is not a valid plugin role.
        """
        role = cls._read_backstage_role(pkg_json_path)
        if not role or role not in constants.VALID_BACKSTAGE_PLUGIN_ROLES:
            return ""

        if role in constants.BACKEND_ROLES:
            return cls._compute_backend_build_args(
                workspace_path, plugin_dir, pkg_json_path, host_packages,
            )
        return ""

    @classmethod
    def create_default(cls, workspace_path: Path) -> "PluginListConfig":
        """Create a default plugin list by scanning workspace for Backstage plugins.

        Recursively walks *workspace_path* to find ``package.json`` files whose
        ``backstage.role`` matches one of :pyattr:`VALID_BACKSTAGE_PLUGIN_ROLES`.

        For backend plugins, dependency analysis is performed against the
        bundled RHDH host lockfile to determine ``--embed-package`` and
        ``--shared-package`` arguments.

        Args:
            workspace_path: Absolute path to the workspace root.

        Returns:
            A :class:`PluginListConfig` with discovered plugins and build arg(s) (if any).
        """
        plugins: Dict[str, str] = {}
        host_packages = cls._get_host_packages()

        # Corner case: if the workspace root has a valid backstage role, add it as a plugin
        root_pkg_json = workspace_path / constants.PKG_JSON
        if root_pkg_json.is_file():
            role = cls._read_backstage_role(root_pkg_json)
            if role and role in constants.VALID_BACKSTAGE_PLUGIN_ROLES:
                plugins["."] = cls._compute_plugin_build_args(
                    workspace_path, ".", root_pkg_json, host_packages,
                )

        for pkg_json_path in cls._find_package_jsons(workspace_path):
            role = cls._read_backstage_role(pkg_json_path)
            if role and role in constants.VALID_BACKSTAGE_PLUGIN_ROLES:
                plugin_dir = pkg_json_path.parent.relative_to(workspace_path).as_posix()
                plugins[plugin_dir] = cls._compute_plugin_build_args(
                    workspace_path, plugin_dir, pkg_json_path, host_packages,
                )

        sorted_plugins = dict[str, str](sorted(plugins.items()))
        cls.logger.debug(f"Discovered {len(sorted_plugins)} plugin(s) in {workspace_path}")
        return cls(sorted_plugins)

    @classmethod
    def _find_package_jsons(cls, root: Path) -> list[Path]:
        """Recursively find package.json files, skipping non-plugin directories."""
        results: list[Path] = []

        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name in constants.SKIP_DIRS or entry.name.startswith("."):
                continue

            pkg_json = entry / constants.PKG_JSON
            if pkg_json.is_file():
                results.append(pkg_json)

            results.extend(cls._find_package_jsons(entry))

        return results

    @classmethod
    def _read_backstage_role(cls, pkg_json_path: Path) -> Optional[str]:
        """Read the ``backstage.role`` field from a package.json file.

        Returns:
            The role string, or *None* if the file cannot be parsed or has no role.
        """
        try:
            data = json.loads(pkg_json_path.read_text(encoding="utf-8"))
            cls.logger.debug(f"Read backstage role from {pkg_json_path}: {data.get('backstage', {}).get('role')}")
            return data.get("backstage", {}).get("role")
        except (json.JSONDecodeError, OSError) as e:
            cls.logger.warning(f"Failed to read {pkg_json_path}: {e}")
            return None

    @classmethod
    def _get_host_packages(cls) -> set[str]:
        """Return cached host packages, parsing the lockfile on first call."""
        if cls._host_packages_cache is None:
            cls._host_packages_cache = cls._parse_host_packages(constants.HOST_LOCKFILE)
        return cls._host_packages_cache

    @classmethod
    def _parse_host_packages(cls, lockfile_path: Path) -> set[str]:
        """Extract all package names from a Yarn Berry lockfile (Yarn 2+).

        Scans top-level key lines (e.g.
        ``"@backstage/catalog-model@npm:^1.7.2, …":`` or
        ``"better-sqlite3@npm:^12.0.0":``) and collects distinct
        package names.  The returned set includes ``@backstage/*``
        packages as well as every other scoped or unscoped package.

        Args:
            lockfile_path: Path to the host ``yarn.lock`` file.

        Returns:
            Set of package names found in the lockfile,
            or an empty set if the file does not exist.
        """
        if not lockfile_path.is_file():
            cls.logger.warning(f"Host lockfile not found at {lockfile_path}")
            return set[str]()

        packages: set[str] = set[str]()
        for line in lockfile_path.read_text(encoding="utf-8").splitlines():
            # skip non-package lines
            if not line.startswith('"'):
                continue
            for match in constants.LOCKFILE_PACKAGE_RE.finditer(line):
                packages.add(match.group(1))

        cls.logger.debug(f"Parsed {len(packages)} @backstage/* packages from host lockfile")
        return packages

    @staticmethod
    def _get_sibling_names(plugin_name: str, role: str) -> set[str]:
        """Derive sibling package names that the RHDH CLI auto-embeds.

        Replicates the rhdh-cli logic: for backend plugins the CLI
        automatically embeds the ``-common`` and ``-node`` siblings.

        Args:
            plugin_name: The npm package name (e.g. ``@scope/my-plugin-backend``).
            role: The ``backstage.role`` value.

        Returns:
            Set of sibling package names, empty for non-backend roles.
        """
        if role == "backend-plugin":
            base = re.sub(r"-backend$", "", plugin_name)
        elif role == "backend-plugin-module":
            base = re.sub(r"-backend-module-.+$", "", plugin_name)
        else:
            return set[str]()

        if base == plugin_name:
            return set[str]()

        return {f"{base}-common", f"{base}-node"}

    @classmethod
    def _resolve_node_module_package_json(
        cls, workspace_path: Path, dep_name: str
    ) -> Optional[Path]:
        """Locate a dependency's ``package.json`` in the workspace root ``node_modules``.

        Yarn workspaces hoist all packages to the workspace root, so only that
        location is checked.

        Args:
            workspace_path: Absolute path to the workspace root.
            dep_name: npm package name (may be scoped, e.g. ``@aws/foo``).

        Returns:
            Path to the dependency's ``package.json``, or *None* if not found.
        """
        candidate = workspace_path / "node_modules" / dep_name / constants.PKG_JSON
        if candidate.is_file():
            return candidate
        return None

    @staticmethod
    def _is_native_module(pkg_data: dict) -> bool:
        """Check whether a ``package.json`` describes a native Node.js module.

        Replicates the logic of the ``is-native-module`` npm package used by RHDH CLI.
        """
        deps = pkg_data.get("dependencies", {})
        if any(marker in deps for marker in constants.NATIVE_DEP_MARKERS):
            return True
        if pkg_data.get("gypfile"):
            return True
        if pkg_data.get("binary"):
            return True
        return False

    @classmethod
    def _gather_native_modules(
        cls,
        workspace_path: Path,
        private_dep_names: set[str],
    ) -> set[str]:
        """Find native modules in the transitive dependency tree of private deps.

        Recursively walks each dep's dependencies via ``node_modules``,
        checking :meth:`_is_native_module` on every package encountered.
        Tracks visited packages to avoid cycles.

        Args:
            workspace_path: Absolute workspace root.
            private_dep_names: Direct dep names to start the walk from.

        Returns:
            Set of native package names found.
        """
        native: set[str] = set[str]()
        visited: set[str] = set[str]()

        def _walk(dep_name: str) -> None:
            if dep_name in visited:
                return
            visited.add(dep_name)

            pkg_json = cls._resolve_node_module_package_json(workspace_path, dep_name)
            if pkg_json is None:
                return

            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return

            if cls._is_native_module(data):
                native.add(dep_name)

            for field in ("dependencies", "optionalDependencies"):
                for sub_dep in data.get(field, {}):
                    _walk(sub_dep)

        for dep in private_dep_names:
            _walk(dep)

        return native

    @classmethod
    def _gather_backstage_deps(
        cls,
        workspace_path: Path,
        dep_name: str,
    ) -> set[str]:
        """Find ``@backstage/*`` packages in the transitive dependency tree.

        Recursively walks *dep_name*'s ``dependencies`` and
        ``optionalDependencies`` via ``node_modules``.  ``@backstage/*``
        packages are collected but not recursed into.  Tracks visited
        packages to avoid cycles.

        Returns:
            Set of ``@backstage/*`` package names found.
        """
        found: set[str] = set()
        visited: set[str] = set()

        def _walk(pkg_name: str) -> None:
            if pkg_name in visited:
                return
            visited.add(pkg_name)

            if pkg_name.startswith("@backstage/"):
                found.add(pkg_name)
                return

            pkg_json = cls._resolve_node_module_package_json(workspace_path, pkg_name)
            if pkg_json is None:
                return

            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                cls.logger.warning(f"Failed to read {pkg_json}: {e}")
                return

            for field in ("dependencies", "optionalDependencies"):
                for sub_dep in data.get(field, {}):
                    _walk(sub_dep)

        _walk(dep_name)
        return found

    @classmethod
    def _compute_backend_build_args(
        cls,
        workspace_path: Path,
        plugin_dir: str,
        pkg_json_path: Path,
        host_packages: set[str],
    ) -> str:
        """Compute ``--embed-package`` / ``--shared-package`` args for a backend plugin.

        Analyses the plugin's direct dependencies:

        * ``@backstage/*`` deps missing from *host_packages* are unshared
          **and** embedded (the host won't provide them at runtime).
        * Non-``@backstage/*``, non-sibling deps whose own dependencies
          include ``@backstage/*`` packages are embedded.  Any of those
          sub-deps missing from *host_packages* are additionally unshared.
        * Native modules are unconditionally suppressed (removed from the
          bundle) since dynamic plugins do not support them.

        Args:
            workspace_path: Absolute workspace root.
            plugin_dir: Plugin directory relative to *workspace_path*.
            pkg_json_path: Path to the plugin's ``package.json``.
            host_packages: All package names present in the host lockfile.

        Returns:
            CLI argument string, or ``""`` if no extra args are needed.
        """
        try:
            pkg_data = json.loads(pkg_json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return ""

        plugin_name: str = pkg_data.get("name", "")
        role: str = pkg_data.get("backstage", {}).get("role", "")
        dependencies: dict = pkg_data.get("dependencies", {})

        siblings = cls._get_sibling_names(plugin_name, role)

        embed_packages: set[str] = set[str]()
        unshare_packages: set[str] = set[str]()
        private_deps: set[str] = set[str]()

        for dep_name in dependencies:
            if dep_name in siblings:
                continue

            if dep_name.startswith("@backstage/"):
                if dep_name not in host_packages:
                    embed_packages.add(dep_name)
                    unshare_packages.add(dep_name)
                continue

            private_deps.add(dep_name)
            backstage_deps = cls._gather_backstage_deps(workspace_path, dep_name)
            if backstage_deps:
                embed_packages.add(dep_name)
                unshare_packages.update(
                    bs for bs in backstage_deps if bs not in host_packages
                )

        suppress_native = cls._gather_native_modules(
            workspace_path, private_deps | embed_packages | siblings,
        )

        parts = [f"--embed-package {pkg}" for pkg in sorted(embed_packages)]
        parts += [f"--shared-package !{pkg}" for pkg in sorted(unshare_packages)]
        parts += [f"--suppress-native-package {pkg}" for pkg in sorted(suppress_native)]
        return " ".join(parts)
