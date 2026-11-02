"""FireRedHD: a new game lands directly in Kanto (Pallet Town), skipping Black 2's Aspertia -> house -> front-door
walk (user request 2026-11-02: "remove the black 2 intro stages, I don't want to go through the whole 'go through the
door to land in Kanto' for each round of testing"). This is the Kanto parallel of patches/opening.py and supersedes
the patches/kanto_door.py test bridge in b2tools/kanto_build.sh: you no longer enter Kanto through a door.

Two byte-asserted, reversible edits (a --clean rebuild restores vanilla before them):

1. New-game start zone. Black 2 picks the first map in code: EventFieldFirst_Create -> LoadAspertiaCitySpawnInfo ->
   LoadZoneSpawnInfoCheckRail(spawn, ZONE_ASPERTIA_CITY), whose zone literal sits at arm9.bin offset 0x15130 (427).
   The engine loads that zone at its header fly position and runs scripts 29/30. Pointing the literal at Pallet Town
   (450, installed by patches/kanto_world.py) makes the player appear in Kanto right after the name entry, with no
   house and no door.

2. First-map invisibility. The opening HIDES the player on that first map (ov035 EventFieldFirst_Callback state 3,
   src/ov035/event_mapchange.c:220: SetActorFlag(FieldPlayer_GetActor(...), 4)) because Black 2 never means to show
   them there - its own opening warps away, and a warp arrival builds a fresh, visible actor. We keep the player put,
   so nothing must be hidden: the 'movs r1, #4' that feeds bl SetActorFlag becomes 'movs r1, #0' (ORing no flag).
   Without this the tester would be an invisible player standing in Pallet Town.

Because a first-map spawn is a fresh spawn (not a warp) and warps fire when you stand on them, the start zone must
carry no warp under its fly point. patches/kanto_world.py writes every Kanto zone's event set EMPTY, so Pallet Town
is warp-free and the spawn is safe - which is why patches/kanto_door.py's fly-point "way home" warp (a 450<->428
reciprocal bridge) is no longer built: left in, it would sit under the spawn and loop. The file is kept for history.

The Black 2 movie (season card + Aspertia 3D flyover) and the name entry are left intact - the user chose "skip the
door only". b2tools/patches/hoenn_intro.py's byte edits show how to strip the flyover/season card too if wanted next.
"""
import os

NEW_GAME_ZONE = 0x15130          # arm9.bin offset of the literal ZONE_ASPERTIA_CITY (0x1ab = 427); see patches/opening.py
PALLET_TOWN = 450                # Pallet Town's free Unova zone slot, installed by patches/kanto_world.py
VANILLA = 427                    # Black 2's Aspertia City: the pristine new-game zone we replace

# ov035 EventFieldFirst_Callback state 3: SetActorFlag(actor, 4) -> SetActorFlag(actor, 0), keeping the player visible
OV035_BASE = 0x0217c940                    # ov035 load address = file offset 0 (the same base patches/hoenn_intro.py uses)
HIDE_FLAG_AT = 0x0217cafa - OV035_BASE     # the 'movs r1, #4' (0x2104) two bytes before 'bl SetActorFlag' (0x2166fc8)
HIDDEN, VISIBLE = '0421', '0021'           # movs r1, #4 (actor flag 4 = hidden)  /  movs r1, #0 (set nothing)


def apply_code(code):
    done = []

    # 1. new game starts in Pallet Town instead of Aspertia (the arm9 zone literal)
    path = os.path.join(code, 'arm9.bin')
    data = bytearray(open(path, 'rb').read())
    old = int.from_bytes(data[NEW_GAME_ZONE:NEW_GAME_ZONE + 4], 'little')
    assert old in (VANILLA, PALLET_TOWN), f'unexpected new-game zone literal {old}'
    data[NEW_GAME_ZONE:NEW_GAME_ZONE + 4] = PALLET_TOWN.to_bytes(4, 'little')
    if os.path.islink(path): os.unlink(path)
    open(path, 'wb').write(data)
    done.append(f'new game starts in Pallet Town {PALLET_TOWN} (was {old})')

    # 2. don't hide the player on that first map (ov035: SetActorFlag(actor, 4) -> (actor, 0))
    path = os.path.join(code, 'arm9_ov035.bin')
    data = bytearray(open(path, 'rb').read())
    o, n = bytes.fromhex(HIDDEN), bytes.fromhex(VISIBLE)
    assert data[HIDE_FLAG_AT:HIDE_FLAG_AT + 2] in (o, n), \
        f'ov035 {HIDE_FLAG_AT:#x}: unexpected {data[HIDE_FLAG_AT:HIDE_FLAG_AT + 2].hex()}'
    data[HIDE_FLAG_AT:HIDE_FLAG_AT + 2] = n
    if os.path.islink(path): os.unlink(path)
    open(path, 'wb').write(data)
    done.append('first map keeps the player visible (no SetActorFlag hide)')

    return '; '.join(done)
