# Ticket 07 package acceptance evidence

Integrated source: `be9b12ef36cc3ae69b57511f0f6d5051f50ceaf9` (`integration/launcher-ux-merge-07`).

## Automated checks

Command:

```sh
TMPDIR=/tmp QT_QPA_PLATFORM=offscreen \
  /tmp/mclauncher-ux-venv/bin/python -m pytest -x -q
```

Result: `80 passed in 3.55s`.

`git diff --check 4327509...HEAD` also passed before this evidence update.

## Clean Ubuntu 24.04 package build

The documented `packaging/build-deb.sh` flow completed in a clean Ubuntu
24.04 amd64 Docker container using `SOURCE_DATE_EPOCH=0`. It produced
`dist/mclauncher_0.1.0_amd64.deb` from the integrated source above.

Package identity and build metadata:

```text
Package: mclauncher
Version: 0.1.0
Architecture: amd64
Size: 44,226,224 bytes
SHA-256: 60c455ea0e19aea4fff1ab0ec6b57f9665020e65b0c882fc28d308d975bcf11b
Build Python: 3.12.3
Pinned PySide6: 6.12.0
Pinned minecraft-launcher-lib: 8.0
Source date epoch: 0
```

The installed desktop entry declares `Exec=/usr/bin/mclauncher` and
`TryExec=/usr/bin/mclauncher`. The package installed successfully with apt in a
clean Ubuntu 24.04 amd64 container; no Python or Java package was installed
separately. Running the installed executable under Xvfb remained alive for the
20-second smoke window. `gtk-launch mclauncher` also opened the installed
desktop entry and produced a `Minecraft Launcher` Qt window. The window was
920 × 560; its captured idle screen is
[evidence/07-package-idle-920x560.png](evidence/07-package-idle-920x560.png).

## Gameplay acceptance blocker

The packaged launcher opened, but version discovery failed against the clean
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
