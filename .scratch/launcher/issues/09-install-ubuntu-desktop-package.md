# 09: Install the launcher as an Ubuntu desktop app

**What to build:** Install an amd64 Debian package on Ubuntu 24.04 LTS, open the launcher from the desktop menu, and install and play Minecraft without manually installing Python or Java.

**Blocked by:** 03: Play an installed instance offline.

**Status:** ready-for-human

- [x] Produce a reproducible amd64 Debian package with bundled Python and GUI dependencies using tested pinned versions.
- [ ] Provide a working desktop-menu entry and graphical launcher startup on Ubuntu 24.04 LTS x86-64.
- [x] Download Minecraft and managed Java during requested instance installation rather than bundling game installations into the launcher package.
- [x] Include required third-party license notices and preserve the manual launcher-update policy.
- [ ] On a clean supported Ubuntu desktop, install and open the package graphically without terminal commands or manual Python/Java setup, then install and launch real Minecraft.
- [x] Record the exact tested package and environment; do not claim support for untested Linux distributions or architectures.

## Comments

Packaged-run artifacts are preserved in [the acceptance evidence directory](../evidence/README.md).

Package verified: mclauncher 0.1.0 amd64, 44,064,956 bytes, SHA-256 304b83ef03b02316b74aa6840d84609b5f5ee3ffb599c695e2c387dd0a253dfb. Ubuntu 24.04 build used Python 3.12.3, PySide6 6.12.0, minecraft-launcher-lib 8.0, and Nuitka 4.1.1. A clean-container GUI install and managed game/runtime install succeeded without system Python or Java, and the packaged desktop file passed validation. The package includes bundled dependency license notices and retains manual launcher updates. The launcher was started graphically, but selecting it through an actual desktop menu was not exercised. Real gameplay stopped at the Xvfb graphics boundary; no wider platform claim is made.
