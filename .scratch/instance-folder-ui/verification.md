# Instance folders and UI verification

- Open Folder stays next to Play on every page, with matching 146×47 rendered buttons.
- Open Folder follows the selected instance and opens its actual Minecraft game directory.
- Open Screenshots opens/creates that instance's minecraft/screenshots directory.
- Diagnostic folder access in Settings retains the active/last game target.
- Instances uses a centered two-column layout with independent scrollable library/tools and no orphan settings labels.
- Home retains username/setup controls; other pages use the smaller persistent launch bar.
- Qt renders visually inspected at 680×420, 920×560, and 1885×1010. Small-window scrolling is tested for full control reachability.
- File-manager dispatch is tested through mocked QDesktopServices.openUrl; launching an actual OS file manager was not exercised in the offscreen environment.

Validation: 164 pytest tests passed; compileall, packaging shell syntax, and git diff --check passed.

Reproduce screenshots from the repository root:

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python .scratch/instance-folder-ui/capture.py
```
