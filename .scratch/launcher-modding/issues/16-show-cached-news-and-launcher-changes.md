# 16: Show cached Minecraft news and launcher changes

**What to build:** Render Minecraft release/news cards and a secondary launcher changelog, cache fetched content, and keep Home and ready-instance launching usable with empty cache, network failures, or offline startup.

**Blocked by:** [03: Ship the Minecraft home and navigation](03-ship-minecraft-home-and-navigation.md).

**Status:** ready-for-human

- [ ] Home shows readable Minecraft release/news cards and a secondary launcher changelog using a verified content source.
- [ ] Cache fetched content for subsequent offline use; empty cache, failed requests, and malformed feed responses produce a usable home screen.
- [ ] Fetching and rendering news must not block window interaction, closing, or launching a ready instance and must not trigger mandatory game updates.
- [ ] Keep bundled/custom background and compact controls readable at default and large window sizes.
- [ ] Test fresh offline startup, cached offline startup, feed failure, and ready-instance launch while news work fails through the window seam; verify the selected live feed contract and rendered layout.

## Parent

[Approved specification](../spec.md). Follow its glossary, ADRs, scope limits, and approved launcher-window testing boundary.

## Comments

Implementation is integrated on `integration/launcher-modding` at `4f29049`. The final automated suite passed (156 tests), and compileall plus `git diff --check` passed. Remaining live/package/desktop acceptance is recorded in issue 17.
