#!/usr/bin/env python3
"""
Quick smoke test for the self-healing pipeline.

Runs py_compile on all changed Python files + the pytest suite.
Exit 0 = safe to push. Exit 1 = fix is broken, do not push.

Usage:
    python scripts/smoke_test.py          # test everything modified since last commit
    python scripts/smoke_test.py --full   # test all files regardless
"""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_changed_files() -> list[str]:
    """Python files changed since last commit (staged + unstaged)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--diff-filter=ACMR"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT),
        )
        return [f for f in result.stdout.strip().split("\n")
                if f.endswith(".py") and f.strip()]
    except Exception:
        return []


def compile_check(files: list[str]) -> bool:
    """Run py_compile on each file."""
    if not files:
        return True
    result = subprocess.run(
        ["python3", "-m", "py_compile"] + files,
        cwd=str(PROJECT_ROOT),
    )
    return result.returncode == 0


def run_tests() -> bool:
    """Run the pytest suite."""
    result = subprocess.run(
        ["python3", "-m", "pytest", "tests/", "-q", "--tb=short"],
        cwd=str(PROJECT_ROOT),
    )
    return result.returncode == 0


def main():
    full = "--full" in sys.argv
    print("=" * 50)
    print("STARFIRE Smoke Test")
    print("=" * 50)

    if full:
        py_files = [str(p.relative_to(PROJECT_ROOT))
                    for p in PROJECT_ROOT.rglob("*.py")
                    if "alembic/versions" not in str(p)]
    else:
        py_files = get_changed_files()

    # 1. Compile check
    if py_files:
        print(f"\n[1/2] Compile-checking {len(py_files)} file(s)...")
        if not compile_check(py_files):
            print("FAIL: Syntax error in changed files")
            return 1
        print("PASS: All files compile")
    else:
        print("\n[1/2] No changed Python files to compile-check")

    # 2. Test suite
    print(f"\n[2/2] Running pytest...")
    if not run_tests():
        print("FAIL: Tests did not pass")
        return 1
    print("PASS: All tests passed")

    print("\n" + "=" * 50)
    print("SMOKE TEST PASSED — safe to push")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
