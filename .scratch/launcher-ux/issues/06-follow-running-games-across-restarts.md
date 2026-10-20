# 06: Follow running games across launcher restarts

**What to build:** Understand starting, running, normal-exit, and crash states in the compact interface, including games that continue after the launcher closes and are detected when it reopens.

**Blocked by:** 02: Play existing setups in the approved interface.

**Status:** ready-for-human

- [x] Present starting and running states near the primary control and explain why another launch is unavailable. Do not add a second launch action or expose raw lifecycle identifiers.
- [x] Prevent duplicate launches during startup and while a managed game is running, including attempts from another launcher window. Preserve the established instance-bound lifecycle/locking behavior.
- [x] Closing the launcher leaves Minecraft running. Reopening recognizes the original live process and shows the running state while retaining safe launch restrictions.
- [x] After normal game exit, make Play available again with a clear status. After a crash, show a readable failure and keep diagnostic export accessible through Settings.
- [x] Handle stale process records safely so an unrelated process or reused process number is not treated as the managed game and launch availability recovers correctly.
- [x] Keep lifecycle messages associated with the correct instance when saved selection changes, and keep running-instance diagnostics/folder access unambiguous.
- [x] Extend the existing launcher-window and focused lifecycle integration scenarios for startup, concurrent attempts, launcher close/reopen, adoption, normal exit, crash, stale records, and selection changes. Retain real process-lifetime checks where UI adapters alone cannot establish the guarantee.
- [ ] Inspect rendered starting, running, and crash states for clear labels, readable wrapping, keyboard access to Settings, and consistent visual hierarchy.

## Comments

- Automated implementation is complete on the integration tip. Lifecycle records capture PID start time, executable, and command line; stale records and PID reuse are rejected; the launcher preserves a detached game across close/reopen; normal exit and crash states release the lock and retain instance-bound diagnostics; selection changes do not retarget running-game actions.
- The waiting-for-lock handoff now restores the persisted instance association before showing the running state, keeping concurrent launcher attempts bound to the correct setup.
- Verification: `TMPDIR=/tmp /mnt/e/project/Python/mclauncher/.venv/bin/python -m pytest -q tests/test_game_lifecycle.py tests/test_launcher_app.py` → 29 passed. Coverage includes startup/duplicate launch protection, concurrent lock handoff, real child-process close/reopen survival, adoption, normal exit, crash diagnostics, stale records, and selection changes.
- The final checklist item remains open for human desktop acceptance: inspect rendered starting/running/crash states, labels/wrapping, keyboard focus, and Settings access.

## Parent

[01: Implement the approved username → version → Play launcher](01-implement-approved-launcher-design.md). Scope and testing decisions follow the [approved specification](../spec.md).
