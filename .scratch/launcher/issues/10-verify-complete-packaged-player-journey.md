# 10: Verify the complete packaged player journey

**What to build:** Use the completed Ubuntu package for the agreed player journey, fix integration failures, and collect release evidence that the combined features work together.

**Blocked by:** 04: Recover interrupted installations; 05: Play multiple isolated, version-pinned instances; 06: Adjust and persist game memory limits; 07: Keep games running across launcher restarts; 08: Troubleshoot through the desktop interface; 09: Install the launcher as an Ubuntu desktop app.

**Status:** ready-for-agent

- [ ] Rebuild the completed application package and verify graphical clean-system installation, desktop entry, username persistence, instance creation, and managed runtime installation.
- [ ] Interrupt and retry installation, verify reuse of valid downloads and pinned versions, and confirm player data survives.
- [ ] Disconnect network access, launch real Minecraft, create and save a world, exit, and reopen the world successfully.
- [ ] Verify multiple instance isolation, unchanged external Minecraft data, and continued play of pinned versions when a newer stable release is advertised.
- [ ] Verify memory defaults, persisted valid adjustments, invalid-setting errors, stable usernames, and the username-change warning.
- [ ] Close and reopen the launcher during play, prevent duplicate games across launcher restarts and concurrent starts, then verify launch availability after game exit.
- [ ] Exercise installation errors and game crashes, export useful diagnostic logs, and open the correct instance folder.
- [ ] Verify downloads occur only for requested installation/retry, failed update checks do not block Play, and no telemetry or automatic launcher/world upgrades occur.
- [ ] Fix discovered integration defects and rerun the affected acceptance checks; preserve evidence of real packaged-app/game behavior rather than relying only on mocks.
- [ ] Record actual environment, dependency versions, package identity, passed checks, and any unresolved gaps; do not claim release readiness if required real-world checks remain unverified.
