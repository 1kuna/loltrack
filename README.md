LoL Stat-Tracker (Web, v0.5)

Local web app (FastAPI + React) that tracks the League metrics you care about: early-game CS & deaths, lane diffs @10, warding discipline, and recall hygiene — with a live in-game panel and rolling post-game trends.

Quick Start (macOS/Linux)
- Prereqs: Python 3.11+, Node 20+
- Start dev: `scripts/start.sh` (runs Vite on 5173 + FastAPI on 8787)
- Open: http://localhost:5173 (dev) or http://127.0.0.1:8787 (prod)
- Stop: `scripts/stop.sh`

Quick Start (Windows)
- Prereqs: Python 3.11+, Node 20+
- Start dev: `scripts\start.ps1`
- Stop: `scripts\stop.ps1`

On first run
- Go to Settings → paste Riot API key (dev key) and Riot ID (GameName#TAG)
- Click Dashboard → if empty, click Sync in Settings or run `POST /api/sync/pull?since=7d`

CLI (legacy)
- The repo still ships a CLI for power users:
  - `pip install -e .`
  - `loltrack auth --riot-id "Game#TAG"`
  - `loltrack pull --since 7d && loltrack dash`

Config
- Server-side YAML at OS-specific path:
  - Windows: %APPDATA%/loltrack/config.yaml
  - macOS: ~/Library/Application Support/loltrack/config.yaml
  - Linux: ~/.config/loltrack/config.yaml

Notes
- Live Client API is at https://127.0.0.1:2999 (self-signed). The backend disables SSL verification for this localhost endpoint only.
- Data is stored locally in SQLite with rolling windows cached for quick dashboards.
