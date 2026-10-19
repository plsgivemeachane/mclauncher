# 02: Play existing setups in the approved interface

**What to build:** Play an installed existing instance through approved layout A: enter a username, choose a saved setup, and press Play. Adjust memory and access diagnostics through Settings rather than the main screen.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Implement the compact PySide6 landscape window with charcoal surfaces, warm white text, a green Play action, a small Settings entry, and a solid bottom launch bar. Use the approved layout A reference and its approximately 920 × 560 initial desktop size; exclude prototype comparison controls.
- [ ] List every existing named instance in the selector, including distinct instances using the same version. Launch the selected ready instance using its existing identifier and directory without requiring network access or moving player data.
- [ ] Automatically save valid username edits on editing completion and commit pending valid edits before Play. Restore the username and last saved-setup selection after reopening; explain invalid input without overwriting the last valid value.
- [ ] Preserve deterministic local player identity and communicate username-change consequences without a permanent second action or visible identity UUID.
- [ ] Move memory allocation, selected-instance folder access, and diagnostic export into Settings. Automatically save valid memory edits, explain invalid edits, and retain the existing default/range policy and last valid value.
- [ ] Remove separate save and installation controls, the large instance list, instance-creation form, and memory field from the normal main screen. Show status/errors near Play and progress only when relevant.
- [ ] Preserve legacy state compatibility, instance/world/settings/screenshot data, external Minecraft isolation, corruption backup/recovery protections, and existing duplicate-launch/process-lifetime behavior while replacing controls.
- [ ] Adapt existing launcher-window interaction coverage for saved-setup selection, direct ready-instance launch, automatic saving, invalid edits, Settings actions, restart restoration, and unrecovered corrupt state. Assert visible behavior and preserved outcomes rather than widget nesting.
- [ ] Demonstrate the saved-setup journey with keyboard navigation and visible focus, and inspect the rendered idle window and Settings against layout A. Archive the approved prototype experiments on a throwaway branch as part of integrating the production design, preserving the design reference.

## Parent

[01: Implement the approved username → version → Play launcher](01-implement-approved-launcher-design.md). Scope and testing decisions follow the [approved specification](../spec.md).
