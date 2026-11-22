#!/bin/bash
# Install Python libraries listed in requirements.txt; never block session start.
pip install -q -r "$CLAUDE_PROJECT_DIR/requirements.txt" >/dev/null 2>&1 || true
# vibration_toolbox 0.6.10 (unmaintained since 2021) uses a matplotlib style removed in 3.6; patch it.
f=$(python3 -c "import importlib.util as u;s=u.find_spec('vibration_toolbox');print(s.submodule_search_locations[0])" 2>/dev/null)/vibesystem.py
[ -f "$f" ] && sed -i "s/'seaborn-white'/'seaborn-v0_8-white'/" "$f" || true
exit 0
