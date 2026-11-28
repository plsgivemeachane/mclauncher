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
# Mojang's Services public keys, served when the live fetch fails. Refresh with:
#   curl -sf https://api.minecraftservices.com/publickeys -o agent/src/mclauncher/agent/publickeys.json
cp "$HERE/src/mclauncher/agent/publickeys.json" "$WORK/classes/mclauncher/agent/"
cat > "$WORK/manifest.txt" <<'EOF'
Premain-Class: mclauncher.agent.OfflineSessionAgent
Agent-Class: mclauncher.agent.OfflineSessionAgent
EOF
jar cfm "$OUT" "$WORK/manifest.txt" -C "$WORK/classes" .
echo "built $OUT"
