# 15: Update imported CurseForge packs

**What to build:** Apply a selected newer exported-pack ZIP to the existing instance through the backed-up update journey, retaining provider identity and handling missing/restricted files without requiring integrated CurseForge browsing.

**Blocked by:** [10: Import CurseForge exported packs](10-import-curseforge-exported-packs.md); [14: Update Modrinth packs with recovery](14-update-modrinth-packs-with-recovery.md).

**Status:** ready-for-human

- [ ] Choose a newer exported-pack ZIP to explicitly update an existing CurseForge instance while retaining its identity and independent player data.
- [ ] Reuse backed-up update behavior: backup before replacement, preserve worlds, warn about local changes, and publish the release only after complete preparation.
- [ ] Handle provider-restricted/missing required files through verified permitted recovery and preserve the previous or recoverable state on failure.
- [ ] Do not require integrated CurseForge browsing, silently update, or replace the instance with an unrelated pack without explanation.
- [ ] Exercise replacement-export update, interruption/reopen, restricted-file recovery, and rollback with real fixture files through the window seam; preserve working Modrinth updates.

## Parent

[Approved specification](../spec.md). Follow its glossary, ADRs, scope limits, and approved launcher-window testing boundary.

## Comments

Implementation is integrated on `integration/launcher-modding` at `4f29049`. The final automated suite passed (156 tests), and compileall plus `git diff --check` passed. Remaining live/package/desktop acceptance is recorded in issue 17.
