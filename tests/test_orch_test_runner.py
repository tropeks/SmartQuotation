import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ORCH_TEST_SCRIPT = ROOT / ".orch-test.sh"


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o755)


def _build_fake_workspace(tmp_path: Path, include_venv_python: bool) -> Path:
    workspace = tmp_path / "workspace"
    backend = workspace / "backend"
    fake_bin = tmp_path / "fake-bin"
    log_file = tmp_path / "runner.log"

    workspace.mkdir()
    backend.mkdir()
    fake_bin.mkdir()
    shutil.copy2(ORCH_TEST_SCRIPT, workspace / ".orch-test.sh")

    _write_executable(
        backend / "manage.py",
        "#!/usr/bin/env python3\n"
        "raise SystemExit('manage.py should not run directly in this test')\n",
    )

    _write_executable(
        fake_bin / "python",
        "#!/usr/bin/env bash\n"
        "echo path-python >> \"$RUNNER_LOG\"\n",
    )

    if include_venv_python:
        _write_executable(
            backend / ".venv" / "bin" / "python",
            "#!/usr/bin/env bash\n"
            "echo venv-python >> \"$RUNNER_LOG\"\n",
        )

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["RUNNER_LOG"] = str(log_file)

    result = subprocess.run(
        ["bash", str(workspace / ".orch-test.sh")],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    return log_file


def test_orch_test_prefers_backend_venv_python(tmp_path):
    log_file = _build_fake_workspace(tmp_path, include_venv_python=True)
    assert log_file.read_text().splitlines() == ["venv-python", "venv-python"]


def test_orch_test_falls_back_to_path_python_when_venv_missing(tmp_path):
    log_file = _build_fake_workspace(tmp_path, include_venv_python=False)
    assert log_file.read_text().splitlines() == ["path-python", "path-python"]
