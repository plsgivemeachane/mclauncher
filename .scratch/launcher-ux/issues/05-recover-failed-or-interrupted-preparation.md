# 05: Recover failed or interrupted preparation

**What to build:** Recover from interrupted downloads, preparation failures, or launch errors through the same primary action, with readable progress and errors and no loss of worlds or completed downloads.

**Blocked by:** 03: Choose a stable version and play in one click.

**Status:** ready-for-human

- [x] Show concise, actionable errors directly above the launch bar for download, managed-runtime, readiness, and launch failures. Keep detailed troubleshooting information available through Settings diagnostics.
- [x] Offer retry on the same primary button rather than adding an installation or recovery button to the normal main screen. Successful retry prepares the original pinned version and starts the game exactly once.
- [x] After reopening an interrupted installation, restore its saved selection and pinned version and make recovery available through the normal primary action.
- [x] Reuse completed verified downloads where supported, preserve worlds/settings/screenshots, and avoid accidentally creating a second automatic instance during retry.
- [x] Preserve the original target instance/version while preparation is in flight. Repeated clicks, asynchronous failures, and selection changes must not start a competing operation or apply results to another instance.
- [x] Use determinate or indeterminate progress according to available totals; clear stale progress/errors after recovery. Never show a completed percentage as proof of launch readiness.
- [x] If required local files are missing, explain the need for preparation and its connectivity requirement. A ready instance still launches without a mandatory network repair or update check.
- [x] Add window-level failure/recovery scenarios using existing recovering installers and player adapters: interruption and restart, changed latest-release metadata between attempts, partial preparation failure, missing runtime/files, launch failure, repeated retry clicks, and successful recovery. Check pinned versions, one launch, reusable downloads where observable, and player-data preservation.

## Parent

[01: Implement the approved username → version → Play launcher](01-implement-approved-launcher-design.md). Scope and testing decisions follow the [approved specification](../spec.md).

## Automation evidence

- `tests/test_launcher_ux_ticket05.py` — 7 recovery scenarios pass: restart recovery with a pinned version, retry through Play with one launch, stale ready-marker repair, control locking, connectivity guidance, error clearing, and diagnostic export.
- `tests/test_launcher_app.py` — existing installer/player adapter coverage passes for persisted-version retry after metadata changes, failed-install restart with world preservation, missing-file readiness failures, and launch-failure diagnostics.
- `tests/test_review_findings.py` and `tests/test_review_workers.py` — interrupted close persistence, worker cancellation, and asynchronous operation isolation pass.
- Focused command: `TMPDIR=/tmp/mclauncher-pytest /mnt/e/project/Python/mclauncher/.venv/bin/pytest -q tests/test_launcher_ux_ticket05.py tests/test_review_workers.py tests/test_review_findings.py` → `24 passed`.

The tracker has no closed state, so this remains `ready-for-human` for the real desktop acceptance pass: rendered error/progress placement and a live download/runtime/game recovery journey still need to be exercised on a packaged desktop environment.
