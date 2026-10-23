import ast
import os
from pathlib import Path

IGNORED_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__",
    "node_modules", ".idea", ".vscode", "dist", "build",
    ".pytest_cache", ".mypy_cache",
}

MAX_FILES = 1500
MAX_FILE_SIZE = 500_000

IMPORTANT_FILES = {
    "requirements.txt",
    "pyproject.toml",
    "poetry.lock",
    "Pipfile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "Procfile",
    "nginx.conf",
    "supervisord.conf",
}


def scan_project(project_path: str) -> dict:
    """Inspect a Python project without executing its code."""

    root = Path(project_path).expanduser().resolve()

    if not root.exists() or not root.is_dir():
        raise ValueError("Project path must be an existing directory.")

    files = []
    python_files = []
    skipped = 0

    for current, dirs, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)

        # Don't follow symlinked directories or scan common generated folders.
        dirs[:] = [
            name for name in dirs
            if name not in IGNORED_DIRS
            and not (current_path / name).is_symlink()
        ]

        for filename in filenames:
            path = current_path / filename

            if path.is_symlink() or not path.is_file():
                continue

            if path.suffix == ".py" or filename in IMPORTANT_FILES:
                try:
                    relative = path.relative_to(root).as_posix()
                except ValueError:
                    continue

                if len(files) >= MAX_FILES:
                    skipped += 1
                    continue

                if path.stat().st_size > MAX_FILE_SIZE:
                    skipped += 1
                    continue

                files.append(relative)

                if path.suffix == ".py":
                    python_files.append(path)

    findings = {
        "routes": [],
        "imports": [],
        "database_hints": [],
        "worker_hints": [],
        "external_service_hints": [],
        "configuration_hints": [],
        "entry_points": [],
        "deployment_files": [],
    }

    for relative in files:
        name = Path(relative).name.lower()

        if name in IMPORTANT_FILES:
            findings["deployment_files"].append(relative)

    # Read Python syntax trees; never import or run the target application.
    for path in python_files:
        relative = path.relative_to(root).as_posix()

        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative)
        except (OSError, UnicodeError, SyntaxError):
            continue

        for node in ast.walk(tree):
            line = getattr(node, "lineno", 1)

            if isinstance(node, ast.Import):
                modules = [item.name for item in node.names]

            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                modules = []

            for module in modules:
                findings["imports"].append({
                    "module": module,
                    "file": relative,
                    "line": line,
                })

                module_lower = module.lower()

                if any(term in module_lower for term in (
                    "sqlalchemy", "psycopg", "sqlite3", "pymongo",
                    "asyncpg", "databases", "mysql"
                )):
                    findings["database_hints"].append({
                        "evidence": f"Import: {module}",
                        "file": relative,
                        "line": line,
                    })

                if any(term in module_lower for term in (
                    "celery", "dramatiq", "rq", "arq"
                )):
                    findings["worker_hints"].append({
                        "evidence": f"Import: {module}",
                        "file": relative,
                        "line": line,
                    })

                if any(term in module_lower for term in (
                    "requests", "httpx", "aiohttp", "urllib"
                )):
                    findings["external_service_hints"].append({
                        "evidence": f"HTTP client import: {module}",
                        "file": relative,
                        "line": line,
                    })

                if module_lower in ("fastapi", "flask", "django"):
                    findings["configuration_hints"].append({
                        "evidence": f"Web framework import: {module}",
                        "file": relative,
                        "line": line,
                    })

            # Detect common web routes through decorators.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call):
                        continue

                    func = decorator.func
                    route_name = None

                    if isinstance(func, ast.Attribute):
                        if func.attr in {
                            "get", "post", "put", "patch",
                            "delete", "head", "options", "api_route"
                        }:
                            route_name = func.attr.upper()

                    if route_name:
                        path_arg = next(
                            (
                                arg.value
                                for arg in decorator.args
                                if isinstance(arg, ast.Constant)
                                and isinstance(arg.value, str)
                            ),
                            None,
                        )

                        if path_arg is not None:
                            findings["routes"].append({
                                "method": route_name,
                                "path": path_arg,
                                "function": node.name,
                                "file": relative,
                                "line": decorator.lineno,
                            })

            # Detect common process entry-point patterns.
            if isinstance(node, ast.If):
                test = node.test

                if (
                    isinstance(test, ast.Compare)
                    and isinstance(test.left, ast.Name)
                    and test.left.id == "__name__"
                ):
                    findings["entry_points"].append({
                        "evidence": 'if __name__ == "__main__"',
                        "file": relative,
                        "line": node.lineno,
                    })

            # Detect environment-variable access.
            if isinstance(node, ast.Call):
                func = node.func

                if (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                    and func.attr in {"getenv"}
                ):
                    findings["configuration_hints"].append({
                        "evidence": "Environment-variable access",
                        "file": relative,
                        "line": node.lineno,
                    })

    # Deduplicate repeated import and configuration evidence.
    for key in findings:
        findings[key] = _deduplicate(findings[key])

    return {
        "project": root.name,
        "root": str(root),
        "files_scanned": len(files),
        "python_files": len(python_files),
        "files_skipped_by_limits": skipped,
        "inspection_method": "Static inspection; target code was not executed.",
        "findings": findings,
        "limitations": [
            "Imports indicate possible dependencies, not proof they are used at runtime.",
            "Only recognizable route decorators are detected.",
            "Runtime health and actual service availability are not tested.",
            "Some indirect dependencies and dynamically registered components may be missed.",
        ],
    }


def _deduplicate(items: list[dict]) -> list[dict]:
    seen = set()
    result = []

    for item in items:
        key = tuple(sorted(item.items()))

        if key not in seen:
            seen.add(key)
            result.append(item)

    return result
