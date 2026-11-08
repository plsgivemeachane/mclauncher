#!/bin/sh
# Rebuild the offline session agent jar shipped in src/mclauncher/assets.
# Targets Java 8 so every Mojang-managed runtime can load it.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OUT="$HERE/../src/mclauncher/assets/offline-session-agent.jar"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/classes"
javac -source 8 -target 8 -nowarn -d "$WORK/classes" \
  "$HERE/src/mclauncher/agent/OfflineSessionAgent.java"
cat > "$WORK/manifest.txt" <<'EOF'
Premain-Class: mclauncher.agent.OfflineSessionAgent
Agent-Class: mclauncher.agent.OfflineSessionAgent
EOF
jar cfm "$OUT" "$WORK/manifest.txt" -C "$WORK/classes" .
echo "built $OUT"
