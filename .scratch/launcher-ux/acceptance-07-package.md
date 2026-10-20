# Ticket 07 package acceptance evidence

Launcher implementation: `be9b12ef36cc3ae69b57511f0f6d5051f50ceaf9`.
Package version: `0.1.1`, shared by the launcher runtime and Debian build.

## Automated checks

Command:

```sh
TMPDIR=/tmp QT_QPA_PLATFORM=offscreen \
  /tmp/mclauncher-ux-venv/bin/python -m pytest -x -q
```

Result: `80 passed in 3.35s`.

`git diff --check` passed for the package/runtime version changes.

## Clean Ubuntu 24.04 package build

The documented `packaging/build-deb.sh` flow completed in a clean Ubuntu
24.04 amd64 Docker container using `SOURCE_DATE_EPOCH=0`. It produced a fresh
`dist/mclauncher_0.1.1_amd64.deb` from the integrated source above. The project
metadata and Debian builder both read the version from
`src/mclauncher/__init__.py`.

Package identity and build metadata:

```text
Package: mclauncher
Version: 0.1.1
Architecture: amd64
Size: 44,228,406 bytes
SHA-256: cc4891fa7dfb48ab6e57f9e8cd347232b1bce391991b3a97ef1fb251ef6e68c9
Build Python: 3.12.3
Pinned PySide6: 6.12.0
Pinned minecraft-launcher-lib: 8.0
Source date epoch: 0
```

The package build installs a desktop entry declaring `Exec=/usr/bin/mclauncher`
and `TryExec=/usr/bin/mclauncher`. A clean Ubuntu 24.04 amd64 container
successfully installed and opened the 0.1.0 build through that entry without a
separate Python or Java install. The executable stayed alive for a 20-second
Xvfb smoke window; `gtk-launch mclauncher` opened a 920 × 560 Qt window. Its
captured idle screen is
[evidence/07-package-idle-920x560.png](evidence/07-package-idle-920x560.png).

Upgrade detection is verified against the installed 0.1.0 package:
`apt-get -s install ./dist/mclauncher_0.1.1_amd64.deb` reports
`Inst mclauncher [0.1.0] (0.1.1 local-deb [amd64])` and `1 upgraded`.
The built executable contains the `0.1.1` runtime version.

## Superseded package checkpoint (0.1.2, 2026-10-20)

The `0.1.2` package was built before the final Home-screen correction. The
installed screenshot exposed an empty flat-green landscape, news/changelog
content on Home, and a background chooser beside the launch controls. The
artifact was 47,439,448 bytes with SHA-256
`d494c65d2b6f59e6cb1f9c6e758df5a715acc00da07530d841a58597c2249353`. It is
superseded by the verified `0.1.3` package below.

## Current integration checkpoint (0.1.3, 2026-10-20)

The final integrated source is commit `c565de5` on
`integration/launcher-modding`. Version `0.1.3` fixes the packaged-artwork path,
keeps the Home screen free of background controls, and removes the news feed,
changelog, and their startup request. Legacy `news_items` fields remain
readable in saved state.

Full regression suite and whitespace check:

```text
TMPDIR=/tmp .venv/bin/python -m pytest -q --basetemp=/tmp/mclauncher-package-013-tests
157 passed in 7.58s
git diff --check
passed
```

`mclauncher_0.1.3_amd64.deb` was built from that source in Ubuntu 24.04 amd64
with `SOURCE_DATE_EPOCH=0`, a 2-CPU limit, and a 6 GiB container memory cap.
Package identity:

```text
Package: mclauncher
Version: 0.1.3
Architecture: amd64
Size: 47,336,516 bytes
SHA-256: 92717bfafe04873179ff8924d8404d3c5e6704f0d22a6c602ad04838a7eac72d
```

The `.deb` installed successfully and opened through `gtk-launch mclauncher` in
an Ubuntu 24.04 amd64 Xvfb desktop smoke. The window was 920 × 560, and the
installed `/usr/lib/mclauncher/assets/minecraft-home.png` was present. The
captured package screenshot confirms the bundled landscape renders and Home
contains no news or changelog panel:
[evidence/07-package-idle-ubuntu24-0.1.3.png](evidence/07-package-idle-ubuntu24-0.1.3.png).
The background chooser is now in Settings; the Home control was removed.

This smoke verifies package installation, desktop-entry launch, the packaged
artwork path, and the reference-size idle screen. It does not establish a
physical desktop graphics journey or real Minecraft gameplay.

## Gameplay acceptance blocker

During the 0.1.0 GUI smoke, version discovery failed against the clean
container's network path with `CERTIFICATE_VERIFY_FAILED` (a self-signed
certificate in the certificate chain). No version list was available, so the
real Minecraft download, Java preparation, world creation/save, offline
relaunch, and world reopen journey could not be reached. TLS verification was
left enabled. This environment result does not establish a product-side TLS
defect or successful gameplay.

The 0.1.3 desktop smoke still reports release discovery failure because this
environment presents a self-signed certificate in the TLS chain. TLS
verification remains enabled. The real game launch and world-save/reopen
journey, legacy-world verification, secondary version/snapshot journey,
interruption/retry and lifecycle demonstrations, and visual checks at smaller
sizes/display scaling remain outstanding. Automated tests and the Xvfb
screenshot do not substitute for those player-visible checks.
