# 09: Install the launcher as an Ubuntu desktop app

**What to build:** Install an amd64 Debian package on Ubuntu 24.04 LTS, open the launcher from the desktop menu, and install and play Minecraft without manually installing Python or Java.

**Blocked by:** 03: Play an installed instance offline.

**Status:** ready-for-agent

- [ ] Produce a reproducible amd64 Debian package with bundled Python and GUI dependencies using tested pinned versions.
- [ ] Provide a working desktop-menu entry and graphical launcher startup on Ubuntu 24.04 LTS x86-64.
- [ ] Download Minecraft and managed Java during requested instance installation rather than bundling game installations into the launcher package.
- [ ] Include required third-party license notices and preserve the manual launcher-update policy.
- [ ] On a clean supported Ubuntu desktop, install and open the package graphically without terminal commands or manual Python/Java setup, then install and launch real Minecraft.
- [ ] Record the exact tested package and environment; do not claim support for untested Linux distributions or architectures.
