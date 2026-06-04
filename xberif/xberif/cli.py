from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from .errors import VALIDATION_FAILED, XberifError

app = typer.Typer(no_args_is_help=True)
config_app = typer.Typer(no_args_is_help=True)
card_app = typer.Typer(no_args_is_help=True)
agent_app = typer.Typer(no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(card_app, name="card")
app.add_typer(agent_app, name="agent")
console = Console()


def _root(output: Optional[Path] = None) -> Path:
    return (output or Path.cwd()).resolve()


def _run(fn):
    try:
        return fn()
    except XberifError as exc:
        console.print(f"error: {exc.message}")
        raise typer.Exit(1)


@config_app.command("init")
def config_init(
    kind: str = typer.Option(..., "--kind"),
    force: bool = typer.Option(False, "--force"),
    merge: bool = typer.Option(False, "--merge"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    output: Optional[Path] = typer.Option(None, "--output"),
) -> None:
    from .config import init_config

    def work():
        files = init_config(_root(output), kind, force=force, merge=merge, dry_run=dry_run)
        for path in files:
            console.print(path)

    _run(work)


@app.command("init")
def init_cmd(model: str = typer.Option(..., "--model")) -> None:
    from .init_flow import initialize

    _run(lambda: initialize(Path.cwd(), model))


@app.command("validate")
def validate_cmd(all_: bool = typer.Option(False, "--all")) -> None:
    from .cards import validate_all

    del all_

    def work():
        errors = validate_all(Path.cwd())
        if errors:
            for err in errors:
                console.print(f"error: {err}")
            raise XberifError(VALIDATION_FAILED, "validation failed")
        console.print("ok")

    _run(work)


@app.command("status")
def status_cmd() -> None:
    from .query import status

    _run(lambda: console.print_json(data=status(Path.cwd())))


@app.command("repair-catalog")
def repair_catalog_cmd() -> None:
    from .cards import repair_catalog

    def work():
        catalog = repair_catalog(Path.cwd())
        console.print_json(data={"ok": True, "catalog_card_count": len(catalog.get("cards", []))})

    _run(work)


@app.command("list-topics")
def list_topics_cmd() -> None:
    from .query import list_topics

    _run(lambda: console.print_json(data=list_topics(Path.cwd())))


@app.command("get")
def get_cmd(topic: str, detail: bool = typer.Option(False, "--detail")) -> None:
    from .query import get_topic, get_topic_detail

    if detail:
        _run(lambda: console.print(get_topic_detail(Path.cwd(), topic)["content"], end=""))
    else:
        _run(lambda: console.print_json(data=get_topic(Path.cwd(), topic)))


@app.command("detail")
def detail_cmd(
    topic_or_action: str,
    topic: Optional[str] = typer.Argument(None),
    stdin: bool = typer.Option(False, "--stdin"),
) -> None:
    from .cards import upsert_detail
    from .query import get_topic_detail

    if topic_or_action == "upsert":
        if topic is None or not stdin:
            raise typer.BadParameter("detail upsert requires <topic> --stdin")
        _run(lambda: upsert_detail(Path.cwd(), topic, sys.stdin.read()))
        return
    if topic is not None or stdin:
        raise typer.BadParameter("use `detail <topic>` or `detail upsert <topic> --stdin`")
    _run(lambda: console.print(get_topic_detail(Path.cwd(), topic_or_action)["content"], end=""))


@app.command("brief")
def brief_cmd(mode: str = typer.Option(..., "--mode")) -> None:
    from .query import brief as render_brief

    _run(lambda: console.print(render_brief(Path.cwd(), mode), end=""))


@card_app.command("upsert")
def card_upsert(stdin: bool = typer.Option(False, "--stdin")) -> None:
    from .cards import upsert_card

    if not stdin:
        raise typer.BadParameter("only --stdin is supported")

    def work():
        upsert_card(Path.cwd(), json.load(sys.stdin))

    _run(work)


@card_app.command("append-key-items")
def card_append_key_items(card_id: str, stdin: bool = typer.Option(False, "--stdin")) -> None:
    from .cards import append_key_items

    if not stdin:
        raise typer.BadParameter("only --stdin is supported")

    def work():
        key_items = json.load(sys.stdin)
        if not isinstance(key_items, list):
            raise XberifError("CARD_SCHEMA_INVALID", "stdin must be a JSON list")
        append_key_items(Path.cwd(), card_id, key_items)

    _run(work)


@agent_app.command("serve")
def agent_serve(stdio: bool = typer.Option(False, "--stdio"), write: bool = typer.Option(False, "--write")) -> None:
    from .agent import serve_stdio

    if not stdio:
        raise typer.BadParameter("only --stdio is supported")
    serve_stdio(Path.cwd(), write=write)


@app.command("hook", hidden=True)
def hook_cmd(action: str) -> None:
    from .hooks import validate_card_write, validate_stop

    if action == "validate-write":
        raise typer.Exit(validate_card_write())
    if action == "validate-stop":
        raise typer.Exit(validate_stop())
    raise typer.BadParameter("unknown hook action")


def _shortcut(namespace: str, topic: str) -> None:
    from .query import check_namespace, get_topic

    def work():
        root = Path.cwd()
        check_namespace(root, namespace)
        console.print_json(data=get_topic(root, topic.replace("-", "_")))

    _run(work)


@app.command("bt")
def bt_cmd(topic: str) -> None:
    _shortcut("bt", topic)


@app.command("it")
def it_cmd(topic: str) -> None:
    _shortcut("it", topic)


@app.command("st")
def st_cmd(topic: str) -> None:
    _shortcut("st", topic)


@app.command("soc")
def soc_cmd(topic: str) -> None:
    _shortcut("soc", topic)


@app.command("bootstrap-state", hidden=True)
def bootstrap_state() -> None:
    """Testing helper: scan manifest and initialize empty state without invoking AI."""

    from .cards import init_state
    from .io import read_toml, write_json
    from .manifest import write_manifest
    from .paths import state_dir

    def work():
        root = Path.cwd()
        cfg = read_toml(root / "xberif" / "kind.toml")
        kind = cfg["env_kind"]
        write_json(state_dir(root) / "kind.json", {"schema_version": "xberif.kind_state.v1", "env_kind": kind})
        write_manifest(root, kind, cfg)
        init_state(root, kind)

    _run(work)
