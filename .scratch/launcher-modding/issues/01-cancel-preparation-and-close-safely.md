# 01: Cancel preparation and close safely

**What to build:** Close during active or stalled downloads, exit promptly, and safely retry the pinned setup using completed verified downloads. Preserve a running game on close.

**Blocked by:** None (can start immediately).

**Status:** ready-for-human

- [ ] Closing during active or stalled preparation cancels work and permits prompt application exit without waiting for the entire download or an indefinitely stalled request; the window remains responsive.
- [ ] Persist the interrupted instance and pinned version without marking partial preparation ready. Reopening offers recovery through Play for the same instance.
- [ ] Reuse completed verified artifacts where supported; reject or repair partial/unverified files and preserve worlds, settings, and screenshots.
- [ ] Late worker results cannot mark a cancelled installation complete, launch the game, or modify another selected instance.
- [ ] Closing while Minecraft is already running leaves its detached process alive and discoverable after reopening.
- [ ] Replace the old close-rejection regression. Use window-level held-download scenarios and a bounded real application-process exit check, plus reopen/retry and detached-process survival checks.

## Parent

[Approved specification](../spec.md). Follow its glossary, ADRs, scope limits, and approved launcher-window testing boundary.

## Comments

Implementation is integrated on `integration/launcher-modding` at `4f29049`. The final automated suite passed (156 tests), and compileall plus `git diff --check` passed. Remaining live/package/desktop acceptance is recorded in issue 17.
