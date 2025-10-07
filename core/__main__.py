from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.prompt import Confirm

from .config import (
    get_config,
    save_config,
    ensure_paths,
    config_path,
    open_config_in_editor,
    get_api_key,
    set_api_key,
)
from .store import Store
from .riot import RiotClient
from .live import LiveClient
from .dashboards import render_live_panel, render_dashboard
from .metrics import ingest_and_compute_recent
from .windows import rebuild_windows


app = typer.Typer(add_completion=False, no_args_is_help=True, help="LoL CLI Stat-Tracker")
console = Console()


@app.callback()
def main_callback() -> None:
    ensure_paths()


@app.command()
def auth(
    riot_id: Optional[str] = typer.Option(None, help="Riot ID as GameName#TAG"),
    api_key: Optional[str] = typer.Option(None, help="Riot API key (overrides env/keyring)"),
):
    """Set Riot key and Riot ID; resolve PUUID and save config."""
    cfg = get_config()
    if api_key:
        set_api_key(api_key)
        rprint("[green]Saved API key to keyring.[/green]")
    else:
        key = get_api_key()
        if not key:
            rprint("[yellow]No API key found. You can pass --api-key or set RIOT_API_KEY.[/yellow]")
            raise typer.Exit(code=1)

    if riot_id:
        cfg["player"]["riot_id"] = riot_id
        save_config(cfg)

    riot_id = cfg["player"].get("riot_id")
    if not riot_id:
        rprint("[red]riot_id not set. Pass --riot-id or run `loltrack config edit`.[/red]")
        raise typer.Exit(code=1)

    rc = RiotClient.from_config(cfg)
    game, tag = riot_id.split("#", 1)
    account = rc.resolve_account(game, tag)
    cfg["player"]["puuid"] = account["puuid"]
    save_config(cfg)
    rprint(f"[green]PUUID resolved and saved:[/green] {account['puuid']}")


@app.command()
def live():
    cfg = get_config()
    live_client = LiveClient()
    with console.screen():
        for panel, stop in render_live_panel(live_client, cfg):
            console.print(panel)
            if stop:
                break


@app.command()
def pull(
    since: Optional[str] = typer.Option(None, help="Since filter: e.g. 7d, 2024-01-01"),
    count: int = typer.Option(20, help="Max matches to scan on first page"),
    queue: Optional[int] = typer.Option(None, help="Queue filter, e.g. 420 for Ranked Solo"),
):
    cfg = get_config()
    store = Store()
    rc = RiotClient.from_config(cfg)
    puuid = cfg["player"].get("puuid")
    if not puuid:
        rprint("[red]No PUUID; run `loltrack auth` first.[/red]")
        raise typer.Exit(code=1)
    ingested = ingest_and_compute_recent(rc, store, puuid, since=since, count=count, queue_filter=queue or None)
    rprint(f"[green]Ingested[/green] {ingested} matches.")
    rebuild_windows(store, cfg)
    rprint("[green]Windows updated.[/green]")


@app.command()
def dash():
    cfg = get_config()
    store = Store()
    render_dashboard(store, cfg)


@app.command()
def config(
    action: str = typer.Argument("show", help="show|edit|path"),
):
    if action == "show":
        rprint(Path(config_path()).read_text())
    elif action == "path":
        rprint(config_path())
    elif action == "edit":
        opened = open_config_in_editor()
        if not opened:
            rprint("[yellow]Could not open editor. Edit the file manually:[/yellow]")
            rprint(config_path())
    else:
        rprint("[red]Unknown action. Use show|edit|path[/red]")


@app.command()
def rebuild():
    cfg = get_config()
    store = Store()
    rebuild_windows(store, cfg)
    rprint("[green]Windows rebuilt.[/green]")


@app.command()
def doctor():
    cfg = get_config()
    store = Store()
    ok = True
    rprint("[bold]Config[/bold]", config_path())
    if not Path(config_path()).exists():
        rprint("[red]Missing config file[/red]")
        ok = False
    key = get_api_key()
    if key:
        rprint("[green]API key present[/green]")
    else:
        rprint("[yellow]No API key found (set RIOT_API_KEY or run auth).[/yellow]")
    db_path = store.db_path
    rprint("[bold]DB[/bold]", db_path)
    if Path(db_path).exists():
        rprint("[green]DB present[/green]")
    else:
        rprint("[yellow]DB will be created on first run[/yellow]")
    # Live client reachability
    live_client = LiveClient()
    try:
        status = live_client.status()
        rprint(f"[green]Live client reachable[/green]: {status}")
    except Exception as e:
        rprint(f"[yellow]Live client not reachable[/yellow]: {e}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    app()

