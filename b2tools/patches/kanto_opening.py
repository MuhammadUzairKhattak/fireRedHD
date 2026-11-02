"""FireRedHD: a new game skips Black 2's opening movie and lands directly in Kanto, visible (user request
2026-11-02: first "remove the black 2 intro stages / the door walk", then after the first build "I get a black screen
after the mom/character shows by her home - I'd rather the whole intro be gone"). This is the Kanto parallel of
patches/opening.py (the arm9 start-zone literal) plus patches/hoenn_intro.py (the ov035 movie no-ops), with none of
Hoenn's content, and it supersedes the patches/kanto_door.py test bridge in b2tools/kanto_build.sh.

Every edit is byte-asserted and reversible (a --clean rebuild restores vanilla first, then re-applies).

1. New-game start zone (arm9.bin 0x15130, the ZONE_ASPERTIA_CITY=427 literal that LoadAspertiaCitySpawnInfo ->
   LoadZoneSpawnInfoCheckRail reads): 427 -> 450 (Pallet Town, installed by patches/kanto_world.py). EventFieldFirst
   loads that zone at its header fly position, so the player appears in Kanto right after the name entry.

2. No season card and no Aspertia flyover (ov035 EventGameOpening_Callback, src/ov035/event_mapchange.c:172-191).
   Black 2 chains a standalone season banner (state 1) and the Aspertia 3D flyover Event3DDemo_Create(gsys,event,5)
   (state 2) through one shared GameEvent_ChainNext; state 3 replaces the event with EventFieldFirst. The three
   creates / the shared ChainNext become no-ops (c046 = Thumb MOV r6,r6 hint), exactly as patches/hoenn_intro.py does
   for Hoenn. Season_Set still runs (the season is set), and case 3 uses GameEvent_Replace, not the NOP'd ChainNext,
   so the chain to EventFieldFirst is intact. This also removes the black screen the user saw: that "mom/character by
   her home" was the Aspertia flyover still rendering, which then collided with loading Pallet as the first map.

3. Player stays visible on that first map (ov035 EventFieldFirst_Callback state 3, event_mapchange.c:246): the
   opening hides the player with SetActorFlag(FieldPlayer_GetActor(...), 4) because Black 2 never means to show them
   before its scripted warp (a warp arrival builds a fresh, visible actor). We keep the player put, so nothing is
   hidden: the 'movs r1, #4' feeding bl SetActorFlag becomes 'movs r1, #0' (ORing no flag).

4. No rival naming (ov162 NewGame_Main, game_start.c): after the player's name is confirmed Black 2 asks for a rival
   name (state NEW_GAME_RIVAL_NAME_ENTRY = 7); it now ends the intro (NEW_GAME_END = 12) like patches/hoenn_intro.py,
   so the movie hands off to the field without that prompt. The short player-name entry is kept.

Because the start is a fresh spawn (not a warp) into a warp-free Kanto zone, patches/kanto_door.py's fly-point "way
home" warp (a 450<->428 reciprocal bridge) is no longer built: left in, it would sit under the spawn and loop.
"""
import os

# 1. arm9.bin new-game zone literal (the same offset patches/opening.py proved)
NEW_GAME_ZONE = 0x15130          # arm9.bin offset of the literal ZONE_ASPERTIA_CITY (0x1ab = 427); see patches/opening.py
PALLET_TOWN = 450                # Pallet Town's free Unova zone slot, installed by patches/kanto_world.py
VANILLA = 427                    # Black 2's Aspertia City: the pristine new-game zone we replace

NOP = 'c046c046'                 # two Thumb 'mov r6, r6' hints: a 4-byte no-op that overwrites a wide bl

# ov035: (load address base = file offset 0, the same base patches/hoenn_intro.py uses)
OV035_BASE = 0x0217c940
# 2. season card + Aspertia flyover gone (EventGameOpening_Callback states 1 and 2)
SEASON_BANNER_BL = (0x0217c9c8 - OV035_BASE, '02f0e2fa')   # bl EventSeasonBanner_CreateStandalone
OPENING_CHAIN_BL = (0x0217c9d0 - OV035_BASE, '9af6caf9')   # bl GameEvent_ChainNext (shared by the season card + flyover)
FLYOVER_BL = (0x0217c9e8 - OV035_BASE, 'e0f7aef8')         # bl Event3DDemo_Create(gsys, event, 5, ...) Aspertia flyover
# 3. first-map player visibility (EventFieldFirst_Callback state 3): SetActorFlag(actor, 4) -> (actor, 0)
HIDE_FLAG_AT = 0x0217cafa - OV035_BASE                      # the 'movs r1, #4' two bytes before 'bl SetActorFlag'
HIDDEN, VISIBLE = '0421', '0021'                           # movs r1,#4 (flag 4 = hidden) / movs r1,#0 (set nothing)

# 4. ov162: no rival-name prompt (base 0x0219ce80, as patches/hoenn_intro.py)
OV162_BASE = 0x0219ce80
RIVAL_NAME_AT = 0x021a022a - OV162_BASE                    # 'movs r0, #7' = NEW_GAME_RIVAL_NAME_ENTRY
RIVAL_ENTRY, INTRO_END = '0720', '0c20'                   # -> 'movs r0, #12' = NEW_GAME_END

OV035_EDITS = [(SEASON_BANNER_BL[0], SEASON_BANNER_BL[1], NOP),
               (OPENING_CHAIN_BL[0], OPENING_CHAIN_BL[1], NOP),
               (FLYOVER_BL[0], FLYOVER_BL[1], NOP),
               (HIDE_FLAG_AT, HIDDEN, VISIBLE)]


def _apply(path, edits):
    """Byte-assert each edit (old or already-patched new), then write once; the file's symlink is replaced by a copy."""
    data = bytearray(open(path, 'rb').read())
    for at, old, new in edits:
        o, n = bytes.fromhex(old), bytes.fromhex(new)
        assert data[at:at + len(o)] in (o, n), f'{os.path.basename(path)} {at:#x}: unexpected {data[at:at + len(o)].hex()}'
        data[at:at + len(o)] = n
    if os.path.islink(path): os.unlink(path)
    open(path, 'wb').write(data)


def apply_code(code):
    # 1. arm9: new game starts in Pallet Town instead of Aspertia
    data = bytearray(open(os.path.join(code, 'arm9.bin'), 'rb').read())
    old = int.from_bytes(data[NEW_GAME_ZONE:NEW_GAME_ZONE + 4], 'little')
    assert old in (VANILLA, PALLET_TOWN), f'unexpected new-game zone literal {old}'
    data[NEW_GAME_ZONE:NEW_GAME_ZONE + 4] = PALLET_TOWN.to_bytes(4, 'little')
    path = os.path.join(code, 'arm9.bin')
    if os.path.islink(path): os.unlink(path)
    open(path, 'wb').write(data)

    # 2 + 3. ov035: no season card / no Aspertia flyover, and keep the first-map player visible
    _apply(os.path.join(code, 'arm9_ov035.bin'), OV035_EDITS)

    # 4. ov162: skip the rival-name prompt
    _apply(os.path.join(code, 'arm9_ov162.bin'), [(RIVAL_NAME_AT, RIVAL_ENTRY, INTRO_END)])

    return ('new game starts in Pallet Town %d (was %d); no season card / no Aspertia flyover; '
            'first map keeps the player visible; no rival naming' % (PALLET_TOWN, old))
