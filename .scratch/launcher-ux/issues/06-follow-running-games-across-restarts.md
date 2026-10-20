# 06: Follow running games across launcher restarts

**What to build:** Understand starting, running, normal-exit, and crash states in the compact interface, including games that continue after the launcher closes and are detected when it reopens.

**Blocked by:** 02: Play existing setups in the approved interface.

**Status:** ready-for-agent

- [ ] Present starting and running states near the primary control and explain why another launch is unavailable. Do not add a second launch action or expose raw lifecycle identifiers.
- [ ] Prevent duplicate launches during startup and while a managed game is running, including attempts from another launcher window. Preserve the established instance-bound lifecycle/locking behavior.
- [ ] Closing the launcher leaves Minecraft running. Reopening recognizes the original live process and shows the running state while retaining safe launch restrictions.
- [ ] After normal game exit, make Play available again with a clear status. After a crash, show a readable failure and keep diagnostic export accessible through Settings.
- [ ] Handle stale process records safely so an unrelated process or reused process number is not treated as the managed game and launch availability recovers correctly.
- [ ] Keep lifecycle messages associated with the correct instance when saved selection changes, and keep running-instance diagnostics/folder access unambiguous.
- [ ] Extend the existing launcher-window and focused lifecycle integration scenarios for startup, concurrent attempts, launcher close/reopen, adoption, normal exit, crash, stale records, and selection changes. Retain real process-lifetime checks where UI adapters alone cannot establish the guarantee.
- [ ] Inspect rendered starting, running, and crash states for clear labels, readable wrapping, keyboard access to Settings, and consistent visual hierarchy.

## Parent

[01: Implement the approved username → version → Play launcher](01-implement-approved-launcher-design.md). Scope and testing decisions follow the [approved specification](../spec.md).
