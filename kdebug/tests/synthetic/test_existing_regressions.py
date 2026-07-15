from __future__ import annotations

import sys
from pathlib import Path

import pytest

from runner import ArtifactWriter, CommandRunner, RunResult


def _require_success(
    result: RunResult,
    *,
    case_name: str,
    artifact_root: Path,
) -> None:
    if result.returncode == 0 and not result.timed_out:
        return
    artifact_dir = ArtifactWriter(artifact_root).write(case_name, result)
    pytest.fail(
        "%s failed rc=%s timeout=%s; artifacts=%s\nstdout tail:\n%s\nstderr tail:\n%s"
        % (
            case_name,
            result.returncode,
            result.timed_out,
            artifact_dir,
            result.stdout_raw[-4000:],
            result.stderr_raw[-4000:],
        )
    )


@pytest.mark.synthetic
@pytest.mark.design
@pytest.mark.slow
def test_existing_design_semantics_regression(
    command_runner: CommandRunner,
    repo_root: Path,
    kdebug_root: Path,
    artifact_root: Path,
) -> None:
    result = command_runner.run(
        ["bash", str(kdebug_root / "tests" / "design" / "run_semantics.sh")],
        cwd=repo_root,
        timeout_sec=900,
        metadata={"suite": "design-semantics"},
    )
    _require_success(
        result,
        case_name="existing-design-semantics",
        artifact_root=artifact_root,
    )
    assert "kdebug design semantics regression passed" in result.stdout_raw


@pytest.mark.synthetic
@pytest.mark.waveform
@pytest.mark.slow
def test_existing_nonaxi_waveform_regression(
    command_runner: CommandRunner,
    repo_root: Path,
    kdebug_root: Path,
    kdebug_bin: Path,
    artifact_root: Path,
) -> None:
    result = command_runner.run(
        [
            sys.executable,
            str(kdebug_root / "tests" / "waveform" / "run_complex_wave.py"),
            "--mode",
            "nonaxi",
            "--kdebug",
            str(kdebug_bin),
        ],
        cwd=repo_root,
        timeout_sec=1200,
        metadata={"suite": "waveform-nonaxi"},
    )
    _require_success(
        result,
        case_name="existing-waveform-nonaxi",
        artifact_root=artifact_root,
    )
    assert "PASS: kdebug complex waveform validation completed" in result.stdout_raw


@pytest.mark.synthetic
@pytest.mark.combined
@pytest.mark.active_trace
@pytest.mark.slow
def test_existing_combined_active_driver_regression(
    command_runner: CommandRunner,
    repo_root: Path,
    kdebug_root: Path,
    kdebug_bin: Path,
    artifact_root: Path,
) -> None:
    result = command_runner.run(
        [
            sys.executable,
            str(
                kdebug_root
                / "tests"
                / "combined"
                / "run_active_driver_fixture.py"
            ),
        ],
        cwd=repo_root,
        timeout_sec=1200,
        env={"KDEBUG": str(kdebug_bin), "KDEBUG_REQUIRE_NPI": "1"},
        metadata={"suite": "combined-active-driver"},
    )
    _require_success(
        result,
        case_name="existing-combined-active-driver",
        artifact_root=artifact_root,
    )
    assert "failed, 0 skipped" in result.stdout_raw
