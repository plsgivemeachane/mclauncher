# Ticket 07 package acceptance evidence

Snapshot: `43275099a712f2c70ab8516a181833453ecc46fd` (`ticket/launcher-ux-07-package-acceptance`)

## Automated checks

Command:

```sh
TMPDIR=/tmp QT_QPA_PLATFORM=offscreen \
  /tmp/mclauncher-ux-venv/bin/python -m pytest -q
```

Result: `73 passed in 2.70s`.

## Reproducible package build

Command from `packaging/README.md`:

```sh
docker run --rm --platform linux/amd64 -v "$PWD":/src -w /src ubuntu:24.04 \
  sh -eu -c 'apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates dpkg-dev file patchelf python3 python3-venv python3-dev \
    build-essential libgl1 libegl1 libglib2.0-0 libfontconfig1 libdbus-1-3 \
    libx11-6 libxkbcommon0 libxkbcommon-x11-0 libwayland-client0 \
    libwayland-cursor0 libwayland-egl1 libgbm1 libbrotli1 \
    libxcb-cursor0 libxcb-icccm4 libxcb-util1 libxcb-keysyms1 libxcb-image0 \
    libxcb-render-util0 libxcb-shape0 libxcb-randr0 libxcb-xinerama0 \
    libxcb-xkb1 libkrb5-3 libgssapi-krb5-2 && \
    SOURCE_DATE_EPOCH=0 packaging/build-deb.sh'
```

Result: **blocked** while downloading the pinned `pyside6_addons-6.12.0` wheel
(`2.6 MB/59.2 MB`, `Connection timed out`, `incomplete-download`). The clean
attempt produced no new `.deb`; the full log is retained at
`/tmp/mclauncher-ux-07-evidence/docker-build.txt`.

## Available artifact inspection (fallback only)

The shared repository contained a pre-existing artifact, not produced by the
failed build above:

```text
dist/mclauncher_0.1.0_amd64.deb
sha256 304b83ef03b02316b74aa6840d84609b5f5ee3ffb599c695e2c387dd0a253dfb
size 44064956 bytes
architecture amd64
Build Python 3.12.3
PySide6 6.12.0
minecraft-launcher-lib 8.0
Source date epoch 0
```

`dpkg-deb --info` showed runtime library dependencies only; no Python or Java
dependency is declared. The package contains the frozen ELF launcher,
`minecraft_launcher_lib/version.txt`, build metadata, and the desktop entry.
The desktop entry has:

```text
Exec=/usr/bin/mclauncher
TryExec=/usr/bin/mclauncher
```

The frozen executable is ELF64 x86-64 and `ldd` resolves only native system
libraries plus bundled `libexpat`; no Python or Java runtime is bundled or
required by the executable.

## GUI smoke

The extracted frozen executable from the fallback artifact was run under host
Xvfb:

```sh
HOME=/tmp/mclauncher-ux-07-package-home QT_QPA_PLATFORM=xcb \
  xvfb-run -a -s '-screen 0 1280x800x24' timeout 12s \
  /tmp/mclauncher-ux-07-package-files/usr/lib/mclauncher/mclauncher
```

Result: exit `124` from `timeout`; the process stayed alive for the full 12
seconds. No GUI crash output was emitted. This is a frozen-binary smoke, not
proof of desktop-entry execution from an installed Ubuntu 24.04 system.

## Unresolved package acceptance gaps

- A fresh Ubuntu 24.04 amd64 build from this snapshot is unproven because the
  pinned wheel download timed out.
- Installation through `apt install ./dist/mclauncher_0.1.0_amd64.deb` in a
  clean Ubuntu 24.04 container was attempted, but the container stalled while
  fetching the 58.5 MB Xvfb test dependencies. No clean-container install
  verdict is claimed.
- The host-Xvfb smoke cannot prove the complete desktop integration, real
  Minecraft download, Java runtime, world save, disconnected reopen, or
  graphics acceptance journey. Those remain ticket 07 manual acceptance work.
