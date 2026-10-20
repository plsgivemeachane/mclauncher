# Responsive launcher, integrated modding, and Minecraft home screen

Status: ready-for-agent

## Problem Statement

Players cannot reliably close the launcher during downloads because installation explicitly blocks closing. Launch controls disagree about whether a session is active: Play is locked while the username remains editable, allowing the saved local player identity to change during a running session.

The launcher currently prepares only vanilla Minecraft. Players cannot discover and install modpacks inside it, import downloaded packs, manage individual mods, or install OptiFine through a supported flow. Modpacks need independent instances to avoid mixing unrelated setups and player data.

The flat green landscape leaves most of the window visually empty. Players want a Minecraft image background, useful release news and changelogs, and clear access to instances and browsing, while keeping the simple username → selected setup → Play journey.

## Solution

Keep the launcher responsive throughout preparation. Closing cancels preparation and exits promptly; completed verified downloads remain reusable on the next attempt. Closing after Minecraft starts leaves the game running. Lock username, selected setup, and launch settings from Play through preparation and the running game, restoring controls after failure or game exit.

Provide integrated Modrinth discovery and installation, plus file-picker import for Modrinth packs and CurseForge exported packs. Automatically prepare the declared Minecraft version, mod loader, managed Java runtime, and required pack files. Each installed pack owns an independent instance. Provide per-instance mod management, local OptiFine installation for compatible setups, explicit backed-up updates, and instance naming, duplication, and confirmed deletion.

Use a Minecraft screenshot background, readable Minecraft release/news cards, a secondary launcher changelog, Home / Instances / Browse navigation, and compact bottom launch controls. Bundle a background, support custom images, and cache news so network failures never prevent launching a ready instance.

## User Stories

1. As a player, I want the launcher responsive during downloads, so that I can interact with its window during preparation.
2. As a player, I want closing during preparation to cancel it and exit promptly, so that I am not trapped waiting for downloads.
3. As a returning player, I want completed verified downloads reused after cancellation, so that retrying avoids unnecessary downloads.
4. As a returning player, I want partial downloads recognized as incomplete, so that interrupted preparation is never shown as ready.
5. As a player, I want retry to retain my selected instance and pinned version, so that recovery prepares the intended setup.
6. As a player, I want closing the launcher to leave an already running game alive, so that I can play without the launcher open.
7. As a returning player, I want the launcher to recognize a game still running, so that reopening does not permit a competing launch or identity edit.
8. As a player, I want username editing locked from Play until game exit, so that my local player identity stays consistent during a session.
9. As a player, I want setup selection and launch settings locked during preparation and play, so that an active operation cannot switch targets.
10. As a player, I want controls restored after preparation or launch failure, so that I can correct the problem and retry.
11. As a player, I want controls restored after game exit, so that I can choose my next session.
12. As a player, I want repeated Play clicks to start at most one preparation and game, so that accidental clicks do not create competing operations.
13. As a player, I want readable progress and recovery instructions near Play, so that I understand what is happening.
14. As a player, I want one Play action to prepare missing prerequisites and launch, so that I do not coordinate separate installation steps.
15. As a player, I want to browse and search Modrinth modpacks inside the launcher, so that I can discover packs without an external download flow.
16. As a player, I want pack details and available releases before installation, so that I can choose the intended release.
17. As a player, I want to install a selected pack from its catalog entry, so that preparation happens in one guided flow.
18. As a player, I want to import a downloaded Modrinth pack through a file picker, so that I do not unpack it or assemble prerequisites manually.
19. As a player, I want to import a CurseForge exported-pack ZIP through a file picker, so that packs obtained elsewhere remain usable.
20. As a player, I want invalid or unsupported archives explained, so that I know why an import cannot proceed.
21. As a player, I want the declared Minecraft version and mod loader prepared automatically, so that I do not guess compatible prerequisites.
22. As a player, I want Fabric, Forge, NeoForge, and Quilt packs supported where their declared combinations are available, so that my choices extend beyond vanilla Minecraft.
23. As a player, I want required pack files and dependencies prepared automatically, so that installed packs have what they need to run.
24. As a player, I want unavailable required downloads to show a recovery action, so that I can resolve missing files without guessing.
25. As a player, I want Play unavailable until required preparation succeeds, so that incomplete packs are not launched as ready.
26. As a player, I want separate instances for separate pack installations, so that worlds, settings, and mods do not mix.
27. As a player, I want packs using one Minecraft version to stay independent, so that a shared game version does not merge their data.
28. As an existing player, I want vanilla instances and saved setups preserved, so that adding modding support does not lose worlds or selections.
29. As a player, I want an instance's Mods page to list its mods, so that I can understand its contents.
30. As a player, I want Modrinth mod search scoped to instance compatibility, so that I can find suitable additions.
31. As a player, I want local mod JAR import into a selected compatible instance, so that I can use mods obtained elsewhere.
32. As a player, I want incompatible mods rejected with an explanation, so that I do not silently damage a working setup.
33. As a player, I want to enable and disable mods, so that I can experiment without immediately deleting them.
34. As a player, I want to remove individual mods, so that I can maintain the selected instance.
35. As a player, I want curated packs marked as modified when I add mods, so that I can distinguish local changes from published contents.
36. As a player, I want a compatibility warning when modifying a curated pack, so that I understand the effect on expected behavior.
37. As a player, I want to select an official local OptiFine JAR for a compatible instance, so that the launcher handles installation.
38. As a player, I want unsupported OptiFine combinations explained, so that it is not offered indiscriminately inside modpacks.
39. As a player, I want to name instances, so that I can recognize my setups.
40. As a player, I want multiple installations of the same pack, so that playthroughs and experiments stay separate.
41. As a player, I want to duplicate an instance into an independent copy, so that I can experiment without altering the original.
42. As a player, I want deletion to identify the instance and confirm world removal, so that I do not accidentally lose a playthrough.
43. As a player, I want pack updates to require explicit action, so that working setups never change silently.
44. As a player, I want a recovery backup before a pack update, so that failed or unwanted updates have a recovery path.
45. As a player, I want updates to preserve worlds, so that updating does not erase progress.
46. As a player, I want a warning before locally changed mods or configuration are replaced, so that I can make an informed update choice.
47. As a player, I want interrupted updates recoverable, so that partial changes do not masquerade as completed pack versions.
48. As a player, I want Home / Instances / Browse navigation, so that launching, managing setups, and discovering packs are easy to find.
49. As a player, I want a Minecraft screenshot background and readable content, so that the launcher feels like a finished Minecraft application.
50. As an offline player, I want a bundled background, so that the home screen does not depend on downloading artwork.
51. As a player, I want a custom background image, so that I can personalize the launcher.
52. As a player, I want Minecraft release/news cards, so that I can see relevant game updates.
53. As a player, I want a secondary launcher changelog, so that I can understand changes to the launcher itself.
54. As an offline player, I want cached news and a usable home screen when fetching fails, so that external content is not a startup dependency.
55. As a player, I want news failures to leave ready instances launchable, so that reading updates never blocks playing.
56. As a returning player, I want compact bottom controls to retain my username and selected setup, so that I can quickly return to playing.

## Implementation Decisions

- Preserve the existing PySide6 application and single-action preparation/launch journey. Extend the launcher window, persistence, installer/player boundaries, and process registry rather than replacing the application stack.
- Handle preparing, running, failed, interrupted, and ready conditions consistently across controls and persisted recovery. Capture the operation's instance and local player identity when Play begins; asynchronous results remain attached to that target.
- Replace close rejection during installation with cancellation and prompt application exit. Cancellation must handle stalled network work without waiting indefinitely. The concrete worker/process mechanism remains an implementation choice; abandoned writes must not publish incomplete state as ready.
- Reuse completed verified artifacts after interruption. Readiness depends on required files and the managed Java runtime, not only a saved flag or progress indicator. Preserve recovery through Play.
- Preserve detached-game discovery across launcher restarts. Reopening while a managed game is alive restores applicable locks; launcher shutdown must not terminate that game.
- Extend persisted instances with pack source/release identity, declared game/loader versions, installed-file/mod metadata, enabled state, local modification information, and installation/update recovery state as needed. Preserve old state and automatic vanilla associations when new fields are absent.
- Separate provider release identity from instance identity. Different packs on one game version and multiple installations of one pack use distinct instance data directories. Do not merge packs into the automatic vanilla-version mapping.
- Deliver integrated Modrinth discovery/install in the first release. File import is a fallback and portability feature, not a substitute for the agreed catalog. Integrated CurseForge browsing is deferred until API access is established.
- Accept Modrinth pack archives and CurseForge exported-pack ZIPs through a file picker. Identify formats by their manifests, validate destination paths and integrity, and apply declared contents and overrides. Explain unsupported archives; arbitrary ZIPs are not automatically modpacks and extraction must stay inside the intended instance.
- Automatically prepare declared Minecraft, loader, runtime, and required files. Target Fabric, Forge, NeoForge, and Quilt, verifying actual support for each requested combination against official sources rather than assuming every version supports every loader.
- Missing or restricted required downloads produce an actionable incomplete/recovery condition. Do not claim archive import embeds every dependency or bypass provider restrictions.
- Scope mod search, import, toggling, and removal to the selected instance. Use available game/loader/dependency metadata for compatibility; unknown compatibility is not verified compatibility. Mark additions to curated packs as modifications and warn about compatibility.
- OptiFine installation accepts a player-selected official JAR for a supported compatible setup. Do not assume an automated download API or universal compatibility with packs and loaders.
- Renaming preserves instance identity; duplication creates an independent copy. Confirm deletion with the instance and world-loss consequence. Mutations of an active preparation target or running instance respect operation locks.
- Updates require explicit action and a recovery backup before replacement. Preserve worlds, warn before replacing local mods/configuration, and retain recovery information so partial updates cannot appear complete.
- Implement Home / Instances / Browse, Minecraft imagery, readable news cards, a secondary launcher changelog, and compact bottom controls. Bundle distributable artwork, allow a custom image, and retain Settings as a secondary entry.
- Fetch/cache news independently of preparation and launch. News failures never gate ready instances. Verify the feed contract and artwork distribution rights during implementation.
- Follow the isolated-instance, Modrinth-first, and home/navigation ADRs. The latter supersedes the old flat landscape, no-feed, and no-instance-screen choices; single Play, memory policy, and saved vanilla setups remain applicable.
- Sequence work through responsiveness/locking, persisted modded instances and loader preparation, catalog/import/mod/OptiFine flows, instance/update operations, then complete visual integration and verification. This order does not reduce the deliverable to an import-only release.

## Testing Decisions

- The user approved the existing launcher-window boundary as the primary test seam. Exercise complete player journeys with injected installer/player collaborators, temporary launcher-owned storage, controlled provider/download responses, and event-loop processing. Prefer this high boundary to many new internal test interfaces.
- Good tests assert observable controls, progress/errors, launch counts/targets, state after reopening, and actual instance files/worlds. Avoid private helper structure, worker implementation, and stylesheet text as substitutes for behavior.
- Extend preparation/retry and pinned-version window scenarios with held or stalled downloads, closing while work is active, bounded application process exit, reopened retry, verified artifact reuse, partial files, network failures, and repeated Play clicks. Writing an interrupted state before startup alone does not prove cancellation works.
- Extend real-process lifecycle checks for detached-game survival, reopening, locks while an adopted game is alive, and unlocking after exit. A bounded child process can prove process survival without requiring Minecraft in deterministic tests.
- Replace the existing regression that expects closing during installation to be ignored. Update old layout assertions for the superseded landscape while retaining underlying preparation, identity, and data-preservation coverage.
- Exercise catalog selection → install → ready → Play, archive import → ready → Play, and failure → recovery through the window seam. Use representative manifests and controlled artifact responses for loader/dependency resolution, overrides, hashes, optional/client applicability, malformed archives, traversal, unavailable files, and unsupported combinations. Verify real provider adapter contracts separately before claiming a live integration works.
- Extend existing isolation and persistence/restart scenarios to different packs on one game version, multiple copies of one pack, legacy state migration, naming, duplication, and confirmed/cancelled deletion. Assert file separation and preserved worlds/settings rather than only distinct labels.
- Exercise per-instance mod search/import, compatibility rejection, toggling, removal, modified-pack warnings, and local OptiFine preparation. Include known incompatible and unknown-metadata cases without claiming universal compatibility.
- Exercise explicit updates with worlds and locally changed files. Verify backup/recovery, warnings before replacement, player-data preservation, no automatic update, and failures/interruption before completion. An update-status label alone is insufficient evidence.
- Test offline startup, failed feeds, cached news, bundled artwork, custom backgrounds, and launch without news connectivity. Review rendered windows at compact default and supplied large-window sizes for readable cards, navigation, controls, and background cropping.
- Reuse prior art from the launcher application, preparation recovery, automatic instance isolation, process lifecycle, persistence/path validation, and packaging suites. Add only the minimum collaborator injection needed to control external dependencies through the primary seam.
- Run targeted regressions first, then applicable existing tests and configured static/build checks. Smoke-test the packaged player journey with bundled assets. Controlled tests do not prove live access or real game/loader/OptiFine compatibility: collect bounded live evidence for supported combinations and report remaining validation gaps.

## Out of Scope

- Integrated CurseForge catalog browsing until API access/eligibility is established; exported-pack ZIP import remains in scope.
- Automatic OptiFine downloads or universal support across arbitrary packs, game versions, and loaders.
- Microsoft authentication, changes to offline-session identity, multiplayer account services, server management, or replacing Minecraft's own interface.
- Silent pack updates, converting vanilla instances to modpacks, or implicitly sharing worlds/settings across instances.
- Background downloads after launcher close or terminating an already running game on launcher close.
- Copying TLauncher branding/assets or reproducing every feature of other launchers; TLauncher is a player-flow reference.
- A general plugin system, replacement application stack, or new third-party dependencies without explicit authorization.

## Further Notes

Product scope and test boundaries were approved in the conversation. This document replaces the interview notes at the same tracker location and is the implementation specification. Its ready-for-agent status publishes it to the project's local issue tracker; no remote issue is required.

Current code explicitly rejects closing while installing, has no worker cancellation path, and disables Play without locking username when a game starts. Installation and persistence are currently vanilla-only. Existing regression coverage intentionally expects installation to block closing; that expectation must change.

Domain and architectural references:

- [Project glossary](../../GLOSSARY.md)
- [Memory policy](../../docs/adr/0001-memory-allocation-policy.md)
- [Original single-action game entry](../../docs/adr/0002-single-action-game-entry.md), with visual/navigation exclusions superseded below
- [Isolated modpack instances](../../docs/adr/0003-isolated-modpack-instances.md)
- [Modrinth-first catalog and pack imports](../../docs/adr/0004-modrinth-first-catalog-and-pack-imports.md)
- [Home and instance navigation](../../docs/adr/0005-launcher-home-and-instance-navigation.md)

Official evidence gathered during the interview:

- [TLauncher modpack flow](https://tlauncher.org/en/news_26/modpack-system_5100.html) describes pack cards, installation, details, dependencies, and manual installation. The article is from 2018, not proof of today's exact interface.
- [Modrinth pack format](https://support.modrinth.com/en/articles/8802351-modrinth-modpack-format-mrpack) describes manifests, dependencies, downloads, hashes, overrides, and path safety.
- [CurseForge import/export](https://support.curseforge.com/support/solutions/articles/9000198501-exporting-and-importing-modpacks) documents exported-pack ZIP import. Verify field-level handling and download access during implementation.
- [CurseForge REST API](https://docs.curseforge.com/rest-api/) requires API-key access; eligibility for this launcher remains unresolved and gates its deferred catalog integration.
- [OptiFine downloads](https://optifine.net/downloads) lists releases and compatibility. Research found no documented automated launcher download contract.

Choose concrete provider request mappings, supported per-version loader combinations, the news source, and distributable artwork during implementation using verified evidence. These are implementation/validation tasks within the agreed scope, not unanswered product interview questions. Publishing this specification changes no application behavior.
