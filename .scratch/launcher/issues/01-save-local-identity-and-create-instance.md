# 01: Save a local identity and create an instance

**What to build:** Open the desktop launcher, save a local username, create a named instance, and restore the saved setup after restarting.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Provide a runnable Python/PySide6 desktop application with username entry, named-instance creation, and a view of the created instance.
- [ ] Persist the username and instance information across launcher restarts.
- [ ] Derive a deterministic local player identity from the username; unchanged usernames retain identity across restarts.
- [ ] Before saving a changed username, warn that worlds or servers may recognize a different player; changing the username changes local player identity.
- [ ] Keep launcher-managed data separate from existing Minecraft installations.
- [ ] Add application-boundary behavior tests for creation, persistence, and identity changes; demonstrate the desktop flow.
