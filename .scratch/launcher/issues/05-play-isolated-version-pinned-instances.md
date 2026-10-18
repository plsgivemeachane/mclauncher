# 05: Play multiple isolated, version-pinned instances

**What to build:** Create and select multiple named instances, play their separate worlds, and keep existing instances unchanged when newer Minecraft releases appear.

**Blocked by:** 03: Play an installed instance offline.

**Status:** ready-for-human

- [ ] Create, list, persist, and select multiple named instances, with actions applying to the selected instance.
- [ ] Keep worlds, game settings, and screenshots separate between instances and from existing Minecraft installations.
- [ ] Use the latest stable release for newly requested installations while keeping existing instances pinned and playable.
- [ ] Never automatically upgrade existing instances or their worlds; do not expose arbitrary historical-version or snapshot installation.
- [ ] Reuse the saved local username and deterministic identity consistently across instances.
- [ ] Test version changes using controlled release metadata, verify isolation through player-visible outcomes, and demonstrate saving and reopening distinct worlds in two instances.
- [ ] Verify a pre-existing external Minecraft installation remains unchanged.

## Comments

Implementation and automated coverage are included in the passing suite. The packaged journey used one instance; separate real worlds, changed-release behavior, and preservation of a pre-existing external installation were not demonstrated in this run.
