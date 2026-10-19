# 03: Choose a stable version and play in one click

**What to build:** From a fresh launcher, select a stable Minecraft version and press Play once to create its isolated instance, prepare Minecraft and managed Java, and start an offline session. Returning players reopen the same concrete version and worlds.

**Blocked by:** 02: Play existing setups in the approved interface.

**Status:** ready-for-agent

- [ ] Discover stable releases asynchronously through the existing installation boundary, keep the desktop responsive, and initially select the latest stable release when no prior selection exists.
- [ ] Expose concrete stable-version choices alongside existing saved setups. Preserve existing saved choices and ready offline play when discovery fails; provide a readable discovery error rather than an empty replacement selector.
- [ ] Browsing or selecting a version does not create instance directories or download game components. Pressing Play creates or reuses the automatic instance associated with that concrete version.
- [ ] Persist the version-to-instance association and last selection using backward-compatible defaults. Repeated requests reuse that automatic instance, while existing named instances remain separate and individually selectable even when their versions match.
- [ ] Resolve the first-use latest stable choice to a concrete version before preparation, remember that concrete choice, and never silently upgrade an existing instance when metadata announces a newer release.
- [ ] One Play action validates input, prepares missing Minecraft components and the managed Java runtime, validates readiness, and launches exactly once after success. Ready instances launch directly without installation or metadata requests as prerequisites.
- [ ] Show real preparation progress above the launch bar, including indeterminate progress when totals are unknown. Keep the primary control visibly busy and prevent competing requests or selection changes from redirecting an in-flight operation.
- [ ] On failure, show a readable error and do not launch an incomplete instance. Preserve the concrete pinned version and player data for subsequent recovery.
- [ ] Add window-level scenarios with deterministic release metadata and installer/player adapters for fresh one-click install-and-launch, ready offline launch, concrete-version restoration, automatic-instance reuse, two-version isolation, existing named setups, metadata failure, newer-release discovery, and repeated clicks.

## Parent

[01: Implement the approved username → version → Play launcher](01-implement-approved-launcher-design.md). Scope and testing decisions follow the [approved specification](../spec.md).
