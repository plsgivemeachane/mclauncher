# 03: Ship the Minecraft home and navigation

**What to build:** Replace the landscape with bundled Minecraft imagery, custom background selection, compact launch controls, and working Home/Instances navigation. Introduce Browse when its catalog lands; avoid a dead destination.

**Blocked by:** None (can start immediately).

**Status:** ready-for-human

- [ ] Replace the painted flat landscape with a bundled, distributable Minecraft screenshot background and readable foreground content.
- [ ] Allow custom image selection, persist it across reopening, and retain a usable bundled fallback when the custom image cannot be loaded.
- [ ] Provide working Home and Instances navigation and preserve access to existing saved setups. Add Browse with its functioning catalog in ticket 09 rather than a dead navigation destination.
- [ ] Retain compact bottom username, selected setup, and single Play controls, Settings access, saved selection, and automatic vanilla setup behavior.
- [ ] Artwork loading must not require network access or gate launching a ready instance. Integrate existing lifecycle locks and progress without redesigning their contracts.
- [ ] Update superseded layout assertions and review rendered windows at compact default and supplied large-window sizes for readable controls, background cropping, and responsive layout.

## Parent

[Approved specification](../spec.md). Follow its glossary, ADRs, scope limits, and approved launcher-window testing boundary.

## Comments

Implementation is integrated on `integration/launcher-modding` at `4f29049`. The final automated suite passed (156 tests), and compileall plus `git diff --check` passed. Remaining live/package/desktop acceptance is recorded in issue 17.
