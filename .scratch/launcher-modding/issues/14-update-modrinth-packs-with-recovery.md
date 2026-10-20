# 14: Update Modrinth packs with recovery

**What to build:** Explicitly choose a new pack release or replacement archive, back up the instance, warn about changed local files, preserve worlds, apply the update, and recover from interruption or failure without publishing a partial release as ready.

**Blocked by:** [09: Browse and install Modrinth packs](09-browse-and-install-modrinth-packs.md).

**Status:** ready-for-human

- [ ] An existing Modrinth instance can explicitly select a new catalog release or replacement .mrpack for update without creating an unintended new instance.
- [ ] Create a usable recovery backup before replacing content, preserve worlds, and warn before replacing locally changed mods/configuration.
- [ ] Preserve source/instance identity and record the new release only after its required preparation is complete; never update installed packs silently.
- [ ] Cancellation, missing files, integrity errors, or interruption leave a recoverable state, not a partially published ready release.
- [ ] Provide a recovery path using the backup and verify its actual contents; refuse updates of an instance being prepared or played.
- [ ] Test explicit update/reopen, changed local files, worlds, backup failure, mid-update interruption, successful recovery, and no background update through the window seam with temporary instance data.

## Parent

[Approved specification](../spec.md). Follow its glossary, ADRs, scope limits, and approved launcher-window testing boundary.

## Comments

Implementation is integrated on `integration/launcher-modding` at `4f29049`. The final automated suite passed (156 tests), and compileall plus `git diff --check` passed. Remaining live/package/desktop acceptance is recorded in issue 17.
