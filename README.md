# mclauncher

[![CI](https://github.com/plsgivemeachane/mclauncher/actions/workflows/ci.yml/badge.svg)](https://github.com/plsgivemeachane/mclauncher/actions/workflows/ci.yml)

A Qt desktop launcher for installing and playing Minecraft with local offline sessions, isolated instances, and managed Java runtimes.

## Install on Ubuntu 24.04 amd64

Build the `.deb` with the [packaging instructions](packaging/README.md), then install it:

```sh
sudo apt install "./dist/mclauncher_<version>_amd64.deb"
```

Minecraft and Java are downloaded when you press **Play** for a version that needs preparation. They are not bundled in the launcher package.

## Develop

Requires Python 3.11 or newer and a desktop environment with Qt runtime libraries.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e . pytest
mclauncher
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

See [packaging instructions](packaging/README.md) for the supported Ubuntu build environment.

## Control the launcher from an AI assistant (MCP)

`mclauncher-mcp` is an [MCP](https://modelcontextprotocol.io) server that lets an assistant such as Claude Code create instances, install Minecraft versions, import Modrinth `.mrpack` / CurseForge `.zip` modpacks, launch and stop the game, and read game logs. It runs headless against the same data folder as the desktop app, so both can be open at once; the desktop app shows new instances after a restart.

```sh
python -m pip install -e '.[mcp]'
claude mcp add mclauncher -- "$PWD/.venv/bin/mclauncher-mcp"
```

This repository also ships a project `.mcp.json`, so Claude Code started here offers the server automatically. For an HTTP endpoint instead of stdio, run `mclauncher-mcp --transport streamable-http --port 8765` (binds to `127.0.0.1`; there is no authentication, so do not expose it to a network). Installs and imports run as background jobs: tools return a job id to poll with `get_job`.

## Audit journal

Everything the launcher changes is appended to `~/.local/share/mclauncher/audit.jsonl`, one JSON event per line. Each event records the time, the `source` (`app`, `mcp`, or `control`), the process id, and the `action`:

- `state_change`: a field-level before/after diff of every `state.json` save (settings, instances added, renamed, changed, or removed)
- `delete_instance`: the instance record plus an inventory of its folder (worlds, mods, backups, file count, bytes), written before the folder is removed
- `import_local_mod`, `toggle_mod`, `remove_mod`, `duplicate_instance`: file-level mod and instance operations
- `game_launch`, `game_stop`, `game_exit`: process id, username, memory, exit code
- `pack_update_backed_up`, `pack_update_applied`, `pack_update_failed`, `pack_update_rollback_failed`, `pack_update_recover`: modpack update lifecycle
- `job_started`, `job_finished`, `mcp_call`: background jobs and every MCP tool call, refused ones included (successful status polls are skipped)
- `app_start`, `app_close`, `state_load_failed`, `state_recover_defaults`

The journal lives outside `instances/`, so it survives instance deletion. When it reaches 20 MB it is renamed to `audit-<timestamp>.jsonl`, and the launcher never deletes old journals. Each instance's `logs/minecraft.log` also gets a marker line at every launch and exit. To read the timeline:

```sh
jq -c '[.ts, .source, .action, (.name // .instance_id // .tool)]' ~/.local/share/mclauncher/audit*.jsonl
```

## CI

Pull requests and pushes to `main` run the regression suite, compile checks, and shell syntax checks. CI does not build or publish packages; build them locally with the [packaging instructions](packaging/README.md).
