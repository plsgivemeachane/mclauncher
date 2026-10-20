# 02: Lock launch controls for the full session

**What to build:** Lock username, selected setup, and launch settings from Play through game exit, including adopted games after reopening; unlock on failure or exit and prevent duplicate launches.

**Blocked by:** None (can start immediately).

**Status:** ready-for-human

- [ ] Lock username, setup selection, and launch settings immediately when Play starts and keep them locked during preparation and the running game.
- [ ] Keep operation identity and instance fixed; repeated Play actions cannot cause a second preparation or launch.
- [ ] On preparation failure, launch failure, or game exit restore appropriate controls and show the existing recovery/status behavior.
- [ ] Reopening while a managed game is still alive restores the locks; detecting that game exit unlocks the controls.
- [ ] Keep non-mutating navigation and window closing usable. Instance-changing operations must not modify an active preparation target or running setup.
- [ ] Verify observable controls, launch targets/counts, and failure recovery through the approved window seam; extend real-process adoption and exit scenarios.

## Parent

[Approved specification](../spec.md). Follow its glossary, ADRs, scope limits, and approved launcher-window testing boundary.

## Comments

Implementation is integrated on `integration/launcher-modding` at `4f29049`. The final automated suite passed (156 tests), and compileall plus `git diff --check` passed. Remaining live/package/desktop acceptance is recorded in issue 17.
