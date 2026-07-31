"""`wiki config` — read/write workspace configuration (#367).

One generic pair of subcommands over ``_CONFIG_KEYS`` instead of a command per
flag: every config the API can PATCH is reachable from the CLI the day it is
added. Storage is the same ``~/.wiki/config.yaml`` the API writes, so a value
set here is what ``GET /config`` returns.
"""

from __future__ import annotations

import json

import typer

from ....core.config import _CONFIG_KEYS
from ....core.paths import load_active_brain
from .._errors import EXIT_USAGE, handle_errors
from .._output import emit

config_app = typer.Typer(
    help="Read and write workspace configuration (~/.wiki/config.yaml).",
    no_args_is_help=True,
)


def _check_key(key: str) -> None:
    if key in _CONFIG_KEYS:
        return
    valid = ", ".join(sorted(_CONFIG_KEYS))
    typer.echo(f"Unknown config key '{key}'. Valid keys: {valid}", err=True)
    raise typer.Exit(code=EXIT_USAGE)


@config_app.command("get")
@handle_errors
def config_get(
    key: str | None = typer.Argument(None, help="Config key. Omit to dump every key."),
    as_json: bool = typer.Option(False, "--json", help="Emit a JSON object on stdout."),
) -> None:
    """Show one config value, or all of them."""
    from ....core.config import load_config

    cfg = load_config(load_active_brain())
    data = cfg.model_dump(mode="json")
    if key is None:
        selected = {k: data[k] for k in _CONFIG_KEYS if k in data}
    else:
        _check_key(key)
        selected = {key: data[key]}

    def human() -> None:
        for k, v in selected.items():
            typer.echo(f"{k} = {json.dumps(v, ensure_ascii=False)}")

    emit(selected, as_json=as_json, human=human)


@config_app.command("set")
@handle_errors
def config_set(
    key: str = typer.Argument(..., help="Config key."),
    value: str = typer.Argument(
        ...,
        help="Value. Parsed as JSON when possible (2048, null, '{\"ingest\": 2048}'), "
        "otherwise kept as a string.",
    ),
) -> None:
    """Set a config value, validating it against the config model first."""
    from pydantic import ValidationError

    from ....core.config import WorkspaceConfig, _read_global_config, load_config, update_config

    _check_key(key)
    try:
        parsed: object = json.loads(value)
    except json.JSONDecodeError:
        parsed = value  # bare strings ("rag", "ollama:llama3") aren't valid JSON

    paths = load_active_brain()
    try:
        WorkspaceConfig.model_validate(
            {**_read_global_config(), key: parsed, "brain_root": paths.root}
        )
    except ValidationError as exc:
        first = exc.errors()[0]
        typer.echo(f"Invalid value for '{key}': {first['msg']}", err=True)
        raise typer.Exit(code=EXIT_USAGE) from None

    try:
        update_config({key: parsed})
    except ValueError as exc:  # write-path guards, e.g. non-positive cap (#370)
        typer.echo(f"Invalid value for '{key}': {exc}", err=True)
        raise typer.Exit(code=EXIT_USAGE) from None
    typer.echo(f"{key} = {json.dumps(load_config(paths).model_dump(mode='json')[key])}")
