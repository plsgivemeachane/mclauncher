# 07: Keep games running across launcher restarts

**What to build:** Close the launcher without closing Minecraft, reopen it to see the running game, and prevent a second launcher-managed game until the first exits.

**Blocked by:** 03: Play an installed instance offline.

**Status:** ready-for-human

- [ ] Closing the launcher leaves its running Minecraft game alive.
- [ ] Reopening detects the same running game, restores its running status, and enforces the one-game limit across all instances.
- [ ] Do not treat a saved process number alone as proof of the original running game; handle stale records and process-number reuse safely.
- [ ] Prevent competing launches from concurrent launcher starts, not only repeated clicks in one window.
- [ ] After the game exits or crashes, clear running state appropriately and allow another launch without terminating unrelated processes.
- [ ] Test lifecycle behavior at the application boundary and demonstrate close/reopen detection with real Minecraft; exercise stale records and concurrent launch attempts deterministically.

## Comments

Implementation and automated coverage are included in the passing suite. The real Minecraft process reached startup but stopped at the Xvfb graphics boundary, so close/reopen detection, process lifetime, and concurrent-launch behavior were not demonstrated with a playable game.
