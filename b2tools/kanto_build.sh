#!/usr/bin/env bash
# FireRedHD (slice a4.5): build the Kanto prototype overworld (Pallet Town + Route 1) into its OWN ROM, parallel to
# b2tools/agent_build.sh but for Kanto content and WITHOUT any Hoenn patch on the command line. Everything the Kanto
# path needs, end to end, reading only the shared Black 2 (pokebw2 b2_us) base:
#   package (world.write_cell over work/kanto compose) -> terrain.dae per cell
#   ToNsbmd batch                                       -> terrain.nsbmd per cell
#   build_rom --clean kanto_world                       -> work/kanto/rom/kanto.nds
# The ROM build dir is HOENN_BUILD_DIR (work/kanto/rom) so a Hoenn build in work/rom is never touched; the clone of
# external/pokebw2's files/code is made fresh each --clean run and pruned to just the ROM at the end.
#   b2tools/kanto_build.sh                (all steps)
#   b2tools/kanto_build.sh --skip-package (reuse work/kanto/world; only nsbmd + ROM)
set -e -o pipefail
cd "$(dirname "$0")/.."
PY="python3 -W ignore::ResourceWarning"
CP="work/java:tools/CTRMap.jar:tools/ctrmap-plugins/CTRMapV-1.4.1.jar"
export KANTO_WORLD_DIR="$PWD/work/kanto/world"
export HOENN_BUILD_DIR="$PWD/work/kanto/rom"
export HOENN_BERRY_PLANTING=0    # keep the Kanto ROM a pure world injection (build_rom appends 'berries' by default)
mkdir -p work/java && javac -cp "$CP" -d work/java b2tools/java/*.java
if [[ "$1" != "--skip-package" ]]; then
  (cd b2tools && $PY kanto_world.py --world)
fi
(cd b2tools && $PY kanto_world.py --nsbmd)
(cd b2tools && $PY build_rom.py --clean kanto_world kanto_door kanto_escape_rope exp_share) | grep -E "nds|patch kanto_|patch exp_share" | cut -c1-200
rm -rf "$HOENN_BUILD_DIR/files" "$HOENN_BUILD_DIR/code"    # keep only the ROM (disk space; next --clean recreates them)
