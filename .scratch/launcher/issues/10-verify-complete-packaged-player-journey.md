# 10: Verify the complete packaged player journey

**What to build:** Use the completed Ubuntu package for the agreed player journey, fix integration failures, and collect release evidence that the combined features work together.

**Blocked by:** 04: Recover interrupted installations; 05: Play multiple isolated, version-pinned instances; 06: Adjust and persist game memory limits; 07: Keep games running across launcher restarts; 08: Troubleshoot through the desktop interface; 09: Install the launcher as an Ubuntu desktop app.

**Status:** ready-for-human

- [ ] Rebuild the completed application package and verify graphical clean-system installation, desktop entry, username persistence, instance creation, and managed runtime installation.
- [ ] Interrupt and retry installation, verify reuse of valid downloads and pinned versions, and confirm player data survives.
- [ ] Disconnect network access, launch real Minecraft, create and save a world, exit, and reopen the world successfully.
- [ ] Verify multiple instance isolation, unchanged external Minecraft data, and continued play of pinned versions when a newer stable release is advertised.
- [ ] Verify memory defaults, persisted valid adjustments, invalid-setting errors, stable usernames, and the username-change warning.
- [ ] Close and reopen the launcher during play, prevent duplicate games across launcher restarts and concurrent starts, then verify launch availability after game exit.
- [ ] Exercise installation errors and game crashes, export useful diagnostic logs, and open the correct instance folder.
- [ ] Verify downloads occur only for requested installation/retry, failed update checks do not block Play, and no telemetry or automatic launcher/world upgrades occur.
- [ ] Fix discovered integration defects and rerun the affected acceptance checks; preserve evidence of real packaged-app/game behavior rather than relying only on mocks.
- [x] Record actual environment, dependency versions, package identity, passed checks, and any unresolved gaps; do not claim release readiness if required real-world checks remain unverified.

## Comments

Packaged-run artifacts are preserved in [the acceptance evidence directory](../evidence/README.md).

Final verification (2026-10-18): Ubuntu 24.04 amd64; package mclauncher 0.1.0; SHA-256 304b83ef03b02316b74aa6840d84609b5f5ee3ffb599c695e2c387dd0a253dfb (44,064,956 bytes); Python 3.12.3 build; PySide6 6.12.0; minecraft-launcher-lib 8.0; Nuitka 4.1.1. The exact package was rebuilt reproducibly and its hash matches the artifact installed in the clean Ubuntu 24.04 test container. The package installed and opened graphically without system Python or Java; username AcceptanceUser and instance Acceptance were saved, and Minecraft 26.3 plus managed Java reached ready state. With the network disconnected, the correct Play button started the packaged game using its managed Java runtime, saved local identity, and instance directory. The process exited after Minecraft 26.3 failed to create a renderer under Xvfb (no matching GLX visual; Vulkan surface extension unavailable), even though Mesa llvmpipe OpenGL 4.5 was available. The profile-service lookup also failed offline without blocking JVM startup. No menu/world creation or save/reopen was verified. Native desktop graphics, retry/recovery demonstrations, multi-instance world separation, external-install preservation, and remaining real-player flows still need acceptance. Automated suite: 41 passed; compileall, shell syntax, git diff check, and desktop-file validation passed.
