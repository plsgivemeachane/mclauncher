# Launcher UX: username, version, Play

Status: ready-for-agent

## Problem Statement

Players currently face a large, mostly empty desktop form exposing local player identity, memory allocation, instance creation, installation, diagnostics, and launch as separate tasks. The main screen has little visual hierarchy, no version selector, explicit save buttons, and a disabled Play button whose prerequisites are difficult to understand. Players must learn launcher administration before playing Minecraft.

The desired task is simple: enter a username, select a Minecraft version or existing setup, and press one button. The desktop application should look deliberately designed rather than like a collection of default widgets.

## Solution

Implement the approved prototype's layout A: a compact dark desktop window, a quiet illustrated Minecraft-style landscape, a small Settings entry, and a solid bottom launch bar containing username, a version selector, and Play. Keep progress and readable errors directly above that bar. Play prepares missing game components and the managed Java runtime, then starts the selected offline session without a second action.

Save valid username and Settings edits automatically. Restore the last selection. First use defaults to the latest stable release; offer stable releases normally and snapshots through a Settings option. Automatically manage isolated instances behind version choices. Existing named instances remain selectable in the same selector so current worlds remain accessible.

## User Stories

1. As a new player, I want username, version, and Play visible together, so that I immediately understand how to start.
2. As a new player, I want the latest stable release selected initially, so that I can play without researching versions.
3. As a player, I want to enter a username without a save button, so that setup requires fewer actions.
4. As a player, I want invalid or empty usernames explained beside the relevant control, so that I can correct them before launch.
5. As a returning player, I want my username restored, so that I do not repeat setup.
6. As a returning player, I want my last version or saved setup restored, so that I can press Play immediately.
7. As a player, I want to browse stable Minecraft releases, so that I can choose the version I intend to play.
8. As a player, I want to search a long version list, so that I can find a specific release quickly.
9. As a player, I want downloaded versions marked, so that I know which choices are locally available.
10. As a player with existing instances, I want their names in the selector, so that I can find my existing worlds.
11. As a player, I want versions and saved setups grouped clearly, so that similarly named entries are distinguishable.
12. As a player trying a version for the first time, I want its instance created automatically, so that I do not name or configure an instance first.
13. As a player returning to a version, I want its existing automatic instance reused, so that I find the same worlds and settings.
14. As a player switching versions, I want worlds and settings isolated, so that an older game does not accidentally open a newer world.
15. As a player with multiple existing instances on the same version, I want each preserved and selectable, so that simplifying the interface does not hide my worlds.
16. As a player, I want one Play action to install missing components and launch, so that I do not choose between installation and playing.
17. As a player with an installed instance, I want Play to start it directly, so that preparation does not become unnecessary repeated work.
18. As an offline player, I want locally ready instances available even if version discovery fails, so that connectivity does not prevent play.
19. As a player installing Minecraft, I want progress beside the launch controls, so that I can see what the launcher is doing.
20. As a player, I want the interface to remain responsive during downloads, so that the launcher does not appear frozen.
21. As a player, I want repeated clicks prevented during preparation and launch, so that I do not start competing operations.
22. As a player whose installation fails, I want a short explanation and a retry through the same primary button, so that recovery is obvious.
23. As a player retrying an installation, I want the same pinned version and reusable completed downloads, so that retry is safe and efficient.
24. As a player whose installation is interrupted, I want to resume through the normal launch flow, so that I do not manage installation recovery separately.
25. As a player whose launch fails, I want a readable error near Play, so that I understand why the game did not open.
26. As a player, I want running and starting states clearly shown, so that temporary unavailability of Play has an explanation.
27. As a player closing the launcher during play, I want Minecraft to continue, so that closing the launcher does not end my session.
28. As a player reopening the launcher, I want the running game recognized, so that duplicate launch protection still works.
29. As a player leaving Minecraft, I want Play available again, so that I can start another session.
30. As a player, I want sensible memory allocation automatically, so that I do not tune Java before playing.
31. As a player adjusting memory, I want that control in Settings, so that the main screen stays focused on playing.
32. As a player editing Settings, I want valid edits saved automatically, so that no separate Save action is necessary.
33. As a player entering invalid memory settings, I want a clear explanation and preservation of my last valid setting, so that an accidental edit does not break launching.
34. As a player interested in snapshots, I want an explicit Settings option, so that experimental versions are available intentionally.
35. As a player, I want snapshots hidden by default, so that ordinary version selection stays simple.
36. As a player who changes username, I want to understand the effect on local player identity, so that the same world recognizing another player is not a surprise.
37. As a player troubleshooting a problem, I want folder access and diagnostic export reachable through Settings, so that I can obtain help without cluttering the main screen.
38. As a player, I want readable text and controls over a solid surface, so that background artwork never obscures the launch task.
39. As a keyboard user, I want visible focus and usable version selection and Settings, so that I can launch without a mouse.
40. As a player resizing the desktop window, I want controls and errors to remain readable, so that the interface works on smaller desktop displays.
41. As a player with existing saved data, I want the upgrade to preserve usernames, memory settings, instance identities, pinned versions, and worlds, so that the redesign does not cost my progress.
42. As a player with an existing external Minecraft installation, I want it untouched, so that trying this launcher does not alter other game setups.

## Implementation Decisions

- Retain Python and PySide6. The HTML prototype is a visual reference, not a replacement desktop stack. Add no dependencies for the redesign.
- Use layout A from the approved prototype: landscape above a bottom launch bar, small brand and Settings entry at the top, username and version fields followed by the strongest action, Play. Layouts B and C were comparisons and are not implementation targets.
- Match the approved charcoal surfaces, warm white typography, green primary action, modest rounded corners, subtle borders, and block landscape. Use readable system typography and approximately 44–47 px controls. The prototype uses a 920 × 560 desktop preview; use this as the initial implementation reference rather than the earlier approximate size discussion. Adapt to desktop resizing and display scaling without clipping.
- Keep controls on a solid dark surface. No news feed, slogans, promotional panels, permanent progress bar, large instance list, identity UUID, memory field, explicit save buttons, or separate installation button on the normal main screen. The prototype comparison toolbar and demo state selector are not product UI.
- Move memory allocation, snapshots preference, folder access, and diagnostic export into Settings. Keep the established memory allocation policy: one quarter of physical RAM rounded down, minimum 1 GiB and maximum initial allocation 8 GiB; valid user overrides remain bounded by physical RAM. Prototype memory values and limits are illustrative, not policy changes.
- Save valid edits on completion of editing and ensure pending valid username edits are committed before Play. Do not persist invalid intermediate values. Explain errors locally; do not add a Save button. Preserve stable local player identity derivation and communicate username-change consequences without restoring a second permanent main-screen action.
- Extend existing installation integration to discover selectable releases and prepare the explicitly selected version. Keep upstream metadata interpretation at the installation boundary. Fetch metadata asynchronously; remember usable metadata for subsequent disconnected launches. Metadata failure must not erase saved setup choices or disable ready local instances.
- Persist the snapshots preference, last selection, and the association between a concrete version and its automatically managed instance. Use stable instance identifiers to distinguish named legacy setups from ordinary version entries. Preserve existing records and directories; missing new fields receive backward-compatible defaults.
- Resolve the first-use latest stable choice to a concrete version before preparation. Pin the version for installation, retry, and future reopening. Remember that concrete choice after use; a newer release must not silently upgrade an existing setup or redirect its worlds.
- Create an automatic instance only when a version is requested for play; merely browsing the selector must not create instances or download game components. Reuse its established version association on later requests. Keep all existing named instances individually accessible, including multiple instances using the same version. Do not merge existing setups merely because their versions match.
- Group selector entries as versions and saved setups, support search, and distinguish locally downloaded choices. Readiness still depends on actual required files and the managed Java runtime, not a decorative downloaded marker or persisted readiness flag alone.
- Treat snapshots as an explicit opt-in for discovering new experimental choices. Turning that preference off must not delete or conceal an existing saved setup and its worlds.
- Implement one launch sequence: validate inputs, select/create the target instance, prepare missing components if necessary, then launch exactly once after successful preparation. Already ready instances launch without network prerequisites. Failures do not fall through to game startup.
- Present idle, preparing/downloading, starting, running, and failure states through the same primary control area. Use Play when idle, contextual busy text while unavailable, and a retry label on that same button after a recoverable failure. Keep progress and errors directly above the bar. Use indeterminate progress when totals are unknown rather than invented percentages.
- Bind an in-flight operation to its original instance and concrete version; prevent competing operations or selection edits from redirecting its results. Preserve the existing one-game rule, detached game lifetime, reopened-launcher adoption, and release of launch availability after exit.
- Preserve player data during errors, retries, upgrades, and state recovery. Keep existing corruption backup and explicit recovery protections; automatic Settings saving must not overwrite unrecovered state.
- Keep presentation, launcher interaction, persistence, installation/runtime integration, and lifecycle responsibilities at existing logical boundaries. Add version discovery at the installation boundary rather than spreading upstream calls through widgets. No new public service or generic framework is required.

## Testing Decisions

- Use the existing launcher window as the primary automated seam: drive player-visible controls with a Qt application, use a temporary launcher data root, and inject installation/player/lifecycle collaborators. This covers the complete username → selection → Play journey while keeping failures and release metadata deterministic. Extend the existing installation collaborator with version discovery support as needed; do not add a separate test-only application layer.
- Good tests assert visible availability, messages, persistence after reopening, selected instance identity, preserved worlds, and whether one game starts. Avoid tests of private helpers, exact widget nesting, thread arrangement, theme implementation, or incidental callback order.
- Existing launcher interaction tests already provide fake installers, a recovering installer, fake players, progress processing, and restart persistence scenarios. Existing memory, review-regression, and lifecycle tests provide prior art for invalid settings, corruption recovery, readiness validation, player-data isolation, detached processes, and reopened-launcher adoption. Adapt obsolete separate-save/install control interactions while retaining their behavioral guarantees.
- Exercise first use, returning use, stable-release listing, search, snapshot preference, existing named setups, remembered concrete version selection, repeated selection reuse, and multiple legacy setups sharing a version.
- Exercise a single Play click through fresh preparation into exactly one launch; ready offline launch without discovery success; interruption and retry on the pinned version; metadata failure; installation failure; launch failure; unknown progress totals; concurrent clicks; and normal/crashed game exit. Verify game components are not downloaded just by opening the window or choosing an entry.
- Reopen against legacy state and new state. Verify preserved identifiers, memory settings, worlds, screenshots, and versions; safe defaults for new preferences; and unchanged corrupt-state backup/recovery behavior. Verify no external Minecraft installation is modified.
- Test memory and username edits through Settings/main-screen interactions, including invalid intermediate input and Play immediately after a valid username edit. Verify unchanged usernames retain local player identity and changed usernames communicate their consequences.
- Keep narrower persistence, installation, and lifecycle checks only where the window seam cannot establish a guarantee reliably. Use the established integration checks for actual readiness, directory containment, and process lifetime.
- Verify the rendered PySide6 window against layout A at the reference desktop size and smaller supported desktop sizes/display scaling. Inspect idle, downloading, unknown progress, error, running, open selector, empty search, and Settings states; check keyboard navigation, focus, contrast, wrapping, and control clipping. This is visual acceptance of real widgets, not HTML screenshot equivalence.
- Retain a real packaged Ubuntu desktop acceptance journey for install → launch and disconnected relaunch. Mocks do not establish actual Minecraft rendering, saved-world persistence, or package correctness. Existing headless renderer limitations remain explicit acceptance gaps until real graphics acceptance succeeds.
- This publication defines future checks only. No implementation tests were run as part of writing this specification, and test-seam recommendations have not been separately approved by the user.

## Out of Scope

- Implementing layouts B or C, a web launcher, or shipping the prototype toolbar.
- News, changelogs, advertisements, promotional content, or a redesigned account system.
- Microsoft sign-in, authenticated multiplayer access, mods, mod loaders, and modpacks.
- Main-screen instance creation/administration, instance deletion/copying, or automatic sharing/conversion of worlds between versions.
- Migrating, merging, deleting, or upgrading existing worlds or external Minecraft installations.
- Changing the memory allocation policy or local player identity algorithm.
- Automatic launcher updates, telemetry, new dependencies, or additional operating-system targets.
- Claiming all historical releases work without qualification; unsupported metadata/runtime requirements must produce a readable failure and preserve existing setups.

## Further Notes

- The user explicitly approved the design after receiving the prototype. Layout A was the default linked preview and the recommended direction throughout the conversation; the approval is recorded against that layout.
- Visual reference: [approved prototype](../launcher/prototype/index.html?variant=A), with [prototype usage and limitations](../launcher/prototype/README.md). All shown versions, settings, percentages, and messages were demo data; the inline block landscape was original artwork. Production behavior must use actual metadata, readiness, progress, and process state.
- Decision source: [single-action game entry ADR](../../docs/adr/0002-single-action-game-entry.md). Retain the existing [memory allocation policy](../../docs/adr/0001-memory-allocation-policy.md) and root domain glossary.
- This specification supersedes the original launcher specification only where it requires explicit username/memory save actions, manual instance creation as the primary journey, separate installation and play actions, or defers selectable stable versions and snapshots. Existing offline-session, safety, lifecycle, packaging, and diagnostic guarantees continue to apply.
- The prototype's JavaScript parsed and its preview served successfully. A connected browser was unavailable, so rendered visual inspection was not claimed. Approval is the user's design verdict, not evidence of completed PySide6 implementation.
- At implementation handoff, preserve the approved prototype as a primary design source; archive experimental variants on a throwaway branch when integrating the production design. Do not copy the prototype's simulated state transitions into the real launcher.
- Publication is local Markdown per the configured issue tracker; no external issue service is required.
