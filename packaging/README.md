# Ubuntu 24.04 amd64 package

This directory builds the supported desktop package for Ubuntu 24.04 LTS on
amd64. The build runs in a clean Ubuntu container (or an equivalent Debian
environment), creates an isolated Python environment, installs the pinned
application dependencies, freezes the Qt application with `pyside6-deploy`,
and wraps the result in a `.deb`.

The package contains the launcher and its Python/Qt dependencies. Minecraft
versions, assets, and managed Java runtimes are downloaded only when the user
selects **Install Minecraft**; they are deliberately not included in this
package. Updating the launcher remains a manual package installation step.

## Build

From the repository root, run:

```sh
SOURCE_DATE_EPOCH=0 packaging/build-deb.sh
```

The output is `dist/mclauncher_0.1.0_amd64.deb`. Existing files in `dist/` are
preserved; only this package and its metadata files are replaced. Set `SOURCE_DATE_EPOCH` to a
release timestamp for a reproducible release build. The script records exact
resolved Python package versions in `usr/share/doc/mclauncher/build-info.txt`
and fails if the build is not amd64.

For a clean local check:

```sh
docker run --rm --platform linux/amd64 -v "$PWD":/src -w /src ubuntu:24.04 \
  sh -eu -c 'apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates dpkg-dev file patchelf python3 python3-venv python3-dev \
    build-essential libgl1 libegl1 libglib2.0-0 libfontconfig1 libdbus-1-3 \
    libx11-6 libxkbcommon0 libxkbcommon-x11-0 libgbm1 libbrotli1 \
    libxcb-cursor0 libxcb-icccm4 libxcb-util1 libxcb-keysyms1 libxcb-image0 \
    libxcb-render-util0 libxcb-shape0 libxcb-randr0 libxcb-xinerama0 \
    libxcb-xkb1 libkrb5-3 libgssapi-krb5-2 && \
    SOURCE_DATE_EPOCH=0 packaging/build-deb.sh'
```

Install and inspect the result with `sudo apt install ./dist/mclauncher_0.1.0_amd64.deb`.
The build and package checks do not prove a clean physical desktop or a real
Minecraft launch; those require a graphical Ubuntu host and a Mojang download.
