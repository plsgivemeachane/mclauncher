# 04: Find versions and enable snapshots

**What to build:** Find a version or saved setup quickly through a searchable grouped selector, see downloaded choices, intentionally enable snapshots, and keep useful selections available when version discovery is unavailable.

**Blocked by:** 03: Choose a stable version and play in one click.

**Status:** ready-for-agent

- [ ] Provide searchable selector groups for stable versions and saved setups, with names that distinguish multiple existing instances. Display an understandable no-results state without changing the current selection.
- [ ] Mark locally downloaded versions based on the corresponding automatic instance and actual readiness. A downloaded marker must not bypass required-file/runtime checks or confuse readiness of a separate named instance.
- [ ] Add an automatically saved Show snapshots preference in Settings, defaulting to off for both new and legacy state. Enabling it exposes searchable experimental choices; selecting one uses the same isolated one-click preparation/launch journey.
- [ ] Disabling snapshot discovery does not delete instances or conceal an existing saved setup containing snapshot worlds. Preserve access to already-created experimental setups and their pinned versions.
- [ ] Cache usable version metadata and restore cached choices when discovery fails. Keep installed saved setups playable without connectivity, and explain when a new selection needs a download rather than implying it is ready.
- [ ] Preserve the last selected concrete version or saved setup across search, filtering, metadata refresh, and reopening; optional discovery failures must not replace it with a newer release.
- [ ] Add window-level tests for search/no-results behavior, grouping, duplicate legacy version names, downloaded/readiness distinctions, snapshot opt-in persistence, disabling snapshots after installation, cached disconnected discovery, invalid preference data, and offline ready-instance launch.
- [ ] Inspect open-selector behavior with keyboard navigation, long names, smaller desktop widths, and readable selected/downloaded states.

## Parent

[01: Implement the approved username → version → Play launcher](01-implement-approved-launcher-design.md). Scope and testing decisions follow the [approved specification](../spec.md).
