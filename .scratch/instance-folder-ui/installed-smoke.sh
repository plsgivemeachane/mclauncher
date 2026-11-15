#!/bin/sh
set -eu
export XDG_DATA_HOME=/tmp/mclauncher-014-installed-smoke
mkdir -p "$XDG_DATA_HOME/mclauncher"
python3 - <<'PY'
import json
import os
from pathlib import Path
root = Path(os.environ['XDG_DATA_HOME']) / 'mclauncher'
instance_id = 'survival-1214-a1b2c3d4'
state = {'username': 'Alex', 'instances': [{'id': instance_id, 'name': 'Survival', 'version': '1.21.4', 'ready': True}], 'selected_instance_id': instance_id, 'selected_setup_id': instance_id, 'available_versions': ['1.21.4'], 'memory_gib': 2}
(root / 'state.json').write_text(json.dumps(state))
(root / 'instances' / instance_id / 'minecraft' / 'screenshots').mkdir(parents=True, exist_ok=True)
PY
/usr/bin/mclauncher > /tmp/mclauncher-014-installed.log 2>&1 &
launcher_pid=$!
trap 'kill "$launcher_pid" 2>/dev/null || true' EXIT
window_id=$(timeout 30 xdotool search --sync --onlyvisible --name '^Minecraft Launcher$' | head -1)
[ -n "$window_id" ]
sleep 2
/work/.packaging-build/venv/bin/python /src/.scratch/instance-folder-ui/capture-installed.py "$window_id" /src/.scratch/instance-folder-ui/installed-home-014.png
xdotool mousemove --window "$window_id" 134 72 click 1
sleep 1
/work/.packaging-build/venv/bin/python /src/.scratch/instance-folder-ui/capture-installed.py "$window_id" /src/.scratch/instance-folder-ui/installed-instances-014.png
xdotool windowsize "$window_id" 680 420
sleep 1
/work/.packaging-build/venv/bin/python /src/.scratch/instance-folder-ui/capture-installed.py "$window_id" /src/.scratch/instance-folder-ui/installed-instances-small-014.png
kill -0 "$launcher_pid"
echo 'Installed launcher stayed running through Home, Instances, and resize smoke'
