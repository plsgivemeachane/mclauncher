# 01: Implement the approved username → version → Play launcher

Status: ready-for-human

**What to build:** Implement [the approved UX specification](../spec.md) using prototype layout A as the visual reference, keeping existing instances and worlds accessible.

**Blocked by:** Nothing; existing launcher, installation, persistence, and lifecycle boundaries are available.

- [x] Replace the default form with the compact dark landscape window and bottom username/version/Play bar.
- [x] Provide searchable stable versions, downloaded markers, grouped named existing setups, first-use latest stable, and remembered selection.
- [x] Create/reuse isolated automatic instances for version choices without merging or moving legacy setups.
- [x] Make Play prepare missing components and launch exactly once; ready local instances remain playable offline.
- [x] Show progress, starting/running status, failures, and retry in the same launch area.
- [x] Automatically save valid username and Settings edits; place memory, snapshots, folder access, and diagnostics in Settings.
- [x] Preserve the memory policy, identity behavior, player data, recovery protections, and process lifecycle guarantees.
- [x] Extend existing window-level interaction coverage and focused integration checks as specified.
- [ ] Compare real PySide6 rendering against layout A, including smaller desktop sizes, keyboard use, and non-idle states.
- [ ] Record real packaged acceptance evidence and distinguish outstanding graphics/world-persistence gaps from automated results.

## Comments

The user approved the visual prototype and requested spec publication. This is an implementation ticket, not a claim that the redesign is already built. The complete specification defines decisions, compatibility boundaries, testing strategy, and scope.

Implementation evidence on the integration branch: the launcher-window checks in `tests/test_launcher_ux_ticket02.py` through `tests/test_launcher_ux_ticket06.py`, `tests/test_game_lifecycle.py`, `tests/test_launcher_app.py`, `tests/test_review_findings.py`, and `tests/test_review_workers.py` pass together (`56 passed`). They cover the visible launch bar, saved setup selection, username/settings persistence, version discovery/search and snapshots, isolated automatic instances, one-click preparation/retry, progress, failure, readiness, lifecycle adoption, and recovery boundaries.

Remaining acceptance is intentionally human-led: compare real PySide6 rendering at the reference and smaller desktop sizes across idle, selector, settings, progress, failure, starting, and running states; then record packaged-player evidence including real graphics/world persistence and disconnected relaunch. These are left unchecked because the offscreen automated suite and package smoke checks cannot establish them.
