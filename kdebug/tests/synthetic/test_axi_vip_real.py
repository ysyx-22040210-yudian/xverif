from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from runner import ArtifactWriter, CommandRunner, RunResult


def _require_success(
    result: RunResult,
    *,
    artifact_root: Path,
    manifest: dict,
) -> None:
    if result.returncode == 0 and not result.timed_out:
        return
    artifact_dir = ArtifactWriter(artifact_root).write(
        "axi-vip-real",
        result,
        manifest=manifest,
    )
    pytest.fail(
        "AXI VIP regression failed rc=%s timeout=%s; artifacts=%s\n"
        "stdout tail:\n%s\nstderr tail:\n%s"
        % (
            result.returncode,
            result.timed_out,
            artifact_dir,
            result.stdout_raw[-8000:],
            result.stderr_raw[-8000:],
        )
    )


@pytest.mark.synthetic
@pytest.mark.waveform
@pytest.mark.axi
@pytest.mark.vip
@pytest.mark.regression
@pytest.mark.slow
def test_axi_vip_real_waveform_actions(
    command_runner: CommandRunner,
    repo_root: Path,
    kdebug_root: Path,
    kdebug_bin: Path,
    artifact_root: Path,
) -> None:
    fixture_dir = kdebug_root / "testdata" / "waveform" / "axi_vip_real"
    manifest = json.loads(
        (fixture_dir / "manifest.json").read_text(encoding="utf-8")
    )
    required_env = manifest["required_env"]
    missing = [name for name in required_env if not os.environ.get(name)]
    assert not missing, (
        "AXI VIP fixture requires environment variables: %s"
        % ", ".join(missing)
    )

    result = command_runner.run(
        [
            sys.executable,
            str(kdebug_root / "tests" / "waveform" / "run_complex_wave.py"),
            "--mode",
            "axi",
            "--kdebug",
            str(kdebug_bin),
        ],
        cwd=repo_root,
        timeout_sec=2400,
        metadata={
            "suite": "axi-vip-real",
            "fixture": str(fixture_dir),
            "seed": manifest["seed"],
        },
    )
    _require_success(
        result,
        artifact_root=artifact_root,
        manifest=manifest,
    )

    resources = manifest["resources"]
    fsdb = fixture_dir / resources["fsdb"]
    daidir = fixture_dir / resources["daidir"]
    sim_log = fixture_dir / resources["simulation_log"]
    assert fsdb.is_file() and fsdb.stat().st_size > 0
    assert daidir.is_dir()
    assert sim_log.is_file()

    log_text = sim_log.read_text(encoding="utf-8", errors="replace")
    assert "UVM_ERROR :    0" in log_text
    assert "UVM_FATAL :    0" in log_text
    assert "Master WRITE transactions: 3200" in log_text
    assert "Master READ transactions:  3200" in log_text
    assert "AXI_EXPECTED_TXN_JSON" in log_text
    assert "TEST PASSED - All data comparisons OK" in log_text
    assert "PASS: kdebug complex waveform validation completed" in result.stdout_raw
