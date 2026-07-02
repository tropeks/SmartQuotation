"""
Regression: orchestrator runtime artifacts (.orch_evidence.txt, .orch_*) must
never be tracked by git.

.orch_evidence.txt is written by the orchestrator worker to report test
evidence for a task; it is not source code. If it gets committed, a stale
copy checked out into a fresh worktree can false-verify later tasks (this
already happened once, fixed in d6649f0, then regressed via a force-add in
e3fad6f). Untracking + .gitignore alone doesn't stick if a future commit
force-adds the file again, so this test guards the invariant permanently.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _tracked_files():
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.splitlines()


def test_orch_evidence_file_not_tracked_by_git():
    tracked = _tracked_files()
    assert ".orch_evidence.txt" not in tracked, (
        ".orch_evidence.txt is a runtime artifact written by the orchestrator "
        "worker, not source code, and must not be committed to git. Run "
        "'git rm --cached .orch_evidence.txt'."
    )


def test_no_orch_prefixed_files_tracked_by_git():
    tracked = _tracked_files()
    offenders = [f for f in tracked if Path(f).name.startswith(".orch_")]
    assert not offenders, (
        f"Found tracked orchestrator runtime artifacts: {offenders}. "
        f"These must be untracked (git rm --cached) and stay covered by "
        f".gitignore's '.orch_*' pattern."
    )


def test_gitignore_covers_orch_artifacts():
    gitignore = (ROOT / ".gitignore").read_text()
    assert ".orch_*" in gitignore, (
        ".gitignore must contain '.orch_*' to prevent orchestrator runtime "
        "artifacts from being re-added to git."
    )


if __name__ == "__main__":
    import sys

    tests = [
        test_orch_evidence_file_not_tracked_by_git,
        test_no_orch_prefixed_files_tracked_by_git,
        test_gitignore_covers_orch_artifacts,
    ]
    failed = []
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed.append(t.__name__)
    print()
    if failed:
        print(f"FAILED: {len(failed)}/{len(tests)} tests failed")
        sys.exit(1)
    else:
        print(f"OK: all {len(tests)} tests passed")
