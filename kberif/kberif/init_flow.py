from __future__ import annotations

import shlex
import subprocess
import sys
import time
from pathlib import Path

from .cards import init_state, reconcile_detail_metadata, update_catalog, validate_all
from .errors import VALIDATION_FAILED, KberifError
from .io import read_toml, write_json, write_text
from .manifest import write_manifest
from .paths import config_dir, state_dir
from .prompt import render_prompt


def _kberif_command() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    wrapper = repo_root / "tools" / "kberif"
    if wrapper.exists():
        return shlex.quote(str(wrapper))
    return f"{shlex.quote(sys.executable)} -m kberif"


def _write_claude_hook_settings(root: Path) -> Path:
    settings_path = state_dir(root) / "raw" / "claude-settings.json"
    kberif = _kberif_command()
    write_json(
        settings_path,
        {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Write|Edit",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"{kberif} hook validate-write",
                                "timeout": 30,
                            }
                        ],
                    }
                ],
                "Stop": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"{kberif} hook validate-stop",
                                "timeout": 120,
                            }
                        ],
                    }
                ],
            },
        },
    )
    return settings_path


def _write_claude_guard_settings_fragment(root: Path) -> Path:
    settings_path = state_dir(root) / "raw" / "claude-kberif-guard-settings.json"
    kberif = _kberif_command()
    write_json(
        settings_path,
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Read|Write|Edit|MultiEdit|NotebookEdit|Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"{kberif} hook guard-state-access",
                                "timeout": 10,
                            }
                        ],
                    }
                ]
            }
        },
    )
    return settings_path


def initialize(root: Path, model: str) -> None:
    kind_cfg = read_toml(config_dir(root) / "kind.toml")
    topics_cfg = read_toml(config_dir(root) / "topics.toml")
    kind = kind_cfg["env_kind"]
    command = kind_cfg.get("agent", {}).get("command", "claudecode -p")
    args = shlex.split(command)
    command_name = Path(args[0]).name if args else ""
    if not args:
        raise KberifError(VALIDATION_FAILED, "agent.command is empty")
    if "--model" in args:
        raise KberifError(VALIDATION_FAILED, "agent.command must not specify --model; use kberif init --model")
    if command_name in {"claude", "claudecode"}:
        args.extend(["--model", model])

    sdir = state_dir(root)
    write_json(sdir / "kind.json", {"schema_version": "kberif.kind_state.v1", "env_kind": kind})
    manifest = write_manifest(root, kind, kind_cfg)
    init_state(root, kind)
    prompt = render_prompt(root, kind_cfg, topics_cfg, manifest)
    write_text(sdir / "raw" / "prompt.md", prompt)
    hook_settings = _write_claude_hook_settings(root)

    log_path = sdir / "raw" / "session.log"
    if command_name == "claude":
        args.extend(["--settings", str(hook_settings)])
    with log_path.open("w", encoding="utf-8") as log:
        try:
            proc = subprocess.run(
                args,
                input=prompt,
                text=True,
                cwd=str(root),
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        except FileNotFoundError as exc:
            raise KberifError(VALIDATION_FAILED, f"agent command not found: {args[0]}") from exc
    if proc.returncode != 0:
        raise KberifError(VALIDATION_FAILED, f"agent command failed with exit code {proc.returncode}")

    reconcile_detail_metadata(root)
    update_catalog(root)
    errors = validate_all(root)
    if errors:
        raise KberifError(VALIDATION_FAILED, "; ".join(errors))
    guard_settings = _write_claude_guard_settings_fragment(root)
    write_json(
        sdir / "lock.json",
        {
            "schema_version": "kberif.lock.v1",
            "env_kind": kind,
            "created_at": int(time.time()),
            "manifest_sha256": manifest["files"][0]["sha256"] if manifest.get("files") else "",
        },
    )
    print(f"kberif Claude guard settings fragment: {guard_settings}")
