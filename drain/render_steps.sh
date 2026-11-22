#!/bin/bash
# Usage: BLENDER=/path/to/blender PH_DIR=/path/to/polyhaven ./render_steps.sh [samples]
cd "$(dirname "$0")"; mkdir -p steps
for i in 1 2 3 4 5 6 7 8; do
  STAGE=$i "$BLENDER" -b --factory-startup -P blender_drain.py -- "$PWD/steps/raw_step$i.png" "${1:-96}" 2>&1 | grep -E "Saved:|Error|Traceback"
done
rm -f steps/*.blend steps/*.blend1
