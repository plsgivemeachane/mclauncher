# 06: Import and play Forge packs

**What to build:** Extend the working pack journey to declared Forge versions, with real readiness validation and useful unsupported-combination errors.

**Blocked by:** [05: Import and play a Fabric Modrinth pack](05-import-and-play-fabric-modrinth-pack.md).

**Status:** ready-for-human

- [ ] Import a representative Forge pack through the established archive flow, automatically prepare its exact declared Forge/game/runtime requirements, and launch that instance.
- [ ] Validate actual supported Forge combinations against official sources; present a useful error for unsupported releases rather than silently substituting another loader/version.
- [ ] Preserve file integrity checks, overrides, independent instance identity, progress, locks, cancellation/retry, and missing-file readiness rules.
- [ ] Keep existing Fabric and vanilla preparation/launch behavior working.
- [ ] Add window-level Forge success/failure/reopen cases and collect bounded live installation/launch evidence for a supported combination, explicitly reporting validation gaps.

## Parent

[Approved specification](../spec.md). Follow its glossary, ADRs, scope limits, and approved launcher-window testing boundary.

## Comments

Implementation is integrated on `integration/launcher-modding` at `4f29049`. The final automated suite passed (156 tests), and compileall plus `git diff --check` passed. Remaining live/package/desktop acceptance is recorded in issue 17.
