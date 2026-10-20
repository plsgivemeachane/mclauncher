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

## Gameplay acceptance blocker

During the 0.1.0 GUI smoke, version discovery failed against the clean
container's network path with `CERTIFICATE_VERIFY_FAILED` (a self-signed
certificate in the certificate chain). No version list was available, so the
real Minecraft download, Java preparation, world creation/save, offline
relaunch, and world reopen journey could not be reached. TLS verification was
left enabled. This environment result does not establish a product-side TLS
defect or successful gameplay.

The real desktop graphics journey, legacy-world verification, secondary
version/snapshot journey, lifecycle demonstrations, and multi-state visual
comparison also remain outstanding. Automated tests cover deterministic
launcher behavior; they do not substitute for those player-visible checks.
