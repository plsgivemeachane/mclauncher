# 06: Adjust and persist game memory limits

**What to build:** See an initial memory limit chosen from available RAM, adjust it in GiB, and launch Minecraft with the saved valid setting.

**Blocked by:** 03: Play an installed instance offline.

**Status:** ready-for-agent

- [ ] Choose and document a conservative initial memory-allocation policy based on available physical RAM.
- [ ] Display memory allocation in GiB and allow the player to adjust and save it through the desktop interface.
- [ ] Restore the chosen memory setting after launcher restart and apply it to game launch.
- [ ] Validate values before starting the game and show actionable errors for invalid allocation without launching Minecraft.
- [ ] Test externally visible defaults, persistence, accepted settings, and rejected settings across representative RAM conditions; demonstrate a real launch with the selected allocation.
