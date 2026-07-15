from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from kberif.agent import handle
from kberif.cards import reconcile_detail_metadata, repair_catalog, update_catalog, validate_all
from kberif.cli import app
from kberif.errors import WRITE_DISABLED, KberifError
from kberif.hooks import guard_state_access, validate_card_write
from kberif.init_flow import _write_claude_guard_settings_fragment, _write_claude_hook_settings, initialize
from kberif.io import read_json, read_toml, write_json, write_toml
from kberif.query import status
from kberif.templates import KINDS, template_prompt_path, topics_for

runner = CliRunner()


def bootstrap_bt(tmp_path: Path) -> None:
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "req_arb.sv").write_text(
        "module req_arb;\nassign req_ready = !req_fifo_full;\nendmodule\n",
        encoding="utf-8",
    )
    assert runner.invoke(app, ["config", "init", "--kind", "bt"], catch_exceptions=False).exit_code == 0
    assert runner.invoke(app, ["bootstrap-state"], catch_exceptions=False).exit_code == 0


def sample_card() -> dict:
    return {
        "schema_version": "kberif.topic_card.v1",
        "id": "bt.backpressure",
        "env_kind": "bt",
        "topic": "backpressure",
        "title": "Backpressure Points",
        "summary": "请求接收受 FIFO 满状态控制；该机制会直接影响吞吐和阻塞调试。",
        "confidence": "medium",
        "key_items": [
            {
                "name": "req_ready_backpressure",
                "one_line": "req_fifo_full 拉高时，req_ready 被拉低以停止新的请求。",
                "confidence": "medium",
                "evidence": [{"path": "rtl/req_arb.sv", "line_start": 1, "line_end": 3}],
            }
        ],
        "detail": {
            "available": True,
            "path": ".kberif/details/bt.backpressure.md",
            "format": "markdown",
            "token_estimate": 0,
            "section_count": 0,
        },
        "notes": [],
        "unknowns": [],
        "generated_by": {"tool": "test", "kberif_version": "0.3.0"},
    }


def sample_card_with_string_evidence() -> dict:
    card = sample_card()
    card["key_items"][0]["evidence"] = ["rtl/req_arb.sv:1-3"]
    return card


def sample_detail(topic: str = "backpressure", card_id: str = "bt.backpressure") -> str:
    return f"""---
schema_version: kberif.topic_detail.v1
env_kind: bt
topic: {topic}
card_id: {card_id}
title: Backpressure Points
confidence: medium
---

# Backpressure Points

## 结论摘要

请求接收由 ready 控制，FIFO 满时向上游施加反压。

## 关键路径

upstream request -> req_ready -> request fifo -> issue path

## 关键项详解

req_fifo_full 使 req_ready 拉低，阻止新的事务进入。

## 验证与 Debug 提示

观察 full 和 ready 的因果关系并检查停顿解除行为。

## 相关 Topic

fifos、checker。

## 未确认信息

未确认是否存在额外 credit 反压。

## Evidence

- rtl/req_arb.sv:1-3 - req_ready 由 FIFO full 状态约束。
"""


def test_bt_config_init_and_no_state(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["config", "init", "--kind", "bt"], catch_exceptions=False)
    assert result.exit_code == 0
    assert (tmp_path / "kberif" / "kind.toml").exists()
    prompt = (tmp_path / "kberif" / "prompts" / "backpressure.md").read_text(encoding="utf-8")
    assert "总结 block 中所有反压点" in prompt
    assert "summary 应该短而明确，概括该 topic 的结论" in prompt
    assert (tmp_path / "kberif" / "views" / "debug.toml").exists()
    assert not (tmp_path / ".kberif").exists()


def test_builtin_prompt_templates_cover_all_topics():
    for kind in KINDS:
        for _topic, _title, prompt, _required in topics_for(kind):
            text = template_prompt_path(kind, prompt).read_text(encoding="utf-8")
            assert "summary 应该短而明确，概括该 topic 的结论" in text
            assert "card summary 应该写出可独立阅读的概要理解" not in text
            assert "detail markdown 应展开" in text


def test_bt_card_detail_query_brief_rpc_and_namespace(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bootstrap_bt(tmp_path)
    assert (tmp_path / ".kberif" / "details").is_dir()
    assert runner.invoke(
        app, ["card", "upsert", "--stdin"], input=json.dumps(sample_card()), catch_exceptions=False
    ).exit_code == 0
    assert runner.invoke(
        app, ["detail", "upsert", "backpressure", "--stdin"], input=sample_detail(), catch_exceptions=False
    ).exit_code == 0
    catalog = read_json(tmp_path / ".kberif" / "cards.json")
    entry = catalog["cards"][0]
    assert entry["key_item_count"] == 1
    assert entry["detail_available"] is True
    assert entry["detail_token_estimate"] > 0

    get_result = runner.invoke(app, ["get", "backpressure"], catch_exceptions=False)
    assert "req_ready_backpressure" in get_result.output
    assert "关键路径" not in get_result.output
    detail_result = runner.invoke(app, ["detail", "backpressure"], catch_exceptions=False)
    assert "## 关键路径" in detail_result.output
    assert "## 关键路径" in runner.invoke(app, ["get", "backpressure", "--detail"], catch_exceptions=False).output

    write_toml(
        tmp_path / "kberif" / "views" / "debug.toml",
        {"schema_version": "kberif.view.v1", "env_kind": "bt", "mode": "debug", "topics": ["backpressure"]},
    )
    brief = runner.invoke(app, ["brief", "--mode", "debug"], catch_exceptions=False).output
    assert "请求接收受 FIFO 满状态控制" in brief
    assert "Detail: `kberif detail backpressure`" in brief
    assert "## 关键路径" not in brief

    rpc_topic = handle(tmp_path, {"id": 1, "method": "kberif.get_topic", "params": {"topic": "backpressure"}})
    assert rpc_topic["result"]["detail_method"] == "kberif.get_topic_detail"
    rpc_detail = handle(
        tmp_path, {"id": 2, "method": "kberif.get_topic_detail", "params": {"topic": "backpressure"}}
    )
    assert rpc_detail["result"]["evidence"][0]["path"] == "rtl/req_arb.sv"
    rpc_brief = handle(tmp_path, {"id": 3, "method": "kberif.brief", "params": {"mode": "debug"}})
    assert rpc_brief["result"]["schema_version"] == "kberif.brief.v1"

    soc_result = runner.invoke(app, ["soc", "boot-flow"], catch_exceptions=False)
    assert soc_result.exit_code == 1
    assert 'current env_kind is "bt"; command namespace "soc" is unavailable' in soc_result.output


def test_status_repair_catalog_and_string_evidence(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["config", "init", "--kind", "bt"], catch_exceptions=False).exit_code == 0
    write_toml(
        tmp_path / "kberif" / "topics.toml",
        {
            "schema_version": "kberif.topics.v1",
            "env_kind": "bt",
            "topics": {
                "backpressure": {
                    "card_id": "bt.backpressure",
                    "title": "Backpressure Points",
                    "prompt": "kberif/prompts/backpressure.md",
                    "required": True,
                }
            },
        },
    )
    write_toml(
        tmp_path / "kberif" / "views" / "debug.toml",
        {"schema_version": "kberif.view.v1", "env_kind": "bt", "mode": "debug", "topics": ["backpressure"]},
    )
    assert status(tmp_path)["state"] == "configured_only"
    (tmp_path / "rtl").mkdir()
    (tmp_path / "rtl" / "req_arb.sv").write_text(
        "module req_arb;\nassign req_ready = !req_fifo_full;\nendmodule\n",
        encoding="utf-8",
    )
    assert runner.invoke(app, ["bootstrap-state"], catch_exceptions=False).exit_code == 0
    assert status(tmp_path)["state"] == "configured_only"

    card_path = tmp_path / ".kberif" / "cards" / "bt.backpressure.json"
    detail_path = tmp_path / ".kberif" / "details" / "bt.backpressure.md"
    write_json(card_path, sample_card_with_string_evidence())
    detail_path.write_text(sample_detail(), encoding="utf-8")
    write_json(tmp_path / ".kberif" / "cards.json", {"schema_version": "kberif.cards_catalog.v1", "env_kind": "bt", "cards": []})

    st = status(tmp_path)
    assert st["state"] == "generated_raw"
    assert st["next_action"] == "run kberif repair-catalog"
    brief = runner.invoke(app, ["brief", "--mode", "debug"], catch_exceptions=False)
    assert brief.exit_code == 1
    assert "repair-catalog" in brief.output

    catalog = repair_catalog(tmp_path)
    assert len(catalog["cards"]) == 1
    assert status(tmp_path)["state"] == "ready"
    repaired = read_json(card_path)
    assert repaired["key_items"][0]["evidence"] == [{"path": "rtl/req_arb.sv", "line_start": 1, "line_end": 3}]


def test_invalid_card_and_detail_errors(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bootstrap_bt(tmp_path)
    card = sample_card()
    card["summary"] = ""
    assert runner.invoke(app, ["card", "upsert", "--stdin"], input=json.dumps(card), catch_exceptions=False).exit_code == 1
    card = sample_card()
    card["key_items"] = []
    assert runner.invoke(app, ["card", "upsert", "--stdin"], input=json.dumps(card), catch_exceptions=False).exit_code == 1

    assert runner.invoke(
        app, ["card", "upsert", "--stdin"], input=json.dumps(sample_card()), catch_exceptions=False
    ).exit_code == 0
    errors = validate_all(tmp_path)
    assert any("DETAIL_REQUIRED_MISSING" in err for err in errors)
    bad_detail = sample_detail().replace("## Evidence", "## Missing Evidence")
    bad = runner.invoke(app, ["detail", "upsert", "backpressure", "--stdin"], input=bad_detail, catch_exceptions=False)
    assert bad.exit_code == 1
    assert "detail section is missing: Evidence" in bad.output
    mismatched = runner.invoke(
        app,
        ["detail", "upsert", "backpressure", "--stdin"],
        input=sample_detail(topic="credit"),
        catch_exceptions=False,
    )
    assert mismatched.exit_code == 1


def test_init_requires_model_option(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["config", "init", "--kind", "bt"], catch_exceptions=False).exit_code == 0
    result = runner.invoke(app, ["init"], catch_exceptions=False)
    assert result.exit_code != 0
    assert "Missing option '--model'" in result.output
    assert not (tmp_path / ".kberif").exists()


def test_init_adds_model_and_rejects_command_model(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bootstrap_bt(tmp_path)
    cfg_path = tmp_path / "kberif" / "kind.toml"
    cfg = read_toml(cfg_path)
    cfg["agent"]["command"] = "claude -p"
    write_toml(cfg_path, cfg)
    invoked = {}

    def fake_run(args, **kwargs):
        invoked["args"] = args
        return type("Proc", (), {"returncode": 1})()

    monkeypatch.setattr("kberif.init_flow.subprocess.run", fake_run)
    with pytest.raises(KberifError):
        initialize(tmp_path, "opus")
    assert "--model" in invoked["args"]
    assert invoked["args"][invoked["args"].index("--model") + 1] == "opus"

    cfg["agent"]["command"] = "claude -p --model sonnet"
    write_toml(cfg_path, cfg)
    with pytest.raises(KberifError) as exc_info:
        initialize(tmp_path, "opus")
    assert "must not specify --model" in exc_info.value.message


def test_hooks_validate_direct_card_and_detail_write(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    bootstrap_bt(tmp_path)
    settings = read_json(_write_claude_hook_settings(tmp_path))
    validate_write = settings["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    validate_stop = settings["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert "kberif" in validate_write and "hook validate-write" in validate_write
    assert "kberif" in validate_stop and "hook validate-stop" in validate_stop
    guard_settings = read_json(_write_claude_guard_settings_fragment(tmp_path))
    assert "PreToolUse" in guard_settings["hooks"]
    guard_hook = guard_settings["hooks"]["PreToolUse"][0]
    assert guard_hook["matcher"] == "Read|Write|Edit|MultiEdit|NotebookEdit|Bash"
    guard_command = guard_hook["hooks"][0]["command"]
    assert "kberif" in guard_command and "hook guard-state-access" in guard_command
    assert not (tmp_path / ".claude" / "settings.json").exists()

    card_path = tmp_path / ".kberif" / "cards" / "bt.backpressure.json"
    detail_path = tmp_path / ".kberif" / "details" / "bt.backpressure.md"
    write_json(card_path, sample_card())
    detail_path.write_text(sample_detail(), encoding="utf-8")
    for generated_path in (card_path, detail_path):
        monkeypatch.setattr(
            sys,
            "stdin",
            type("Input", (), {"read": lambda self, p=generated_path: json.dumps({"tool_input": {"file_path": str(p)}})})(),
        )
        assert validate_card_write() == 0
    reconcile_detail_metadata(tmp_path)
    update_catalog(tmp_path)
    assert not any("backpressure" in err for err in validate_all(tmp_path) if "CARD_REQUIRED_MISSING" not in err)


def test_guard_state_access_blocks_kberif_file_tools_and_bash(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    (tmp_path / ".kberif").mkdir()

    def run_hook(payload: dict) -> tuple[int, str]:
        monkeypatch.setattr(sys, "stdin", type("Input", (), {"read": lambda self: json.dumps(payload)})())
        rc = guard_state_access()
        return rc, capsys.readouterr().out

    rc, out = run_hook({"tool_name": "Read", "tool_input": {"file_path": ".kberif/cards.json"}})
    assert rc == 0
    result = json.loads(out)
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "kberif status" in result["systemMessage"]

    rc, out = run_hook(
        {"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / "subdir" / ".." / ".kberif" / "cards.json")}}
    )
    assert rc == 0
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"

    rc, out = run_hook({"tool_name": "Bash", "tool_input": {"command": "grep backpressure .kberif/cards.json"}})
    assert rc == 0
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"

    rc, out = run_hook({"tool_name": "Read", "tool_input": {"file_path": "rtl/top.sv"}})
    assert rc == 0
    assert out == ""

    rc, out = run_hook({"tool_name": "Bash", "tool_input": {"command": "echo hello"}})
    assert rc == 0
    assert out == ""


def test_rpc_write_mode_for_card_key_items_and_detail(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bootstrap_bt(tmp_path)
    with pytest.raises(KberifError) as exc_info:
        handle(tmp_path, {"id": 1, "method": "kberif.card.upsert", "params": {"card": sample_card()}})
    assert exc_info.value.code == WRITE_DISABLED
    result = handle(
        tmp_path, {"id": 2, "method": "kberif.card.upsert", "params": {"card": sample_card()}}, write=True
    )
    assert result["result"]["ok"] is True
    result = handle(
        tmp_path,
        {"id": 3, "method": "kberif.detail.upsert", "params": {"topic": "backpressure", "content": sample_detail()}},
        write=True,
    )
    assert result["result"]["ok"] is True
    result = handle(
        tmp_path,
        {
            "id": 4,
            "method": "kberif.card.append_key_items",
            "params": {
                "card_id": "bt.backpressure",
                "key_items": [
                    {
                        "name": "release",
                        "one_line": "FIFO 空闲后 ready 可重新接受请求。",
                        "confidence": "low",
                        "evidence": [{"path": "rtl/req_arb.sv", "line_start": 1, "line_end": 3}],
                    }
                ],
            },
        },
        write=True,
    )
    assert result["result"]["ok"] is True
