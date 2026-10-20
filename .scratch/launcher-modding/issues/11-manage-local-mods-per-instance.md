# 11: Manage local mods per instance

**What to build:** List mods, import compatible local JARs, enable/disable/remove them, and persist changes. Reject known incompatibility, explain unknown metadata, warn about curated-pack changes, and mark additions as modifications.

**Blocked by:** [05: Import and play a Fabric Modrinth pack](05-import-and-play-fabric-modrinth-pack.md).

**Status:** ready-for-human

- [ ] The selected instance has a Mods page listing installed content and persisted enabled/disabled state.
- [ ] Import a compatible local mod JAR only into that instance, rejecting known game/loader incompatibility and explaining unknown metadata without presenting it as verified.
- [ ] Enable, disable, and remove individual mods, retain changes after reopening, and keep disabled content from being treated as active.
- [ ] Warn about curated-pack compatibility when adding a mod and visibly mark the instance as modified.
- [ ] Protect active preparation/running instances from mutation and preserve other instances and player worlds/settings.
- [ ] Use window-level import/toggle/remove/reopen and incompatible/unknown-metadata scenarios that assert actual instance content and modified state.

## Parent

[Approved specification](../spec.md). Follow its glossary, ADRs, scope limits, and approved launcher-window testing boundary.

## Comments

Implementation is integrated on `integration/launcher-modding` at `4f29049`. The final automated suite passed (156 tests), and compileall plus `git diff --check` passed. Remaining live/package/desktop acceptance is recorded in issue 17.
