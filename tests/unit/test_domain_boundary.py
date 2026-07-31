# The dependency contract from PRODUCTION_EVOLUTION_PROMPT.md 4, enforced.
#
# "`domain` imports nothing from `agents`, `platform`, or any web framework."
#
# The reference tooling for this is import-linter. It is not used here: this
# environment has no package-index access, and a gate that cannot be installed is
# a gate that does not run. The contract is enforced with `ast` from the standard
# library instead -- fewer moving parts, no new dependency (Standing Rules), and
# it fails in the same place for the same reason.
#
# The list is an ALLOWLIST, not a blocklist. A blocklist only stops the imports
# someone already thought of; the first new framework anyone reaches for would
# sail straight through it.

import ast
import pathlib

DOMAIN_DIR = pathlib.Path(__file__).resolve().parents[2] / "src" / "domain"

#: Everything `domain` is permitted to import. Pure computation and typing only.
ALLOWED_ROOTS = frozenset(
    {
        "__future__",
        "src",  # narrowed to src.domain below
        "pydantic",
        "typing",
        "enum",
        "math",
        "statistics",
        "collections",
        "dataclasses",
        "abc",
        "bisect",
        "itertools",
        "functools",
        # Pure text matching, used by the self-critique pass in critique.py.
        # Still no I/O, no network, no framework -- the property this contract
        # exists to protect is untouched.
        "re",
    }
)


def _domain_files() -> list[pathlib.Path]:
    files = sorted(p for p in DOMAIN_DIR.glob("*.py"))
    assert files, "src/domain contains no modules -- the contract is checking nothing"
    return files


def _imported_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module)
    return found


def test_domain_imports_only_allowlisted_modules():
    violations: list[str] = []
    for path in _domain_files():
        for module in sorted(_imported_modules(path)):
            root = module.split(".")[0]
            if root not in ALLOWED_ROOTS:
                violations.append(f"{path.name}: {module}")
            elif root == "src" and not module.startswith("src.domain"):
                violations.append(f"{path.name}: {module}")

    assert not violations, (
        "src/domain must stay pure -- these imports break the contract:\n  "
        + "\n  ".join(violations)
    )


def test_domain_performs_no_io():
    """No file, socket or process access anywhere in the package.

    An import allowlist alone would still let `__import__('os')` or a bare
    `open(...)` through. Purity is what makes the package property-testable and
    what lets both entrypoints share it, so it is worth checking twice.
    """
    banned_calls = {"open", "__import__", "eval", "exec", "compile", "input"}
    violations: list[str] = []

    for path in _domain_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in banned_calls:
                    violations.append(f"{path.name}:{node.lineno}: {node.func.id}()")

    assert not violations, "src/domain must do no I/O:\n  " + "\n  ".join(violations)


def test_domain_is_importable_without_the_agent_stack():
    """Importing domain must not drag in ADK, dotenv or any provider client.

    If it did, every domain unit test would need credentials and CI would be one
    import away from touching a real LLM (6.3).
    """
    import subprocess
    import sys

    # Measured as a DELTA against a bare interpreter: some distributions install
    # a .pth that pre-registers `google`/`google.cloud` namespace stubs before
    # any project code runs, and blaming those on the domain package would make
    # this test permanently red for a reason nobody can fix.
    probe = (
        "import sys; "
        "before = set(sys.modules); "
        "import src.domain; "
        "added = set(sys.modules) - before; "
        "bad = [m for m in added "
        "if m.split('.')[0] in {'google', 'dotenv', 'fastapi', 'sklearn', 'starlette'}]; "
        "print(','.join(sorted(bad)))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(DOMAIN_DIR.parents[1]),
    )
    assert result.returncode == 0, result.stderr
    leaked = [m for m in result.stdout.strip().split(",") if m]
    assert not leaked, f"importing src.domain pulled in the agent stack: {leaked}"
