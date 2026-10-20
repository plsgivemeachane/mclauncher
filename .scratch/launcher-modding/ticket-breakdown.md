# Published ticket breakdown

Approved by the user and published as 17 individual ready-for-agent tickets.

Source: [approved specification](spec.md). Each implementation ticket includes window-level behavior checks using the approved seam; process lifetime checks use real bounded child processes. The final ticket verifies integration and packaging rather than deferring all testing.

No standalone prefactoring ticket is proposed. Current installer/player injection and temporary storage already provide useful seams; minimal changes belong inside the first complete behavior that requires them.

1. **[Cancel preparation and close safely](issues/01-cancel-preparation-and-close-safely.md)**
   - **Blocked by:** None (can start immediately).
   - **What it delivers:** Close during active or stalled downloads, exit promptly, and safely retry the pinned setup using completed verified downloads. Preserve a running game on close.

2. **[Lock launch controls for the full session](issues/02-lock-launch-controls-for-the-full-session.md)**
   - **Blocked by:** None (can start immediately).
   - **What it delivers:** Lock username, selected setup, and launch settings from Play through game exit, including adopted games after reopening; unlock on failure or exit and prevent duplicate launches.

3. **[Ship the Minecraft home and navigation](issues/03-ship-minecraft-home-and-navigation.md)**
   - **Blocked by:** None (can start immediately).
   - **What it delivers:** Replace the landscape with bundled Minecraft imagery, custom background selection, compact launch controls, and working Home/Instances navigation. Introduce Browse when its catalog lands; avoid a dead destination.

4. **[Manage independent instances](issues/04-manage-independent-instances.md)**
   - **Blocked by:** 03.
   - **What it delivers:** Name, duplicate, and confirm deletion of saved instances from Instances, preserving independent data and warning about world loss. Retain existing vanilla setups.

5. **[Import and play a Fabric Modrinth pack](issues/05-import-and-play-fabric-modrinth-pack.md)**
   - **Blocked by:** 01, 02.
   - **What it delivers:** Select a .mrpack, create an isolated instance, prepare declared Fabric/Minecraft/runtime/files, and launch. Include source metadata, safe extraction, integrity checks, cancellation/retry, and visible incomplete states.

6. **[Import and play Forge packs](issues/06-import-and-play-forge-packs.md)**
   - **Blocked by:** 05.
   - **What it delivers:** Extend the working pack journey to declared Forge versions, with real readiness validation and useful unsupported-combination errors.

7. **[Import and play NeoForge packs](issues/07-import-and-play-neoforge-packs.md)**
   - **Blocked by:** 05.
   - **What it delivers:** Extend the working pack journey to declared NeoForge versions while preserving isolated data, recovery, and exact release selection.

8. **[Import and play Quilt packs](issues/08-import-and-play-quilt-packs.md)**
   - **Blocked by:** 05.
   - **What it delivers:** Extend the working pack journey to declared Quilt versions while preserving isolated data, recovery, and exact release selection.

9. **[Browse and install Modrinth packs](issues/09-browse-and-install-modrinth-packs.md)**
   - **Blocked by:** 03, 05.
   - **What it delivers:** Search in Browse, inspect pack details/releases, select a compatible release, install, and Play through the established instance preparation flow. Additional loader support follows its own tickets.

10. **[Import CurseForge exported packs](issues/10-import-curseforge-exported-packs.md)**
   - **Blocked by:** 06.
   - **What it delivers:** Import an exported-pack ZIP into its own instance using supported loaders, prepare accessible required files, and launch. Explain unavailable/restricted files with a permitted recovery action, verify supplied replacements, and keep Play disabled until complete.

11. **[Manage local mods per instance](issues/11-manage-local-mods-per-instance.md)**
   - **Blocked by:** 05.
   - **What it delivers:** List mods, import compatible local JARs, enable/disable/remove them, and persist changes. Reject known incompatibility, explain unknown metadata, warn about curated-pack changes, and mark additions as modifications.

12. **[Find and install individual Modrinth mods](issues/12-find-and-install-individual-modrinth-mods.md)**
   - **Blocked by:** 09, 11.
   - **What it delivers:** Search compatible mods from the instance Mods page, prepare required dependencies, install into that instance, and launch; preserve recovery, compatibility, and modified-pack behavior.

13. **[Install a local OptiFine release](issues/13-install-local-optifine-release.md)**
   - **Blocked by:** 06.
   - **What it delivers:** Select an official local OptiFine JAR and prepare a supported standalone or compatible Forge setup, with clear incompatible-version/loader errors and no automated OptiFine downloading.

14. **[Update Modrinth packs with recovery](issues/14-update-modrinth-packs-with-recovery.md)**
   - **Blocked by:** 09.
   - **What it delivers:** Explicitly choose a new pack release or replacement archive, back up the instance, warn about changed local files, preserve worlds, apply the update, and recover from interruption or failure without publishing a partial release as ready.

15. **[Update imported CurseForge packs](issues/15-update-imported-curseforge-packs.md)**
   - **Blocked by:** 10, 14.
   - **What it delivers:** Apply a selected newer exported-pack ZIP to the existing instance through the backed-up update journey, retaining provider identity and handling missing/restricted files without requiring integrated CurseForge browsing.

16. **[Show cached Minecraft news and launcher changes](issues/16-show-cached-news-and-launcher-changes.md)**
   - **Blocked by:** 03.
   - **What it delivers:** Render Minecraft release/news cards and a secondary launcher changelog, cache fetched content, and keep Home and ready-instance launching usable with empty cache, network failures, or offline startup.

17. **[Verify the complete packaged player journey](issues/17-verify-complete-packaged-player-journey.md)**
   - **Blocked by:** 04, 07, 08, 12, 13, 15, 16.
   - **What it delivers:** Verify the assembled product in the packaged application: real provider/loader samples, imports, isolated duplicates, mod management, updates/recovery, close/reopen locks, and compact/large/offline visual behavior. Report evidence and any unsupported combinations explicitly.

## Dependency notes

- Loader tickets 06–08 each extend the complete import-to-launch path; they are not separate schema/API/UI layers.
- Ticket 09 initially offers only combinations already supported by completed loader tickets; it need not wait for every loader.
- Ticket 10 starts with Fabric/Forge support and picks up other supported loaders as their tickets land; it includes missing-file recovery rather than calling incomplete imports successful.
- Ticket 04 owns the Instances entry point. Ticket 05 introduces pack identity through a working import flow, not a schema-only prerequisite. Final verification covers naming/duplicating/deleting both vanilla and pack instances.
- Ticket 13 follows 06 to reuse verified Forge installation for its compatible Forge path; its scope also includes supported standalone OptiFine installation.
- All file-mutating operations must respect active-instance locks; every new preparation path must preserve cancellation and pinned-target recovery.
- Ticket 17 depends on the terminal feature tickets; their transitive prerequisites cover all earlier work.

## Execution frontier

Tickets 01, 02, and 03 have no blockers. Work any ticket whose blockers have completed; later ticket numbers do not imply a linear execution chain. Every ticket is published with ready-for-agent status, while its blocking edges still determine when work can start. The parent specification remains unchanged.
