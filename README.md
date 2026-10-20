# mclauncher

[![CI and release](https://github.com/plsgivemeachane/mclauncher/actions/workflows/ci-release.yml/badge.svg)](https://github.com/plsgivemeachane/mclauncher/actions/workflows/ci-release.yml)

A Qt desktop launcher for installing and playing Minecraft with local offline sessions, isolated instances, and managed Java runtimes.

## Install on Ubuntu 24.04 amd64

Download the `.deb` from [Releases](https://github.com/plsgivemeachane/mclauncher/releases/latest), then install it:

```sh
sudo apt install ./mclauncher_0.1.1_amd64.deb
```

Minecraft and Java are downloaded when you choose **Install Minecraft**. They are not bundled in the launcher package.

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

## CI and releases

Pull requests and pushes to `main` run the regression suite, compile checks, and shell syntax checks. After successful checks on `main`, CI reads `__version__` from `src/mclauncher/__init__.py`. If `v<version>` has no GitHub release yet, CI builds the `.deb`, checks its version and architecture, and publishes a release with the package, SHA-256 checksum, and package metadata. The first push publishes the current version automatically.

To release an update, increment `__version__` to a new stable `X.Y.Z` value and push to `main`. Keep released versions immutable. Pushes without a new version run checks and skip packaging. The workflow can also be retried through **Actions → CI and release → Run workflow**; an existing release is skipped.

Build artifacts are also retained in GitHub Actions for 30 days. Release assets remain available from Releases.
