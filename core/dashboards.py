from __future__ import annotations

import time
from typing import Any, Dict, Generator, Tuple

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich.console import Group
from rich.console import Console

from .live import LiveClient
from .store import Store
from .windows import rebuild_windows


def render_live_panel(live: LiveClient, cfg: Dict[str, Any]) -> Generator[Tuple[Panel, bool], None, None]:
    palette = cfg["render"]["palette"]
    accent = palette.get("accent", "cyan")
    ok_c = palette.get("ok", "green")
    warn_c = palette.get("warn", "yellow")
    bad_c = palette.get("bad", "red")

    # Attempt to poll in a small loop; yield frames
    last_t = None
    while True:
        try:
            data = live.allgamedata()
        except Exception:
            msg = Text("Waiting for match (Live Client API not available)", style=warn_c)
            yield Panel(msg, title="LIVE", box=box.ROUNDED), True
            return

        gd = data.get("gameData", {})
        t = gd.get("gameTime", 0.0)
        champ = data.get("activePlayer", {}).get("championName", "?")
        role = "?"
        # Playerlist may have positions but live client doesn't expose role reliably
        # We'll leave role unknown in live for now.

        # Early stats
        scores = data.get("activePlayer", {}).get("scores", {})
        cs_now = int(scores.get("creepScore") or 0)
        deaths = int(scores.get("deaths") or 0)
        csmin = cs_now / max(t / 60.0, 1e-6)

        # Targets (very rough placeholders until baseline/targets computed)
        target_cs10 = cfg.get("metrics", {}).get("targets", {}).get("CS10", {}).get("manual_floor", 60)
        # Estimate projected CS@10 from current rate
        proj_cs10 = int(csmin * 10)
        cs10_delta = proj_cs10 - target_cs10
        cs10_color = ok_c if cs10_delta >= 0 else (warn_c if cs10_delta >= -5 else bad_c)

        dl_ok = deaths == 0 and t < 14 * 60
        dl_text = Text("DL14: ", style=accent) + Text("on track" if dl_ok else "failed" if t >= 14*60 else "?", style=(ok_c if dl_ok else bad_c))

        targets = Table.grid(expand=True)
        targets.add_column(ratio=1)
        targets.add_column(ratio=2)
        targets.add_row(
            Text(f"CS@10: {proj_cs10} (target ≥ {target_cs10})", style=cs10_color),
            Text(f"CS/min: {csmin:.2f}  Deaths: {deaths}", style=accent),
        )

        header = Text.assemble(
            (" LIVE ", "bold white on black"),
            ("  |  ", accent),
            (f"Game {int(t//60):02d}:{int(t%60):02d}", accent),
            ("  |  ", accent),
            (f"Champ: {champ}", accent),
        )

        group = Group(header, dl_text, targets)
        panel = Panel(group, box=box.ROUNDED)

        yield panel, False
        time.sleep(1)
        # Detect end (time stops advancing)
        if last_t is not None and t <= last_t:
            # one extra frame then stop
            yield Panel(Text("Match ended. Syncing post-game soon...", style=accent), box=box.ROUNDED), True
            return
        last_t = t


def render_dashboard(store: Store, cfg: Dict[str, Any]) -> None:
    puuid = cfg["player"].get("puuid")
    if not puuid:
        Console().print("[red]No PUUID configured. Run `loltrack auth`.[/red]")
        return
    queue = (cfg["player"].get("track_queues") or [None])[0]
    key = f"puuid:{puuid}:queue:{queue or 'any'}"

    # Ensure windows present
    rebuild_windows(store, cfg)

    with store.connect() as con:
        rows = con.execute(
            "SELECT metric, window_type, window_value, value, n, trend, spark FROM windows WHERE key=? ORDER BY metric, window_type, window_value",
            (key,),
        ).fetchall()

    console = Console()
    if not rows:
        console.print("[yellow]No window data yet. Run `loltrack pull --since 30d`.[/yellow]")
        return

    table = Table(title="DASH | Windows", box=box.ROUNDED)
    table.add_column("Metric")
    table.add_column("5 games", justify="right")
    table.add_column("10 games", justify="right")
    table.add_column("30 days", justify="right")
    table.add_column("Trend", justify="left")

    # Aggregate rows into a display-friendly shape
    metrics = cfg["metrics"]["primary"]
    by_metric: Dict[str, Dict[Tuple[str, int], Any]] = {}
    for r in rows:
        by_metric.setdefault(r[0], {})[(r[1], int(r[2]))] = r

    for m in metrics:
        r5 = by_metric.get(m, {}).get(("count", 5))
        r10 = by_metric.get(m, {}).get(("count", 10))
        r30d = by_metric.get(m, {}).get(("days", 30))
        val5 = f"{r5[3]:.1f} ({int(r5[4])})" if r5 else "-"
        val10 = f"{r10[3]:.1f} ({int(r10[4])})" if r10 else "-"
        val30d = f"{r30d[3]:.1f} ({int(r30d[4])})" if r30d else "-"
        trend = (r10[6] if r10 else "")
        table.add_row(m, val5, val10, val30d, trend)

    console.print()
    console.print(table)
