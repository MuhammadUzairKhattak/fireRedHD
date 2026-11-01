"""TEST / reachability bridge (slice a4.6): make the FireRedHD Kanto prototype world actually enterable in a Black 2
build that carries only patches/kanto_world.py (Pallet Town = zone 450). Following patches/test_door_to_nuvema.py
(Aspertia's front-door mat, zone 428 warp 0, is the slot the emulator harness reaches the slice from off the opening
savestate), that same reachable door now leads into Pallet Town, and one arrival warp is added at Pallet Town's fly
point leading back to Aspertia so you can step in and step out. It rewires only those two door destinations - it adds
no Kanto terrain (that is patches/kanto_world.py) and ships none of Kanto's real doors/story (later slices).

Build it after the world patch:
    python3 build_rom.py --clean kanto_world kanto_door        (KANTO_WORLD_DIR = the packaged world)
"""
import os, json, struct
import narcio, zoneheaders
from zones import parse_entities, build_entities

ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
W = os.environ.get('KANTO_WORLD_DIR') or os.path.join(ROOT, 'work', 'kanto', 'world')
ENTRY_ZONE = 428        # Aspertia City: the player's-house front-door mat, reachable from Black 2's own opening
ENTRY_WARP = 0          # its warp 0 (the slot test_door_to_nuvema repurposes)
KANTO_ZONE = 450        # Pallet Town (patches/kanto_world.py installs it on the Kanto matrix)


def apply(files):
    fly = json.load(open(os.path.join(W, 'world.json')))['zones'][str(KANTO_ZONE)]['fly']
    headers, _ = zoneheaders.load(files)
    ents = narcio.load(files, 126)

    # 1. Pallet Town gets one arrival warp at its fly point, leading back out to Aspertia's door slot (a way home)
    hd = headers[KANTO_ZONE]
    e, _ = parse_entities(ents[hd['entities']])
    e['warps'] = [dict(dest_zone=ENTRY_ZONE, dest_warp=ENTRY_WARP, dir=2, type=3, rail=0,
                       x=fly[0] * 16 + 8, y=0, z=fly[1] * 16 + 8, w=1, h=1, unk=0)]
    ents[hd['entities']] = build_entities(e, ents[hd['entities']])

    # 2. Aspertia's front-door mat now leads into Pallet Town's warp 0 (the arrival added above)
    hd2 = headers[ENTRY_ZONE]
    data = bytearray(ents[hd2['entities']])
    parsed, warps_at = parse_entities(bytes(data))
    assert parsed['warps'], f'entry zone {ENTRY_ZONE} has no warp {ENTRY_WARP} to repurpose'
    old = struct.unpack_from('<HH', data, warps_at)
    struct.pack_into('<HH', data, warps_at, KANTO_ZONE, 0)
    ents[hd2['entities']] = bytes(data)

    narcio.save(files, 126, ents)
    return (f'Pallet Town {KANTO_ZONE} warp 0 -> ({ENTRY_ZONE},{ENTRY_WARP}) at fly {fly} '
            f'[x {fly[0] * 16 + 8}, z {fly[1] * 16 + 8}]; '
            f'Aspertia {ENTRY_ZONE} warp {ENTRY_WARP} {old} -> ({KANTO_ZONE},0)')
