# 08: Import and play Quilt packs

**What to build:** Extend the working pack journey to declared Quilt versions while preserving isolated data, recovery, and exact release selection.

**Blocked by:** [05: Import and play a Fabric Modrinth pack](05-import-and-play-fabric-modrinth-pack.md).

**Status:** ready-for-agent

- [ ] Import a representative Quilt pack and automatically prepare its exact declared loader/game/runtime requirements before Play.
- [ ] Verify supported combinations and declared dependencies without assuming Quilt and Fabric are interchangeable.
- [ ] Preserve isolated data, pinned release selection, overrides/integrity, lock/cancel/retry behavior, and incomplete-download recovery.
- [ ] Retain existing vanilla/Fabric journeys and explain unsupported Quilt combinations without claiming readiness.
- [ ] Add window-level success/failure/reopen scenarios and bounded live evidence for a supported Quilt combination, reporting any unverified claims.

## Parent

[Approved specification](../spec.md). Follow its glossary, ADRs, scope limits, and approved launcher-window testing boundary.
