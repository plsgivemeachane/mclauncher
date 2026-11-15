# mclauncher

[![CI and release](https://github.com/plsgivemeachane/mclauncher/actions/workflows/ci-release.yml/badge.svg)](https://github.com/plsgivemeachane/mclauncher/actions/workflows/ci-release.yml)

A Qt desktop launcher for installing and playing Minecraft with local offline sessions, isolated instances, and managed Java runtimes.

## Install on Ubuntu 24.04 amd64

Download the `.deb` from [Releases](https://github.com/plsgivemeachane/mclauncher/releases/latest), then install it:

```sh
sudo apt install ./mclauncher_0.1.3_amd64.deb
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

## CI and releases

Pull requests and pushes to `main` run the regression suite, compile checks, and shell syntax checks. After successful checks on `main`, CI reads `__version__` from `src/mclauncher/__init__.py`. If `v<version>` has no GitHub release yet, CI builds the `.deb`, checks its version and architecture, and publishes a release with the package, SHA-256 checksum, and package metadata. The first push publishes the current version automatically.

To release an update, increment `__version__` to a new stable `X.Y.Z` value and push to `main`. Keep released versions immutable. Pushes without a new version run checks and skip packaging. The workflow can also be retried through **Actions → CI and release → Run workflow**; an existing release is skipped.

Build artifacts are also retained in GitHub Actions for 30 days. Release assets remain available from Releases.
