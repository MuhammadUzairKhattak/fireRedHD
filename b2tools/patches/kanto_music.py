"""FireRedHD slice a5.4: the FireRed/LeafGreen soundtrack on Black 2's instruments.

The engine and the Black 2 sound library are Hoenn's, unchanged: the M4A parser (b2tools/m4a.py), the RSE->Black 2
converter (b2tools/m4a_to_sseq.py), the instrument/role table (data/hoenn_music.json) and the in-game-measured
calibration (data/hoenn_music_levels.json) all apply to FireRed too, because Gen 3 shares one M4A engine. Only two
things differ for Kanto, and this module supplies them:
  * where the songs come from - the user's FireRed dump, read by b2tools/m4a_frlg.py (its own song table + a
    reconstructed sample->name map, since pokefirered's direct_sound_data.inc drops pokeruby's `@ address` labels);
  * the handful of GBA sample names RSE never had - the "defaults" overlay in data/kanto_music.json.

mapping() deep-merges that overlay over the Hoenn table; convert_all() runs the standard converter on FireRed songs.
This is the read/convert layer. Installing the converted songs into swan_sound_data.sdat slots (music_slots.py),
giving each Kanto zone its bgm2, and the ITCM hooks are the follow-on steps of this slice; until they land,
kanto_music is not in the Kanto build list and adds no songs to the ROM.

    python3 kanto_music.py                 convert the Kanto prototype's songs, report sizes (no ROM write)
"""
import os, sys, json, copy

HERE = os.path.dirname(os.path.abspath(__file__))
B2T = os.path.dirname(HERE)
ROOT = os.path.dirname(B2T)
sys.path.insert(0, B2T)

KANTO_JSON = os.path.join(ROOT, 'data', 'kanto_music.json')

# the songs the Kanto prototype plays today: Pallet Town (zone 450), Route 1 (zone 451) and the title screen.
# (pokefirered data/maps/<map>/map.json "music", lower-cased - the same rule hoenn_music.map_song uses for Hoenn.)
KANTO_SONGS = ['mus_pallet', 'mus_route1', 'mus_title']


def mapping():
    """The Hoenn RSE->Black 2 table with FireRed's additions merged in (never mutating data/hoenn_music.json)."""
    import m4a_to_sseq as conv
    mp = copy.deepcopy(conv.load_mapping())
    k = json.load(open(KANTO_JSON))
    mp['defaults'].update(k['defaults'])
    for song, cfg in k.get('songs', {}).items():
        mp.setdefault('songs', {}).setdefault(song, {}).update(cfg)
    if 'slots' in k:
        mp.setdefault('slots', {}).update(k['slots'])
    return mp


def convert_all(songs=None, mp=None):
    """Every named FireRed song as {song: (sseq, sbnk, swar, volume)} - the same shape hoenn_music.convert_all returns,
    but reading the GBA side from the FireRed dump. Songs: default to the Kanto prototype's."""
    import m4a_frlg as frlg
    import m4a_to_sseq as conv
    from sdat import SDAT, DEFAULT
    mp = mp or mapping()
    rom = frlg.FrlgRom()
    sd = SDAT(open(DEFAULT, 'rb').read())
    lv = conv.load_levels()
    out, sizes = {}, []
    for song in (songs if songs is not None else KANTO_SONGS):
        sg = conv.Song(song, rom=rom, mapping=mp, sdat=sd, levels=lv)
        q, b, w = sg.convert()
        out[song] = (q, b, w, sg.info_volume)
        sizes.append(sg.size)
    return out, sum(sizes)


def main(_argv):
    mp = mapping()
    songs, total = convert_all(mp=mp)
    for song, (q, b, w, vol) in songs.items():
        print(f'  {song}: sseq {len(q):,} B, sbnk {len(b):,} B, swar {len(w):,} B, volume {vol}')
    print(f'kanto_music: {len(songs)} FireRed song(s) converted, {total:,} B of sequence+bank+wave (no ROM write)')
    return 0


if __name__ == '__main__':
    main(sys.argv[1:])
