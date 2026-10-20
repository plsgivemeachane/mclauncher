# 09: Browse and install Modrinth packs

**What to build:** Search in Browse, inspect pack details/releases, select a compatible release, install, and Play through the established instance preparation flow. Additional loader support follows its own tickets.

**Blocked by:** [03: Ship the Minecraft home and navigation](03-ship-minecraft-home-and-navigation.md); [05: Import and play a Fabric Modrinth pack](05-import-and-play-fabric-modrinth-pack.md).

**Status:** ready-for-human

- [ ] Browse opens a working integrated Modrinth pack catalog with search, pack details, available releases, and release selection.
- [ ] Installing the selected release creates an independent instance and uses the established preparation-to-Play flow, retaining provider/release identity.
- [ ] Offer combinations supported by completed loader work and explain unsupported requirements; do not wait for all loader tickets to deliver a working Fabric catalog path.
- [ ] Catalog failures/empty results show useful status and do not prevent launching already ready instances. Repeated requests cannot install the wrong selected release or start duplicate work.
- [ ] Catalog installation preserves cancellation, integrity validation, progress, readiness, and recovery; do not replace the integrated experience with an external download instruction.
- [ ] Use controlled provider responses for search/details/install/Play, empty/failure cases, and exact-release assertions; separately verify live Modrinth contracts and one bounded end-to-end sample.

## Parent

[Approved specification](../spec.md). Follow its glossary, ADRs, scope limits, and approved launcher-window testing boundary.

## Comments

Implementation is integrated on `integration/launcher-modding` at `4f29049`. The final automated suite passed (156 tests), and compileall plus `git diff --check` passed. Remaining live/package/desktop acceptance is recorded in issue 17.
