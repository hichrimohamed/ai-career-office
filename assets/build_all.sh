#!/bin/zsh
# Rebuild the office and the four workers from their Blender scripts into frontend/public/models.
# Usage: assets/build_all.sh            (BLENDER=/path/to/Blender to override)
set -euo pipefail
cd "$(dirname "$0")/.."
BLENDER=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
OUT=frontend/public/models

"$BLENDER" --factory-startup -b -P assets/office/build_office.py -- --out $OUT/office.glb | grep "\[office\]"
for name in nora leo maya kai; do
  "$BLENDER" --factory-startup -b -P assets/characters/$name.py -- --out $OUT/$name.glb | grep "\[characters\]"
done
