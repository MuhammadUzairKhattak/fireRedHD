"""FireRedHD slice a5.4 (foundation): read FireRed's M4A music straight from the user's own FireRed dump.

b2tools/m4a.py parses the GBA "Sappy"/MP2K format the Hoenn conversion uses, but it is bound to pokeruby: its
ROM_PATH is Sapphire's dump, and it finds the song table and sample names by reading pokeruby's
sound/song_table.inc and sound/direct_sound_data.inc. FireRed shares the exact same M4A engine (pokefirered
sound/ ships voice_groups.inc, MPlayDef.s, keysplit_tables.inc ...), so only those two pokeruby-bound lookups and
the ROM path differ.

This module supplies the FireRed song-table lookup (pokefirered's song_table.inc, 347 entries in the same
`song name, player, player` layout) so we can dump the structure of the songs the Kanto maps play - Pallet Town
(mus_pallet), Route 1 (mus_route1) and the title (mus_title) - directly from roms/firered_rev1_original.gba.

    python3 m4a_frlg.py [SONG ...]        default: mus_pallet mus_route1 mus_title

Scope of this step: song STRUCTURE (header, tracks, notes, loops, voices). The instrument "defaults"/"roles" map
keys on GBA sample *names*, and pokefirered's direct_sound_data.inc drops the `@ address` labels pokeruby kept, so
naming FRLG samples (and re-calibrating the RSE->Black 2 instrument table onto FireRed's samples) is the authoring
work that follows, not done here. Nothing in this module touches the ROM build: it is read-only GBA analysis.
"""
import os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import m4a  # noqa: E402  (the shared M4A engine parsing, reused unchanged)

ROM_PATH = os.path.join(ROOT, 'roms', 'firered_rev1_original.gba')
PFIR = os.path.join(ROOT, 'external', 'pokefirered')
SONG_TABLE_INC = os.path.join(PFIR, 'sound', 'song_table.inc')
DS_INC = os.path.join(PFIR, 'sound', 'direct_sound_data.inc')

# the songs the Kanto prototype's maps and title play (pokefirered data/maps/<map>/map.json "music", lower-cased)
KANTO_SONGS = ['mus_pallet', 'mus_route1', 'mus_title']


class FrlgRom(m4a.GbaRom):
    """m4a.GbaRom pointed at FireRed: same engine, different song table source (pokefirered) and ROM."""

    def __init__(self, path=ROM_PATH):
        if not os.path.exists(path):
            raise SystemExit(f'FireRed dump not found: {path}')
        self.d = open(path, 'rb').read()
        self.sample_names = None                 # FRLG sample naming is the authoring step that follows
        self.song_table = self._find_fr_song_table()

    def _find_fr_song_table(self):
        """gSongTable: 8-byte {header ptr, u16 player, u16 player} entries whose player pattern matches pokefirered's
        sound/song_table.inc (347 songs). Scans the ROM for 40 consecutive entries that agree (m4a's method, FRLG data)."""
        txt = open(SONG_TABLE_INC).read()
        pat = [tuple(map(int, m.groups())) for m in
               re.finditer(r'^\s*song\s+\w+,\s*(\d+),\s*(\d+)', txt, re.M)]
        self.song_names = re.findall(r'^\s*song\s+(\w+),', txt, re.M)
        assert len(pat) == len(self.song_names) == 347, f'expected 347 pokefirered songs, got {len(pat)}/{len(self.song_names)}'
        d = self.d
        for off in range(0, len(d) - 8 * 40, 4):
            if all(struct.unpack_from('<HH', d, off + 8 * i + 4) == pat[i] and
                   0x08000000 <= struct.unpack_from('<I', d, off + 8 * i)[0] < 0x0A000000 for i in range(40)):
                return 0x08000000 + off
        raise SystemExit('FireRed song table not found in the dump')

    def sample_name(self, addr):
        if self.sample_names is None:
            self.sample_names = self._build_sample_names()
        return self.sample_names.get(addr, f'{addr:08X}')

    def _build_sample_names(self):
        """FireRed's sample->address map. pokeruby's direct_sound_data.inc listed each sample with its `@ address`,
        pokefirered's does not (the decomp resolves them at link time), so recover them instead: each
        `DirectSoundWaveData_NAME::` is a `.incbin "sound/direct_sound_samples/NAME.bin"` and that blob sits verbatim
        in the dump, so finding the bytes gives the address. A few unused/identical samples do not appear (or collide);
        those are skipped (voice_key only needs the samples the songs actually play)."""
        names = {}
        for label, rel in re.findall(r'DirectSoundWaveData_(\w+)::\s*\.incbin\s*"([^"]+)"', open(DS_INC).read()):
            p = os.path.join(PFIR, rel.replace('\\', os.sep).replace('/', os.sep))
            if not os.path.exists(p):
                continue
            blob = open(p, 'rb').read()
            if len(blob) < 16:
                continue
            off = self.d.find(blob)                                  # first match is the sample's home
            if off >= 0:
                names.setdefault(0x08000000 + off, label)
        return names


def dump(name, rom=None):
    rom = rom or FrlgRom()
    n = rom.song_index(name)
    h, tracks = m4a.parse_song(rom, n)
    loops = sum(1 for t in tracks if t.loop_tick is not None)
    notes = sum(len([e for e in t.events if e[0] == 'note']) for t in tracks)
    print(f'{name}: table {rom.song_table:08X}, song #{n}, header {h["addr"]:08X}, {h["tracks"]} tracks, '
          f'voicegroup {h["voicegroup"]:08X}, {loops}/{len(tracks)} looping, {notes} notes')
    return h, tracks


def voices(name, rom=None, limit=None):
    """Each voice a song uses, resolved to its GBA instrument name (the map the instrument conversion keys on)."""
    rom = rom or FrlgRom()
    h = rom.header(rom.song_index(name))
    used = sorted({e[2] for t in m4a.parse_song(rom, rom.song_index(name))[1] for e in t.events if e[0] == 'voice'})
    out = []
    for v in used[:limit]:
        desc = rom.describe_voice(h['voicegroup'], v)
        out.append((v, desc))
        print(f'  voice {v:3d}: {desc}')
    return out


def main(argv):
    names = [a for a in argv if not a.endswith('.gba')] or KANTO_SONGS
    rom = FrlgRom()
    print(f'FireRed dump: {os.path.relpath(ROM_PATH, ROOT)} ({len(rom.d):,} B), song table at {rom.song_table:08X}, '
          f'{len(rom.song_names)} songs')
    for name in names:
        if name not in rom.song_names:
            print(f'  {name}: NOT in the FireRed song table'); continue
        dump(name, rom)


if __name__ == '__main__':
    main(sys.argv[1:])
