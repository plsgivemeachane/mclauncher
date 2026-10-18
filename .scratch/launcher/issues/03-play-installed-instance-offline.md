# 03: Play an installed instance offline

**What to build:** Launch the selected installed instance with the saved local player identity, create and reopen a world offline, and see when the game starts or exits.

**Blocked by:** 02: Install Minecraft and managed Java.

**Status:** ready-for-agent

- [ ] Generate the game command through minecraft-launcher-lib using the pinned version, managed Java runtime, explicit local identity, and selected instance data.
- [ ] Launch a ready instance without successful network requests, including when update checks fail; do not run unconditional network-dependent repair before Play.
- [ ] Do not ship randomized tutorial test identities; verify intended local-session behavior against the target Minecraft release.
- [ ] Keep the launcher responsive and open while playing, show running and exit status, and prevent duplicate launches while this launcher is open.
- [ ] Explain missing required local files and leave recovery dependent on an explicit player request.
- [ ] With network access disabled, launch real Minecraft, create and save a world, exit, and reopen it with the same local identity.
- [ ] Add application-boundary checks for offline launch, incomplete-instance rejection, and duplicate prevention; record real game-launch evidence.
