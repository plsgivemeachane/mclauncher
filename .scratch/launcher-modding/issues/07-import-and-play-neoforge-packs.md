# 07: Import and play NeoForge packs

**What to build:** Extend the working pack journey to declared NeoForge versions while preserving isolated data, recovery, and exact release selection.

**Blocked by:** [05: Import and play a Fabric Modrinth pack](05-import-and-play-fabric-modrinth-pack.md).

**Status:** ready-for-agent

- [ ] Import a representative NeoForge pack and automatically prepare its exact declared loader/game/runtime requirements before Play.
- [ ] Confirm the requested combination is supported; do not substitute Forge or guess compatibility from similar names.
- [ ] Preserve isolated data, pinned release selection, overrides/integrity, lock/cancel/retry behavior, and incomplete-download recovery.
- [ ] Retain the existing vanilla/Fabric journeys and expose unsupported NeoForge combinations as useful errors.
- [ ] Add window-level success/failure/reopen scenarios and bounded live evidence for a supported NeoForge combination, reporting any unverified claims.

## Parent

[Approved specification](../spec.md). Follow its glossary, ADRs, scope limits, and approved launcher-window testing boundary.
