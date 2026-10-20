# 12: Find and install individual Modrinth mods

**What to build:** Search compatible mods from the instance Mods page, prepare required dependencies, install into that instance, and launch; preserve recovery, compatibility, and modified-pack behavior.

**Blocked by:** [09: Browse and install Modrinth packs](09-browse-and-install-modrinth-packs.md); [11: Manage local mods per instance](11-manage-local-mods-per-instance.md).

**Status:** ready-for-human

- [ ] From an instance Mods page, search Modrinth for suitable mods and select a release matching the instance game/loader requirements.
- [ ] Install the selected mod and required compatible dependencies into that instance without duplicate or competing installations.
- [ ] Preserve compatibility rejection, curated-pack warnings/modified state, active-instance locks, integrity checks, progress, and missing-download recovery.
- [ ] Failures leave understandable recovery and do not silently present incomplete changed content as ready; reopening retains the outcome.
- [ ] Verify search to installation to Play through the window seam with controlled dependency success/conflict/failure responses, then verify real provider contract behavior.

## Parent

[Approved specification](../spec.md). Follow its glossary, ADRs, scope limits, and approved launcher-window testing boundary.

## Comments

Implementation is integrated on `integration/launcher-modding` at `4f29049`. The final automated suite passed (156 tests), and compileall plus `git diff --check` passed. Remaining live/package/desktop acceptance is recorded in issue 17.
