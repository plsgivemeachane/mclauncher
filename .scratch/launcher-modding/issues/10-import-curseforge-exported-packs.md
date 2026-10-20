# 10: Import CurseForge exported packs

**What to build:** Import an exported-pack ZIP into its own instance using supported loaders, prepare accessible required files, and launch. Explain unavailable/restricted files with a permitted recovery action, verify supplied replacements, and keep Play disabled until complete.

**Blocked by:** [06: Import and play Forge packs](06-import-and-play-forge-packs.md).

**Status:** ready-for-agent

- [ ] Import a CurseForge exported-pack ZIP into a distinct instance using its manifest, overrides, declared game version, and supported loader; start with the available Fabric/Forge paths.
- [ ] Resolve accessible required files through permitted provider mechanisms. Archive import must not assume integrated CurseForge catalog access or that every file is embedded.
- [ ] For unavailable/restricted files, show the missing item and a permitted recovery action. If a player supplies a replacement, verify its identity/integrity using available authoritative metadata; reject mismatches and do not claim unknown files verified.
- [ ] Keep Play disabled for an incomplete pack until required files and prerequisites are validated. Preserve retry/reopen recovery and avoid bypassing provider download restrictions.
- [ ] Validate archive/destination paths and integrity, preserve provider identity and independent worlds/settings, and reject arbitrary or malformed ZIPs clearly.
- [ ] Exercise import to Play and missing-file/replacement recovery through the approved window seam; verify manifest and provider access contracts with authoritative evidence and report access-dependent limits.

## Parent

[Approved specification](../spec.md). Follow its glossary, ADRs, scope limits, and approved launcher-window testing boundary.
