# 01: Implement the approved username → version → Play launcher

Status: ready-for-agent

**What to build:** Implement [the approved UX specification](../spec.md) using prototype layout A as the visual reference, keeping existing instances and worlds accessible.

**Blocked by:** Nothing; existing launcher, installation, persistence, and lifecycle boundaries are available.

- [ ] Replace the default form with the compact dark landscape window and bottom username/version/Play bar.
- [ ] Provide searchable stable versions, downloaded markers, grouped named existing setups, first-use latest stable, and remembered selection.
- [ ] Create/reuse isolated automatic instances for version choices without merging or moving legacy setups.
- [ ] Make Play prepare missing components and launch exactly once; ready local instances remain playable offline.
- [ ] Show progress, starting/running status, failures, and retry in the same launch area.
- [ ] Automatically save valid username and Settings edits; place memory, snapshots, folder access, and diagnostics in Settings.
- [ ] Preserve the memory policy, identity behavior, player data, recovery protections, and process lifecycle guarantees.
- [ ] Extend existing window-level interaction coverage and focused integration checks as specified.
- [ ] Compare real PySide6 rendering against layout A, including smaller desktop sizes, keyboard use, and non-idle states.
- [ ] Record real packaged acceptance evidence and distinguish outstanding graphics/world-persistence gaps from automated results.

## Comments

The user approved the visual prototype and requested spec publication. This is an implementation ticket, not a claim that the redesign is already built. The complete specification defines decisions, compatibility boundaries, testing strategy, and scope.
