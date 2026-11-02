"""FireRedHD (slice a4.5): install the Kanto overworld built by b2tools/kanto_world.py (work/kanto/world/) into the
Black 2 (pokebw2 b2_us) base that FireRedHD's NDS build starts from - the Kanto parallel of patches/hoenn_world.py,
kept focused so it carries no Hoenn coupling (no Sapphire version doors, fixed weather, encounter tables, seasons,
alt layouts or the sub-cell ZoneLookup code patch). Kanto appends on Unova's OWN counts (the same region base Hoenn
used): its 12 cell chunks go to a/0/0/8 from first_chunk (1065), one format-1 matrix to a/0/0/9 at world['matrix']
(416), and the two zone headers Pallet Town / Route 1 take (450 / 451, free Unova slots) are pointed at that matrix
and area with a fly point. Black 2's own matrices, chunks and every other zone are left exactly as they are.

The chunks reuse hoenn_world._chunk UNCHANGED (the generic 'WB'/'GC' container: terrain.nsbmd through Black 2's
tree/water material fix, collision layers, placements.bin). Each Kanto zone's event set is written EMPTY (no signs /
NPCs / triggers) except for the warp doors world.json carries under a zone's 'doors' key (see kanto_world.kanto_doors):
a few discrete maps - a dungeon like Viridian Forest and its Route 2 entrance rooms - are entered through a warp, not a
seamless edge, so their zones get real Black 2 warp records while every other (door-less) prototype zone stays blank. The zone header's field/init script numbers and the entity
file's map-script table are copied from Black 2's own Nuvema (town, 389) / Route 1 (route, 317) headers - pristine,
self-contained Gen 5 scripts that load without touching anything we removed.

Run through build_rom.py with KANTO_WORLD_DIR set to the packaged world (default work/kanto/world):
    python3 build_rom.py --clean kanto_world        (patches read the .nds file tree, never the clone source)
"""
import os, json, struct
import sys as _sys
import narcio, zoneheaders
_sys.path.insert(0, os.path.dirname(__file__))
from hoenn_world import _chunk          # generic chunk packer (terrain.nsbmd + collision + placements), no Hoenn state
_sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from zones import build_entities        # serialise an (empty) event set back into an a/1/2/6 entry, keeping its tail

ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
W = os.environ.get('KANTO_WORLD_DIR') or os.path.join(ROOT, 'work', 'kanto', 'world')
NO_NPC_CACHE = 24                 # zone header npc_cache >= 24 = no preloaded people list (as 562 of Black 2's 615 zones)
NO_ENCOUNTERS = 0x1FFF            # Black 2's "no wild table" enc value (enc_slot 0); Kanto encounters come later
TEMPLATE = {'town': 389, 'route': 317}    # Black 2's Nuvema Town / Route 1: pristine outdoor headers to copy shape from

# header fields taken verbatim from the kind template: outdoor map_type/flags/camera/weather, its BGM, its (valid,
# self-contained) field/init script numbers, and a place name (the manifest's string 'place' is descriptive only -
# real Kanto place-name text into a/0/0/2 is a later content slice).
COPY_FIELDS = ('map_type', 'flags', 'cam_bound', 'icon_word', 'weather_word',
               'bgm0', 'bgm1', 'bgm2', 'bgm3', 'scripts', 'init_scripts', 'place', 'place_display')


def apply(files):
    world = json.load(open(os.path.join(W, 'world.json')))
    cells = sorted(world['cells'], key=lambda c: c['chunk'])

    # 1. chunks -> a/0/0/8, appended on Unova's own count (hoenn_world.apply asserts the same invariant)
    chunks = narcio.load(files, 8)
    assert len(chunks) == cells[0]['chunk'], f'a/0/0/8 has {len(chunks)} entries, expected {cells[0]["chunk"]}'
    for c in cells:
        d = os.path.join(W, 'cells', f'{c["cx"]:02d}_{c["cz"]:02d}')
        chunks.append(_chunk(d))
    narcio.save(files, 8, chunks)

    # 2. the Kanto matrix -> a/0/0/9: format 1 (a zone per cell), Black 2's own matrices keep their ids below it
    w, h = world['width'], world['height']
    ids = [0xFFFFFFFF] * (w * h)
    zs = [0] * (w * h)
    for c in cells:
        ids[c['cz'] * w + c['cx']] = c['chunk']
        zs[c['cz'] * w + c['cx']] = c['zone']
    mats = narcio.load(files, 9)
    assert len(mats) == world['matrix'], f'a/0/0/9 has {len(mats)} entries, expected {world["matrix"]}'
    mats.append(struct.pack('<HHHH', 1, 0, w, h) + struct.pack(f'<{w * h}I', *ids) + struct.pack(f'<{w * h}I', *zs))
    narcio.save(files, 9, mats)

    # 3. the zones' headers + empty event sets
    headers, hentries = zoneheaders.load(files)
    ents = narcio.load(files, 126)
    done = []
    for zid, z in world['zones'].items():
        zid = int(zid)
        hd = dict(headers[zid])
        t = headers[TEMPLATE[z.get('kind', 'route')]]
        for k in COPY_FIELDS:
            hd[k] = t[k]
        hd['npc_cache'] = NO_NPC_CACHE
        hd['encounters'], hd['enc_slot'] = NO_ENCOUNTERS, 0
        hd['parent'] = zid
        hd['matrix'], hd['area'] = world['matrix'], world['area']
        hd['fly_x'], hd['fly_y'], hd['fly_z'] = z['fly'][0], 0, z['fly'][1]
        # an empty event set (the repurposed slot's own Unova actors/warps stay out of the Kanto geometry); the zone's
        # init-script table is kept from the entity file, which the header's (template) init_scripts number drives.
        # The one exception is world.json's 'doors': Black 2 warp records for a Kanto map you enter through a warp
        # (a dungeon / entrance room), resolved by kanto_world.kanto_doors. A zone with no doors keeps its event set
        # blank exactly as before, so the door-less prototype maps and the boot path are byte-for-byte unchanged.
        ents[hd['entities']] = build_entities(dict(signs=[], npcs=[], warps=z.get('doors', []), triggers=[]), ents[hd['entities']])
        headers[zid] = hd
        done.append(f'zone {zid} ({z.get("kind")} "{z.get("place")}" -> maps {z.get("maps")}): '
                    f'matrix {hd["matrix"]}, area {hd["area"]}, fly [{z["fly"][0]}, {z["fly"][1]}]')
    zoneheaders.save(files, headers, hentries)
    narcio.save(files, 126, ents)
    return (f"{len(cells)} chunks from {cells[0]['chunk']}, matrix {world['matrix']} ({w}x{h}, "
            f"area {world['area']}), zones {'; '.join(done)}")
