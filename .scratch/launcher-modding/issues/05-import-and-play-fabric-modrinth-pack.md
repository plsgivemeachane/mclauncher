# 05: Import and play a Fabric Modrinth pack

**What to build:** Select a .mrpack, create an isolated instance, prepare declared Fabric/Minecraft/runtime/files, and launch. Include source metadata, safe extraction, integrity checks, cancellation/retry, and visible incomplete states.

**Blocked by:** [01: Cancel preparation and close safely](01-cancel-preparation-and-close-safely.md); [02: Lock launch controls for the full session](02-lock-launch-controls-for-the-full-session.md).

**Status:** ready-for-human

- [ ] A player selects a valid Fabric .mrpack, gets a distinct modpack instance, and prepares and plays its declared Minecraft/Fabric release without manually assembling prerequisites.
- [ ] Persist provider/release identity, loader/game requirements, installed content, and recoverable preparation state. Preserve legacy saved setups and separate packs from automatic vanilla instances.
- [ ] Validate the manifest and integrity hashes, resolve required client files, and apply applicable overrides according to the official format. Reject malformed archives, path traversal, absolute/drive paths, and escaping destinations before unsafe writes.
- [ ] Automatically prepare the supported declared loader and managed Java runtime. Explain unsupported combinations; never equate completed progress or a saved flag with actual readiness.
- [ ] Honor cancellation, pinned-target retry, locks, required-download recovery, and single launch. Missing required files keep the instance visibly incomplete and prevent launching it as ready.
- [ ] Different packs or repeated installations of one pack get independent directories even on the same game version; preserve existing worlds/settings on failure and retry.
- [ ] Exercise file picker to import to launch and failure/retry through the approved window seam using representative manifests and controlled artifacts; verify real loader/format contracts before claiming live compatibility.

## Parent

[Approved specification](../spec.md). Follow its glossary, ADRs, scope limits, and approved launcher-window testing boundary.

## Comments

Implementation is integrated on `integration/launcher-modding` at `4f29049`. The final automated suite passed (156 tests), and compileall plus `git diff --check` passed. Remaining live/package/desktop acceptance is recorded in issue 17.
