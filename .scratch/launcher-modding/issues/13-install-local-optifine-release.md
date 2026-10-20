# 13: Install a local OptiFine release

**What to build:** Select an official local OptiFine JAR and prepare a supported standalone or compatible Forge setup, with clear incompatible-version/loader errors and no automated OptiFine downloading.

**Blocked by:** [06: Import and play Forge packs](06-import-and-play-forge-packs.md).

**Status:** ready-for-human

- [ ] Accept a player-selected official OptiFine JAR and install a supported standalone setup or a verified compatible Forge setup through the launcher.
- [ ] Check exact game/OptiFine/Forge compatibility against authoritative evidence, preserving the selected instance and existing vanilla/pack worlds.
- [ ] Explain unsupported releases or loader/pack combinations; do not offer OptiFine as universally compatible with modpacks.
- [ ] Do not scrape or assume an automated OptiFine download API; obtaining the official JAR remains outside the automated installation flow.
- [ ] Honor progress, cancellation, locks, readiness, and error recovery; malformed or incompatible inputs cannot be shown as successful installations.
- [ ] Exercise local selection/preparation/Play plus incompatible-input failure through the window seam; collect bounded real launch evidence for the supported standalone and Forge paths or explicitly report validation gaps.

## Parent

[Approved specification](../spec.md). Follow its glossary, ADRs, scope limits, and approved launcher-window testing boundary.

## Comments

Implementation is integrated on `integration/launcher-modding` at `4f29049`. The final automated suite passed (156 tests), and compileall plus `git diff --check` passed. Remaining live/package/desktop acceptance is recorded in issue 17.
