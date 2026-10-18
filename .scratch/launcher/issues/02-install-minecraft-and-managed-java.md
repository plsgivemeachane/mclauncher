# 02: Install Minecraft and managed Java

**What to build:** Request installation for a named instance, see progress while vanilla Minecraft and its managed Java runtime are installed, and see readiness only after setup succeeds.

**Blocked by:** 01: Save a local identity and create an instance.

**Status:** ready-for-agent

- [ ] Use minecraft-launcher-lib to install the current stable Minecraft release and its required managed Java runtime without requiring system Java.
- [ ] Resolve the release for the requested installation and persist the pinned version before downloading, so later retries retain that version.
- [ ] Download only in response to the player installation request, report progress, and keep the desktop interface responsive.
- [ ] Use the selected instance data area and preserve separation from existing Minecraft installations.
- [ ] Mark the instance ready only after required installation work succeeds; show a readable failure otherwise.
- [ ] Add application-boundary tests for requested installation, progress, pinning, and readiness; demonstrate a real completed installation on the supported Ubuntu target.
