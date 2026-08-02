#!/usr/bin/env python
"""Line-coverage gate for src/domain (PRODUCTION_EVOLUTION_PROMPT.md 8.3).

    uv run python scripts/domain_coverage.py            # gate at the default
    uv run python scripts/domain_coverage.py --min 97   # ratchet upward

Exits non-zero, listing the uncovered lines, when coverage falls below the gate.

Why not `coverage.py`/`pytest-cov`: this environment has no package-index access,
and a quality gate that cannot be installed is a quality gate that never runs.
`trace` has been in the standard library since 2.0, needs nothing, and measures
the same thing. If the project later gains network access, swapping in
`pytest --cov=src/domain --cov-fail-under=95` is a one-line change and this file
should be deleted rather than kept alongside it.

Only `src/domain` is measured. It is the layer where a wrong line silently
produces a wrong number about a real person, and it is the only layer that is
pure enough for a coverage figure to mean anything.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import trace
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "src" / "domain"

#: Tests that exercise the domain layer directly. Deliberately not the whole
#: suite: tracing the agent stack costs minutes and adds no domain coverage.
DOMAIN_TESTS = [
    "tests/unit/test_domain_properties.py",
    "tests/unit/test_domain_edges.py",
    "tests/unit/test_domain_statistics.py",
    "tests/unit/test_evolution.py",
    "tests/unit/test_intervention.py",
    "tests/unit/test_cohort_pass.py",
]

DEFAULT_MIN = 95.0


def executable_lines(path: pathlib.Path) -> set[int]:
    """Line numbers that can actually execute, from the compiled code objects.

    Derived from bytecode rather than from the source text, so comments, blank
    lines and multi-line expressions are handled the way the interpreter handles
    them instead of the way a regex would guess.
    """
    code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
    lines: set[int] = set()
    stack = [code]
    while stack:
        current = stack.pop()
        for _start, _end, lineno in current.co_lines():
            if lineno:
                lines.add(lineno)
        stack.extend(c for c in current.co_consts if isinstance(c, types.CodeType))
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min", type=float, default=DEFAULT_MIN)
    args = parser.parse_args()

    import pytest

    def run_suite() -> int:
        # Re-execute the package body under the tracer. Something in pytest's
        # startup imports `src.domain` before `runfunc` begins, and an already
        # imported module never runs again -- which reported `__init__.py` as 0%
        # covered when in fact it had run, just too early to be seen. Measuring
        # the wrong thing quietly is worse than not measuring.
        for name in [m for m in sys.modules if m.startswith("src.domain")]:
            del sys.modules[name]
        import src.domain  # noqa: F401

        return pytest.main(["-q", "--no-header", *DOMAIN_TESTS])

    tracer = trace.Trace(count=1, trace=0, ignoredirs=[sys.prefix, sys.exec_prefix])
    exit_code = tracer.runfunc(run_suite)
    if exit_code != 0:
        print("\nTests failed -- coverage not reported.", file=sys.stderr)
        return int(exit_code)

    executed: dict[str, set[int]] = {}
    for (filename, lineno), count in tracer.results().counts.items():
        if count:
            executed.setdefault(str(pathlib.Path(filename).resolve()), set()).add(
                lineno
            )

    total = covered = 0
    report: list[str] = []

    for path in sorted(DOMAIN.glob("*.py")):
        resolved = str(path.resolve())
        runnable = executable_lines(path)
        hit = runnable & executed.get(resolved, set())
        missing = sorted(runnable - hit)

        total += len(runnable)
        covered += len(hit)

        pct = 100.0 * len(hit) / len(runnable) if runnable else 100.0
        report.append(f"  {path.name:<16} {pct:6.2f}%  ({len(hit)}/{len(runnable)})")
        if missing:
            report.append(f"      uncovered: {missing}")

    overall = 100.0 * covered / total if total else 100.0

    print("\nsrc/domain line coverage")
    print("\n".join(report))
    print(f"  {'TOTAL':<16} {overall:6.2f}%  ({covered}/{total})")

    if overall < args.min:
        print(
            f"\nFAIL: {overall:.2f}% is below the {args.min:.2f}% gate.",
            file=sys.stderr,
        )
        return 1

    print(f"\nOK: {overall:.2f}% >= {args.min:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
