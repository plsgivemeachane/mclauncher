#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
OUT="$ROOT/dist"
BUILD="$ROOT/.packaging-build"
PYTHON_BIN=${PYTHON_BIN:-python3}
PY_SIDE_VERSION=${PY_SIDE_VERSION:-6.12.0}
MLL_VERSION=${MLL_VERSION:-8.0}
APP_VERSION=$(PYTHONPATH="$ROOT/src" python3 -c 'from importlib.metadata import version; print(version("mclauncher"))' 2>/dev/null || printf '%s\n' 0.1.0)
PACKAGE=mclauncher

cleanup_deploy_outputs() {
  rm -rf "$ROOT/packaging/deployment" "$ROOT/packaging/mclauncher.dist" \
    "$ROOT/packaging/entrypoint.dist" "$ROOT/packaging/pysidedeploy.spec"
}
trap cleanup_deploy_outputs EXIT

case "$(uname -m)" in
  x86_64|amd64) ARCH=amd64 ;;
  *) echo "error: this package is only buildable for amd64" >&2; exit 1 ;;
esac

command -v dpkg-deb >/dev/null
command -v dpkg-shlibdeps >/dev/null
command -v "$PYTHON_BIN" >/dev/null
PYTHON_VERSION=$($PYTHON_BIN -c 'import platform; print(platform.python_version())')

rm -rf "$BUILD"
mkdir -p "$BUILD" "$OUT"
"$PYTHON_BIN" -m venv "$BUILD/venv"
# shellcheck disable=SC1091
. "$BUILD/venv/bin/activate"
python -m pip install --upgrade --disable-pip-version-check 'pip==25.2' 'setuptools==80.9.0' wheel
python -m pip install --disable-pip-version-check \
  "PySide6==$PY_SIDE_VERSION" "minecraft-launcher-lib==$MLL_VERSION"
python -m pip install --no-deps .

rm -rf "$BUILD/frozen" "$BUILD/pysidedeploy.spec" "$BUILD/entrypoint.dist" \
  "$BUILD/entrypoint.bin" "$BUILD/mclauncher.dist" "$BUILD/mclauncher.bin" \
  "$ROOT/packaging/deployment" "$ROOT/packaging/mclauncher.dist" \
  "$ROOT/packaging/entrypoint.dist"
mkdir -p "$BUILD/frozen"
# pyside6-deploy writes its standalone tree beside the spec. Keep the spec in
# the build directory so the entry point and deployment settings are recorded.
(cd "$ROOT/packaging" && pyside6-deploy --force --mode standalone \
  --name mclauncher entrypoint.py)
if [ -d "$BUILD/mclauncher.dist" ]; then
  cp -a "$BUILD/mclauncher.dist/." "$BUILD/frozen/"
  [ -x "$BUILD/mclauncher.bin" ] && cp "$BUILD/mclauncher.bin" "$BUILD/frozen/mclauncher"
elif [ -d "$BUILD/entrypoint.dist" ]; then
  cp -a "$BUILD/entrypoint.dist/." "$BUILD/frozen/"
  [ -x "$BUILD/entrypoint.bin" ] && cp "$BUILD/entrypoint.bin" "$BUILD/frozen/mclauncher"
fi
if [ -d "$ROOT/packaging/deployment/entrypoint.dist" ]; then
  cp -a "$ROOT/packaging/deployment/entrypoint.dist/." "$BUILD/frozen/"
  [ -x "$ROOT/packaging/deployment/entrypoint.bin" ] && cp "$ROOT/packaging/deployment/entrypoint.bin" "$BUILD/frozen/mclauncher"
fi
if [ -d "$ROOT/packaging/mclauncher.dist" ]; then
  cp -a "$ROOT/packaging/mclauncher.dist/." "$BUILD/frozen/"
  [ -x "$ROOT/packaging/mclauncher.dist/entrypoint.bin" ] && cp "$ROOT/packaging/mclauncher.dist/entrypoint.bin" "$BUILD/frozen/mclauncher"
fi

BIN=$(find "$BUILD/frozen" -maxdepth 2 -type f -perm -111 \
  \( -name 'mclauncher' -o -name 'mclauncher.bin' \) -print -quit)
if [ -z "$BIN" ]; then
  echo "error: pyside6-deploy did not produce a mclauncher executable" >&2
  find "$BUILD/frozen" -maxdepth 2 -type f -print >&2
  exit 1
fi

ROOTFS="$BUILD/rootfs"
mkdir -p "$ROOTFS/usr/lib/mclauncher" "$ROOTFS/usr/bin" \
  "$ROOTFS/usr/share/applications" "$ROOTFS/usr/share/doc/$PACKAGE" \
  "$ROOTFS/DEBIAN"
cp -a "$(dirname -- "$BIN")/." "$ROOTFS/usr/lib/mclauncher/"
# The supported Ubuntu desktop path uses the XCB platform plugin. EGLFS and
# Wayland integration plugins introduce optional host libraries and are not
# needed for this package's tested X11 desktop target.
rm -rf "$ROOTFS/usr/lib/mclauncher/PySide6/qt-plugins/egldeviceintegrations" \
  "$ROOTFS/usr/lib/mclauncher/PySide6/qt-plugins/wayland-graphics-integration-client" \
  "$ROOTFS/usr/lib/mclauncher/PySide6/qt-plugins/wayland-decoration-client" \
  "$ROOTFS/usr/lib/mclauncher/PySide6/qt-plugins/wayland-shell-integration" \
  "$ROOTFS/usr/lib/mclauncher/PySide6/qt-plugins/platforms/libqwayland-egl.so" \
  "$ROOTFS/usr/lib/mclauncher/PySide6/qt-plugins/platforms/libqwayland-generic.so" \
  "$ROOTFS/usr/lib/mclauncher/PySide6/qt-plugins/platforms/libqeglfs.so"
find "$ROOTFS/usr/lib/mclauncher/PySide6/qt-plugins/platforms" \
  -type f -name 'libqwayland*.so' -delete
find "$ROOTFS/usr/lib/mclauncher/PySide6/qt-plugins" -type d -name 'wayland*' \
  -prune -exec rm -rf {} +
rm -f "$ROOTFS/usr/lib/mclauncher/libQt6WaylandClient.so.6"
rm -f "$ROOTFS/usr/lib/mclauncher/libQt6WlShellIntegration.so.6"
rm -rf "$ROOTFS/usr/lib/mclauncher/PySide6/qt-plugins/printsupport"
find "$ROOTFS/usr/lib/mclauncher/PySide6/qt-plugins/platforms" -type f \
  \( -name 'libqlinuxfb.so' -o -name 'libqminimal.so' -o -name 'libqoffscreen.so' \
     -o -name 'libqvkkhrdisplay.so' -o -name 'libqminimalegl.so' \) -delete
rm -f "$ROOTFS/usr/lib/mclauncher/PySide6/qt-plugins/platformthemes/libqgtk3.so"
cat > "$ROOTFS/usr/bin/mclauncher" <<'EOF'
#!/bin/sh
exec /usr/lib/mclauncher/mclauncher "$@"
EOF
chmod 0755 "$ROOTFS/usr/bin/mclauncher"

sed "s|^Exec=.*|Exec=/usr/bin/mclauncher|; s|^TryExec=.*|TryExec=/usr/bin/mclauncher|" \
  "$ROOT/resources/mclauncher.desktop" > "$ROOTFS/usr/share/applications/mclauncher.desktop"
grep -q '^TryExec=/usr/bin/mclauncher$' "$ROOTFS/usr/share/applications/mclauncher.desktop" || \
  printf '%s\n' 'TryExec=/usr/bin/mclauncher' >> "$ROOTFS/usr/share/applications/mclauncher.desktop"

python -m pip freeze | sort > "$ROOTFS/usr/share/doc/$PACKAGE/python-packages.txt"
{
  printf 'Package: %s\nVersion: %s\nArchitecture: %s\n\n' "$PACKAGE" "$APP_VERSION" "$ARCH"
  printf 'Build Python: %s\n' "$PYTHON_VERSION"
  printf 'Pinned PySide6: %s\n' "$PY_SIDE_VERSION"
  printf 'Pinned minecraft-launcher-lib: %s\n' "$MLL_VERSION"
  printf 'Source date epoch: %s\n' "${SOURCE_DATE_EPOCH:-unset}"
} > "$ROOTFS/usr/share/doc/$PACKAGE/build-info.txt"
{
  printf 'Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/\n'
  printf 'Upstream-Name: mclauncher\nSource: local project\n\n'
  printf 'Files: mclauncher source\nCopyright: 2026 mclauncher contributors\nLicense: Unknown (no project license file is distributed)\n\n'
  printf 'Files: bundled Python and Qt dependencies\nLicense: See python-packages.txt and the corresponding upstream license files.\n'
} > "$ROOTFS/usr/share/doc/$PACKAGE/copyright"
find "$BUILD/venv/lib" -type f \( -iname 'LICENSE*' -o -iname 'COPYING*' \) -print | sort | while IFS= read -r license; do
  base=$(basename "$(dirname "$license")")-$(basename "$license")
  cp "$license" "$ROOTFS/usr/share/doc/$PACKAGE/$base" || true
  {
    printf '\n--- %s ---\n' "$base"
    cat "$license"
  } >> "$ROOTFS/usr/share/doc/$PACKAGE/copyright"
done

# dpkg-shlibdeps determines host runtime libraries from every ELF file in the
# actual frozen tree. It is intentionally used instead of a guessed Depends.
mkdir -p "$BUILD/debian"
find "$ROOTFS/usr/lib/mclauncher" -type f -exec file {} + | \
  awk -F: '/ELF .*executable|ELF .*shared object/ {print $1}' > "$BUILD/debian/elf-files"
[ -s "$BUILD/debian/elf-files" ] || { echo 'error: frozen tree contains no ELF files' >&2; exit 1; }
cat > "$BUILD/debian/control" <<EOF
Source: $PACKAGE
Section: games
Priority: optional
Maintainer: mclauncher contributors
Standards-Version: 4.7.0

Package: $PACKAGE
Architecture: $ARCH
Description: Minecraft offline-session launcher
 A graphical Qt launcher.
EOF
SHLIBS=$(cd "$BUILD" && xargs dpkg-shlibdeps -O < debian/elf-files | sed -n 's/^shlibs:Depends=//p' | tr '\n' ',' | sed 's/,$//' )
[ -n "$SHLIBS" ] || { echo 'error: dpkg-shlibdeps returned no runtime dependencies' >&2; exit 1; }
cat > "$ROOTFS/DEBIAN/control" <<EOF
Package: $PACKAGE
Version: $APP_VERSION
Section: games
Priority: optional
Architecture: $ARCH
Maintainer: mclauncher contributors
Depends: $SHLIBS
Description: Minecraft offline-session launcher
 A graphical Qt launcher for installing and playing managed Minecraft instances.
 Minecraft and Java files are downloaded on request by the user.
EOF
cat > "$ROOTFS/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database >/dev/null 2>&1 || true
fi
exit 0
EOF
chmod 0755 "$ROOTFS/DEBIAN/postinst"

find "$ROOTFS" -type f -exec touch -h -d "@${SOURCE_DATE_EPOCH:-0}" {} +
dpkg-deb --build --root-owner-group "$ROOTFS" "$OUT/${PACKAGE}_${APP_VERSION}_${ARCH}.deb" >/dev/null
dpkg-deb --info "$OUT/${PACKAGE}_${APP_VERSION}_${ARCH}.deb" > "$OUT/package-info.txt"
dpkg-deb --contents "$OUT/${PACKAGE}_${APP_VERSION}_${ARCH}.deb" > "$OUT/package-contents.txt"
file "$OUT/${PACKAGE}_${APP_VERSION}_${ARCH}.deb" | grep -q 'Debian binary package'
grep -q 'usr/share/applications/mclauncher.desktop' "$OUT/package-contents.txt"
grep -q 'usr/share/doc/mclauncher/copyright' "$OUT/package-contents.txt"
echo "Built $OUT/${PACKAGE}_${APP_VERSION}_${ARCH}.deb"
