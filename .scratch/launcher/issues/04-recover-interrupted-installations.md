# 04: Recover interrupted installations

**What to build:** Retry a failed or interrupted installation from the desktop interface while reusing valid completed downloads and preserving player data.

**Blocked by:** 02: Install Minecraft and managed Java.

**Status:** ready-for-human

- [ ] Present readable failure information and an explicit retry action for failed or interrupted installation.
- [ ] On retry, retain the instance pinned version even if a newer stable release is now available.
- [ ] Reuse completed verified downloads and recover missing or corrupt installation files without discarding existing worlds or settings.
- [ ] Keep the instance unready until required setup succeeds; an interrupted operation must not be mistaken for completion after restarting the launcher.
- [ ] Begin recovery downloads only after the player requests retry and report progress without freezing the interface.
- [ ] Exercise interrupted downloads, a failed request, a corrupt downloaded file, and retry across launcher restart through application-boundary tests and a demonstrated recovery flow.

## Comments

Implementation and automated coverage are included in the passing suite. This acceptance run did not interrupt and retry a real download, test reuse of completed files, or demonstrate recovery across a launcher restart.
