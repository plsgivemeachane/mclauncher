# 01: Save a local identity and create an instance

**What to build:** Open the desktop launcher, save a local username, create a named instance, and restore the saved setup after restarting.

**Blocked by:** None (can start immediately).

**Status:** ready-for-human

- [x] Provide a runnable Python/PySide6 desktop application with username entry, named-instance creation, and a view of the created instance.
- [x] Persist the username and instance information across launcher restarts.
- [x] Derive a deterministic local player identity from the username; unchanged usernames retain identity across restarts.
- [x] Before saving a changed username, warn that worlds or servers may recognize a different player; changing the username changes local player identity.
- [ ] Keep launcher-managed data separate from existing Minecraft installations.
- [x] Add application-boundary behavior tests for creation, persistence, and identity changes; demonstrate the desktop flow.

## Comments

Implementation and application-boundary tests are included in the passing 41-test suite. The exact packaged app saved AcceptanceUser and created the Acceptance instance in the clean GUI flow. Cross-restart identity stability and the rename warning were not manually exercised in this packaged run.
