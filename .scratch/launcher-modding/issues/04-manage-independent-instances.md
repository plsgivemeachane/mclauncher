# 04: Manage independent instances

**What to build:** Name, duplicate, and confirm deletion of saved instances from Instances, preserving independent data and warning about world loss. Retain existing vanilla setups.

**Blocked by:** [03: Ship the Minecraft home and navigation](03-ship-minecraft-home-and-navigation.md).

**Status:** ready-for-agent

- [ ] From Instances, rename an instance without changing its identity, source metadata, or data directory; retain the name after reopening.
- [ ] Duplicate an instance with a new identity and independent copied worlds/settings/content; changes to the duplicate cannot modify the original.
- [ ] Permit multiple installations of the same pack without merging their data. Preserve all available source, loader, and modification metadata when copying a setup.
- [ ] Deletion identifies the selected instance and explicitly warns about removing its worlds. Cancelling leaves data intact; confirming removes only the intended instance and updates selection safely.
- [ ] Refuse mutations of an instance being prepared or played. Preserve existing vanilla instances and version associations.
- [ ] Use window-level temporary-storage scenarios for rename/reopen, file independence, confirmed/cancelled deletion, and active-instance protection; final integration adds pack-specific coverage as those flows land.

## Parent

[Approved specification](../spec.md). Follow its glossary, ADRs, scope limits, and approved launcher-window testing boundary.
