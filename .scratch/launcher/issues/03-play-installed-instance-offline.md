# 03: Play an installed instance offline

**What to build:** Launch the selected installed instance with the saved local player identity, create and reopen a world offline, and see when the game starts or exits.

**Blocked by:** 02: Install Minecraft and managed Java.

**Status:** ready-for-human

- [x] Generate the game command through minecraft-launcher-lib using the pinned version, managed Java runtime, explicit local identity, and selected instance data.
- [x] Launch a ready instance without successful network requests, including when update checks fail; do not run unconditional network-dependent repair before Play.
- [ ] Do not ship randomized tutorial test identities; verify intended local-session behavior against the target Minecraft release.
- [ ] Keep the launcher responsive and open while playing, show running and exit status, and prevent duplicate launches while this launcher is open.
- [ ] Explain missing required local files and leave recovery dependent on an explicit player request.
- [ ] With network access disabled, launch real Minecraft, create and save a world, exit, and reopen it with the same local identity.
- [x] Add application-boundary checks for offline launch, incomplete-instance rejection, and duplicate prevention; record real game-launch evidence.

## Comments

Packaged-run artifacts are preserved in [the acceptance evidence directory](../evidence/README.md).

With the test container network disconnected, the correct Play button started Minecraft 26.3 using the instance managed Java runtime, saved local identity, and instance data. The JVM exited at the Xvfb renderer boundary (no matching GLX visual/Vulkan surface), even though Mesa llvmpipe OpenGL 4.5 was exposed. The menu and offline world create/save/reopen flow remain unverified.
