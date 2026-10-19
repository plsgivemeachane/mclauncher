# Minecraft Offline-Session Launcher

Status: ready-for-human

## Problem Statement

Regular players want to install and play Minecraft Java Edition using an offline session without setting up a mod-development environment, constructing Java commands, or manually managing game files and Java. They need persistent worlds, reliable installation, and understandable errors.

The initial audience uses Ubuntu 24.04 LTS on x86-64. Installation must work graphically, and installed instances must remain playable without internet access.

## Solution

Provide a graphical desktop launcher that installs vanilla Minecraft and a managed Java runtime, saves a local username, and launches offline sessions. Players create and select named instances with separate worlds, settings, and screenshots.

New instances install the current stable release. Existing instances keep their installed version. Provide download progress and retry, adjustable memory allocation, running-game status, access to instance folders, and exportable diagnostic logs.

Deliver an amd64 Debian package with a desktop-menu entry and bundled Python and GUI dependencies. Initial game installation requires internet access; players do not install Python or Java manually.

## User Stories

1. As an Ubuntu player, I want to install the launcher graphically, so that I can start without terminal commands.
2. As an Ubuntu player, I want a desktop-menu entry, so that I can find the launcher like another desktop application.
3. As a new player, I want bundled Python and GUI dependencies, so that I do not need to configure the launcher's execution environment.
4. As a new player, I want to install Minecraft without an existing installation, so that I can complete setup through the launcher.
5. As a player, I want Minecraft's required Java runtime installed automatically, so that I do not need to select or install Java.
6. As a player, I want to enter and save a local username, so that I can identify myself in offline sessions.
7. As a returning player, I want an unchanged username to retain its local player identity, so that my identity stays consistent across launches.
8. As a player, I want to edit my username before launch, so that I can choose a different local player identity.
9. As a player changing my username, I want an identity-change warning before saving, so that I understand worlds or servers may recognize a different player.
10. As a player, I want to create a named instance, so that I can organize a separate playable setup.
11. As a player, I want to view and select my instances, so that I can choose which setup to play.
12. As a player creating an instance, I want it to install the current stable release, so that I can use the supported Minecraft version without researching version numbers.
13. As a player, I want installation progress and status, so that I can see whether setup is advancing.
14. As a player, I want downloads to start only after my installation or retry request, so that network activity is predictable.
15. As a player whose installation fails, I want an understandable error, so that I know why setup did not finish.
16. As a player whose installation is interrupted, I want to retry it, so that I can complete setup without abandoning the instance.
17. As a player retrying installation, I want completed verified downloads reused, so that I avoid unnecessary downloads.
18. As a player, I want Play enabled only when required files are ready, so that I do not launch an incomplete installation.
19. As a player recovering from installation failure, I want existing worlds preserved, so that a download problem does not cost my progress.
20. As a player, I want to launch the selected instance graphically, so that I do not need to construct a command.
21. As an offline player, I want installed instances to launch without internet access, so that connectivity does not prevent local play.
22. As an offline player, I want failed update checks to leave Play available, so that optional network activity does not block my game.
23. As a player, I want to create, save, and reopen a world offline, so that my progress persists.
24. As a player with multiple instances, I want separate worlds, settings, and screenshots, so that my setups remain independent.
25. As a player with an existing Minecraft installation, I want it left untouched, so that my current game data remains safe.
26. As a returning player, I want an instance to retain its installed version, so that new releases do not automatically change my world environment.
27. As a player, I want previously installed versions to remain playable, so that I can continue existing instances after a new release appears.
28. As a player, I want an initial memory limit based on available RAM, so that I can launch without tuning Java settings.
29. As a player, I want to view and adjust the memory limit in GiB, so that I can control resource use.
30. As a player entering an invalid memory limit, I want an explanation before launch, so that I can correct the setting.
31. As a returning player, I want saved usernames, instance information, and memory settings restored, so that I do not repeat setup.
32. As a player, I want the launcher to remain open and display running-game status, so that I understand its current state.
33. As a player, I want duplicate launches prevented, so that I do not accidentally start competing game processes.
34. As a player closing the launcher during play, I want Minecraft to keep running, so that closing the launcher does not end my session.
35. As a player reopening the launcher during play, I want the running game detected, so that the one-game limit still applies.
36. As a player leaving Minecraft, I want the launcher to show the game has exited, so that I can start another session.
37. As a player whose game crashes, I want a readable failure message, so that I know the session ended unexpectedly.
38. As a player, I want to open the selected instance's folder, so that I can find its worlds and screenshots.
39. As a player reporting a failure, I want to save a diagnostic log, so that I can share troubleshooting information without a terminal.
40. As a player, I want to install launcher updates manually, so that the application does not change unexpectedly.
41. As a player, I want no telemetry in the first release, so that launcher use does not generate background analytics reports.

## Implementation Decisions

- Use Python, PySide6 for the desktop interface, and minecraft-launcher-lib for installation and launch-command generation. Pin tested dependency versions during implementation.
- Target Ubuntu 24.04 LTS on x86-64. Ship an amd64 Debian package containing Python and GUI dependencies, with a desktop-menu entry. Download game files and the managed Java runtime during installation.
- Organize responsibilities around desktop interaction, launcher application operations, persistence, Minecraft installation/runtime integration, game-process lifecycle, and diagnostics. These are logical boundaries; there are no existing application modules to preserve.
- Expose player operations for saving a username, creating and selecting instances, installation/retry, launching, memory settings, opening an instance folder, and exporting logs.
- Persist one editable local username and derive the local player identity deterministically from it. Unchanged usernames retain identity across instances and restarts. Warn before saving a changed username. Microsoft sign-in is deferred.
- An offline session describes local identity independently of network connectivity. It does not provide authenticated access to services or servers requiring a valid account session.
- Persist instance names, instance identifiers, pinned game versions, installation readiness, and relevant settings. Isolate each instance's worlds, settings, and screenshots from other instances and existing Minecraft installations.
- Resolve the current stable release for a requested new installation and pin that instance to it. Interrupted retries continue the pinned installation. Existing versions remain playable; arbitrary historical-version selection and snapshots are deferred.
- Never automatically upgrade existing instances or their worlds.
- Delegate game metadata interpretation, downloads, launch arguments, and runtime integration to the library where supported. The launcher owns instance management and local player identity.
- Report progress and readable installation failures. Allow retries, reuse verified completed downloads, and preserve player data. Mark an instance playable only after required files are ready.
- Keep Play independent of successful network requests. Avoid unconditional network-dependent installation/repair before launching a ready instance. Explain missing local files and allow explicitly requested recovery.
- Download only for a requested installation or retry. Failed update checks do not block installed games. Launcher updates are manual; v1 sends no telemetry.
- Select initial memory allocation from available RAM, display it in GiB, persist changes, and validate before launch. The exact formula is an implementation detail to verify on the supported target.
- Allow one launcher-managed game at a time. Keep the launcher responsive and show readiness, installation progress, running, exit, and failure states.
- Let Minecraft survive launcher closure. Reopening detects the still-running game and enforces the one-game limit. Handle stale lifecycle records; a persisted process number alone is insufficient proof that the original game is running.
- Provide readable errors, Open instance folder, and Save diagnostic log actions.

## Testing Decisions

- Use one primary test seam: the launcher application exercised through its packaged desktop interface on the supported Ubuntu target. The user already approved this packaged-app journey during planning, establishing the requested agreement on the seam.
- Good tests assert external behavior, persisted outcomes, actual game-process behavior, and player-data isolation. Avoid tests coupled to private methods, class organization, or exact third-party call sequences.
- Cover desktop interaction, application operations, persistence, installation/runtime integration, lifecycle, and diagnostics through the same player-facing flows where practical. Use narrower integration checks only when needed to make failure scenarios deterministic.
- At test-planning time there was no application implementation, existing test suite, or existing test seam in this repo. The nine packaged-app acceptance scenarios agreed during the interview are expanded below.
- On a clean Ubuntu 24.04 x86-64 system, install and open the package graphically without separately installing Python or Java. Verify the desktop entry and first-run flow.
- Save a username, create an instance, install the current stable Minecraft release and managed runtime, observe progress, and launch the real game.
- Interrupt installation and retry. Verify completed verified downloads are reused, worlds are preserved, and incomplete instances cannot be launched as ready.
- Disable network access, launch an installed instance, create and save a world, exit, and reopen it. Verify failed update checks do not block Play.
- Simulate a newer stable release and verify new installations use it while existing instances keep their pinned versions. Do not wait for an actual upstream release during testing.
- Verify separate worlds, settings, and screenshots across instances. Compare an existing external Minecraft installation before and after use to confirm it remains untouched.
- Restart the launcher and verify saved settings survive. Verify stable identity for unchanged usernames, the warning and identity change on rename, and clear rejection of invalid memory settings.
- Launch a game, attempt a second launch, close and reopen the launcher, and verify the original game continues and blocks another launch. Verify launching becomes available after the game exits. Exercise stale process records and concurrent launcher starts at the application boundary.
- Exercise installation failure and game crash scenarios. Verify readable errors, useful diagnostic-log export, and opening the correct instance folder.
- Verify predictable downloads, no automatic instance or launcher upgrades, and no telemetry.
- Collect real packaged-app and game-launch evidence. Mocks may support recovery and release-change scenarios but cannot alone establish packaging, managed Java, offline play, or game-process lifetime correctness.

## Out of Scope

- Windows, other Linux distributions, ARM, and a general cross-distribution compatibility promise.
- Mod loaders, mods, and modpacks.
- Installing arbitrary historical releases or snapshots. Retaining previously installed instances remains in scope.
- Microsoft sign-in, account management, and authenticated multiplayer access.
- Instance deletion and copying.
- Automatic launcher updates and telemetry.
- Mod-author development tooling.

## Further Notes

- Approved UX follow-up: [username, version, Play specification](../launcher-ux/spec.md) and [implementation ticket](../launcher-ux/issues/01-implement-approved-launcher-design.md). That follow-up supersedes separate save/install controls, the primary manual-instance-creation journey, and the deferral of selectable releases/snapshots. Other guarantees and outstanding acceptance gaps remain applicable.
- Initially published to the configured local Markdown tracker as ready-for-agent. Implementation and automated verification are complete; packaged-app evidence and remaining player-acceptance gaps are recorded in Issues 01–10.
- The original repository contained agent configuration, engineering skills, a domain glossary, and this specification, with no application code or existing domain ADR constraining the implementation.
- Use the glossary's distinctions between instance, offline session, local player identity, vanilla Minecraft, and managed Java runtime.
- [minecraft-launcher-lib installation documentation](https://minecraft-launcher-lib.readthedocs.io/en/stable/modules/install.html) describes progress callbacks and repair. Verify the integration preserves offline launching rather than assuming installation/repair calls need no network.
- [minecraft-launcher-lib getting-started documentation](https://minecraft-launcher-lib.readthedocs.io/en/stable/tutorial/getting_started.html) presents generated test identities for development/testing and warns about public launchers enabling unpurchased play. Do not treat its tutorial helper as a supported production account model. Verify intended local-session compatibility against the target release; this spec neither adds Microsoft sign-in nor establishes distribution rights.
- [Qt for Python deployment documentation](https://doc.qt.io/qtforpython-6/deployment/index.html) describes desktop bundling. Verify the actual package on the agreed Ubuntu baseline and include required third-party notices.
- Exact dependency versions, identity encoding, memory-allocation formula, storage layout, and bundling tool are implementation choices constrained by the agreed behavior, not additional confirmed product decisions.

## Comments

### Implementation and acceptance record

Final verification (2026-10-18): Ubuntu 24.04 amd64; package mclauncher 0.1.0; SHA-256 304b83ef03b02316b74aa6840d84609b5f5ee3ffb599c695e2c387dd0a253dfb (44,064,956 bytes); Python 3.12.3 build; PySide6 6.12.0; minecraft-launcher-lib 8.0; Nuitka 4.1.1. The exact package was rebuilt reproducibly and its hash matches the artifact installed in the clean Ubuntu 24.04 test container. The package installed and opened graphically without system Python or Java; username AcceptanceUser and instance Acceptance were saved, and Minecraft 26.3 plus managed Java reached ready state. With the network disconnected, the correct Play button started the packaged game using its managed Java runtime, saved local identity, and instance directory. The process exited after Minecraft 26.3 failed to create a renderer under Xvfb (no matching GLX visual; Vulkan surface extension unavailable), even though Mesa llvmpipe OpenGL 4.5 was available. The profile-service lookup also failed offline without blocking JVM startup. No menu/world creation or save/reopen was verified. Native desktop graphics, retry/recovery demonstrations, multi-instance world separation, external-install preservation, and remaining real-player flows still need acceptance. Automated suite: 41 passed; compileall, shell syntax, git diff check, and desktop-file validation passed.
