# Packaged acceptance evidence

Captured 2026-10-18 from `mclauncher 0.1.0 amd64` (SHA-256 `304b83ef03b02316b74aa6840d84609b5f5ee3ffb599c695e2c387dd0a253dfb`) in a clean Ubuntu 24.04 amd64 container without system Python or Java.

- `ubuntu-24.04-installed.png` shows the packaged launcher after Minecraft 26.3 and managed Java reached ready state.
- `ubuntu-24.04-offline-renderer-limit.png` shows the offline Play attempt and the renderer error. The managed Java process started with `AcceptanceUser`, version 26.3, and the selected instance directory, then exited because Minecraft could not find a matching GLX visual or a Vulkan surface.
- `ubuntu-24.04-minecraft.log` contains the game startup log. Minecraft also logged an unavailable profile-service lookup while the network was disconnected; this did not prevent the JVM from starting.
- `ubuntu-24.04-llvmpipe-glx.txt` records that Xvfb exposed Mesa llvmpipe and OpenGL 4.5. Minecraft 26.3 still could not create its renderer in this virtual display, so no menu or world was reached.

The build used Python 3.12.3, PySide6 6.12.0, minecraft-launcher-lib 8.0, and Nuitka 4.1.1. The exact package was rebuilt reproducibly and its hash matches the installed artifact. See the launcher spec and Issues 01–10 for automated results and remaining acceptance gaps.
