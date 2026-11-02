"""FireRedHD (slice a5.2): enable Escape Rope / Dig exit remembering for the Kanto build, reusing
b2tools/patches/escape_rope.py unchanged.

escape_rope is self-contained: it rewrites 12 bytes of Black 2's own GetIsZoneMatrix0 (arm9 0x02018d04) so the
engine treats the region's own overworld matrix (and its standalone outdoor matrices) as "outdoors", which is the
only case where Black 2 stores an Escape Rope / Dig exit (event_mapchange.c: GetIsZoneMatrix0(remember) &&
!GetIsZoneMatrix0(dest)). No clang, no shared ITCM arena, no Hoenn data - a clean pilot that proves a code patch
applies on the bare Kanto base.

The only Hoenn-specific thing in escape_rope is where it reads the region's matrix/standalone counts from:
HOENN_WORLD_DIR (falling back to version.world_dir(), which on this machine is Hoenn's and does not exist). This
adapter points it at the packaged Kanto world (KANTO_WORLD_DIR, default work/kanto/world) and delegates, so no
Hoenn patch is edited in place (AGENTS.md convention: extend via kanto_* adapters). Kanto's world.json is
matrix 416, standalone [] - escape_rope makes matrix 416 the remembered-exit outdoors; its effect is fully latent
until Kanto caves/buildings with interiors exist (a later phase) but the patch itself is correct on the prototype.

Run through build_rom.py after kanto_world (it reads the packaged world.json):
    python3 build_rom.py --clean kanto_world kanto_door kanto_escape_rope
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
import escape_rope          # the generic engine patch, imported unchanged


def _kanto_world():
    return os.environ.get('KANTO_WORLD_DIR') or os.path.join(ROOT, 'work', 'kanto', 'world')


def apply_code(code):
    # escape_rope reads the region world from HOENN_WORLD_DIR first; point it at Kanto's packaged world so it sees
    # matrix 416 (not Hoenn's work/world, which does not exist on the Kanto build machine).
    os.environ['HOENN_WORLD_DIR'] = _kanto_world()
    msg = escape_rope.apply_code(code)
    return msg.replace('Hoenn', 'Kanto') if msg else msg
