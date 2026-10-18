#!/bin/sh
set -eu

BUILD_LIB=$1
ROOTFS=$2
VERSION_SOURCE=$(find "$BUILD_LIB" -type f \
  -path '*/site-packages/minecraft_launcher_lib/version.txt' -print -quit)
if [ -z "$VERSION_SOURCE" ]; then
  echo "error: pinned minecraft-launcher-lib build is missing version.txt" >&2
  exit 1
fi

VERSION_DEST="$ROOTFS/usr/lib/mclauncher/minecraft_launcher_lib/version.txt"
mkdir -p "$(dirname -- "$VERSION_DEST")"
cp "$VERSION_SOURCE" "$VERSION_DEST"
if [ ! -f "$VERSION_DEST" ]; then
  echo "error: package rootfs is missing minecraft_launcher_lib/version.txt" >&2
  exit 1
fi
