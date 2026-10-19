# 07: Verify the complete packaged player journey

**What to build:** Demonstrate that the integrated redesign works as an installed Ubuntu desktop application, matches approved layout A, and preserves existing worlds and disconnected play. Record concrete evidence and any unresolved acceptance gaps.

**Blocked by:** 02: Play existing setups in the approved interface; 03: Choose a stable version and play in one click; 04: Find versions and enable snapshots; 05: Recover failed or interrupted preparation; 06: Follow running games across launcher restarts.

**Status:** ready-for-agent

- [ ] Run the relevant automated launcher, persistence, installation, memory, lifecycle, and packaging checks after integration and record the exact commands/results. Fix integration regressions before acceptance.
- [ ] Install and open the built package on the supported Ubuntu 24.04 x86-64 target through the desktop entry without separately installing Python or Java. Record package identity and environment.
- [ ] On clean data, enter a username, choose a stable version, press Play once, observe preparation, and reach the real game. Create and save a world, exit, disconnect the network, reopen the launcher, and reopen that world.
- [ ] Open representative legacy data with multiple named instances, including instances sharing a version, and demonstrate access to their distinct worlds. Verify pinned versions, usernames, memory settings, screenshots, and an external Minecraft installation remain intact.
- [ ] Demonstrate a second version using its separate automatic instance, version search/downloaded markers, snapshot preference persistence, and remembered concrete selection without silent upgrades.
- [ ] Demonstrate an interrupted preparation/retry and game close/reopen lifecycle journey. Verify usable progress/errors, one-button recovery, preserved game data, a game surviving launcher closure, and duplicate-launch protection.
- [ ] Compare actual PySide6 rendering with prototype layout A at the reference size and smaller supported desktop sizes/display scaling. Inspect idle, Settings, selector, empty search, determinate/indeterminate progress, failure, starting, and running states; fix clipping, unreadable contrast, focus, and wrapping problems.
- [ ] Confirm no prototype switcher/demo state controls, separate Save/Install buttons, main-screen memory/identity administration, or promotional/news panels ship in the product.
- [ ] Collect packaged screenshots and player-visible evidence. If graphics limitations prevent reaching the menu or saving/reopening worlds, explicitly record those as unresolved acceptance gaps rather than inferring success from JVM startup or mocked tests.
- [ ] Report final validation results and remaining limitations against the specification; preserve the approved prototype reference and keep experimental prototype code separate from production.

## Parent

[01: Implement the approved username → version → Play launcher](01-implement-approved-launcher-design.md). Scope and testing decisions follow the [approved specification](../spec.md).
