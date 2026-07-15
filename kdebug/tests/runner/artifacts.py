from __future__ import annotations

import difflib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .cli import RunResult


_SENSITIVE_ENV = re.compile(r"(TOKEN|PASSWORD|PASSWD|SECRET|API_KEY|PRIVATE_KEY)")


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or "case"


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def redact_env(env: Mapping[str, str]) -> Dict[str, str]:
    return {
        key: "<redacted>" if _SENSITIVE_ENV.search(key.upper()) else value
        for key, value in sorted(env.items())
    }


class ArtifactWriter:
    def __init__(self, root: Path, run_id: Optional[str] = None) -> None:
        self.root = Path(root)
        self.run_id = run_id or time.strftime("%Y%m%d-%H%M%S")

    def write(
        self,
        case_name: str,
        result: RunResult,
        *,
        expected: Any = None,
        manifest: Any = None,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> Path:
        case_dir = self.root / self.run_id / _safe_name(case_name)
        case_dir.mkdir(parents=True, exist_ok=True)

        (case_dir / "command.json").write_text(
            _json_text({"argv": result.command, "cwd": result.cwd}),
            encoding="utf-8",
        )
        (case_dir / "env.json").write_text(
            _json_text(redact_env(result.env)), encoding="utf-8"
        )
        (case_dir / "request.json").write_text(
            _json_text(result.request), encoding="utf-8"
        )
        (case_dir / "stdout.raw").write_text(result.stdout_raw, encoding="utf-8")
        (case_dir / "stderr.raw").write_text(result.stderr_raw, encoding="utf-8")
        (case_dir / "response.normalized.json").write_text(
            _json_text(result.normalized_response), encoding="utf-8"
        )
        (case_dir / "summary.json").write_text(
            _json_text(
                {
                    "returncode": result.returncode,
                    "elapsed_ms": result.elapsed_ms,
                    "timed_out": result.timed_out,
                    "ok": result.ok,
                    "metadata": result.metadata,
                }
            ),
            encoding="utf-8",
        )

        if result.envelope is not None:
            (case_dir / "envelope.json").write_text(
                _json_text(result.envelope), encoding="utf-8"
            )
        if expected is not None:
            expected_text = _json_text(expected)
            actual_text = _json_text(result.normalized_response)
            (case_dir / "expected.json").write_text(expected_text, encoding="utf-8")
            diff = "".join(
                difflib.unified_diff(
                    expected_text.splitlines(True),
                    actual_text.splitlines(True),
                    fromfile="expected",
                    tofile="actual",
                )
            )
            (case_dir / "diff.txt").write_text(diff, encoding="utf-8")
        if manifest is not None:
            if isinstance(manifest, Path):
                manifest_text = manifest.read_text(encoding="utf-8")
            else:
                manifest_text = _json_text(manifest)
            (case_dir / "manifest.yaml").write_text(
                manifest_text, encoding="utf-8"
            )
        for name, value in (extra or {}).items():
            path = case_dir / _safe_name(name)
            if isinstance(value, (dict, list)):
                path.with_suffix(".json").write_text(
                    _json_text(value), encoding="utf-8"
                )
            else:
                path.with_suffix(".txt").write_text(str(value), encoding="utf-8")
        return case_dir
