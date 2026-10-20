# 17: Verify the complete packaged player journey

**What to build:** Verify the assembled product in the packaged application: real provider/loader samples, imports, isolated duplicates, mod management, updates/recovery, close/reopen locks, and compact/large/offline visual behavior. Report evidence and any unsupported combinations explicitly.

**Blocked by:** [04: Manage independent instances](04-manage-independent-instances.md); [07: Import and play NeoForge packs](07-import-and-play-neoforge-packs.md); [08: Import and play Quilt packs](08-import-and-play-quilt-packs.md); [12: Find and install individual Modrinth mods](12-find-and-install-individual-modrinth-mods.md); [13: Install a local OptiFine release](13-install-local-optifine-release.md); [15: Update imported CurseForge packs](15-update-imported-curseforge-packs.md); [16: Show cached Minecraft news and launcher changes](16-show-cached-news-and-launcher-changes.md).

**Status:** ready-for-agent

- [ ] Run the applicable behavior regressions and configured static/build checks, and smoke-test the packaged application with required metadata, dependencies, and bundled artwork present.
- [ ] Verify close during a real held/stalled preparation, prompt application exit, pinned retry, and a detached game surviving close/reopen with correct control locks.
- [ ] Collect bounded live provider/loader evidence for supported Fabric, Forge, NeoForge, and Quilt combinations, both archive formats, integrated pack/mod discovery, and supported local OptiFine paths. Distinguish controlled-test evidence from actual installation/launch evidence.
- [ ] Verify naming, duplicate file/world independence, confirmed/cancelled deletion, legacy saved setups, and multiple installations of one pack on one game version.
- [ ] Verify explicit backed-up updates, local-mod/configuration warnings, interrupted recovery, missing-file handling, and world preservation for both pack sources.
- [ ] Review Home/Instances/Browse, Mods, news/changelog, background selection, progress, errors, and bottom controls at compact/default and supplied large-window sizes, including fresh and cached offline startup.
- [ ] Fix integration defects within the agreed scope or record concrete blockers and unsupported combinations with evidence; do not claim all integrations verified merely because mocked tests pass.

## Parent

[Approved specification](../spec.md). Follow its glossary, ADRs, scope limits, and approved launcher-window testing boundary.
