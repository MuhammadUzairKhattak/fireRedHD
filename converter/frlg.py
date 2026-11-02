"""FireRed/LeafGreen source adapter for the shared Gen 3 map reader.

FRLG uses many of the same tileset symbols as Ruby/Sapphire for different
metatile data.  Namespace those symbols at the adapter boundary so Kanto
classification rules cannot accidentally reuse Hoenn labels.
"""
import argparse
import hashlib
import json
import os
import sys

from gba import Repo


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CONFIG = os.path.join(ROOT, 'data', 'frlg_source.json')


class FrlgRepo(Repo):
    """A Gen 3 repository whose tilesets have FRLG-specific identities."""

    TILESET_PREFIX = 'frlg:'
    # pokefirered include/fieldmap.h: the primary tileset keeps 640 metatiles and 640 tiles (not pokeruby's 512),
    # each metatile attribute is a 32-bit word (fieldmap.c sMetatileAttrMasks) and the palette table gives the
    # primary 7 slots (0..6) with the secondary in 7..12 (NUM_PALS_IN_PRIMARY).
    METATILE_BOUNDARY = 640
    TILE_BOUNDARY = 640
    PAL_PRIMARY = 7
    ATTR_DTYPE = '<u4'

    def __init__(self, root):
        super().__init__(root)
        self.layouts = {
            key: dict(
                layout,
                primary_tileset=self._qualify(layout['primary_tileset']),
                secondary_tileset=self._qualify(layout['secondary_tileset']),
            )
            for key, layout in self.layouts.items()
        }

    @classmethod
    def _qualify(cls, symbol):
        return symbol if symbol.startswith(cls.TILESET_PREFIX) else cls.TILESET_PREFIX + symbol

    def tileset_dir(self, symbol):
        if not symbol.startswith(self.TILESET_PREFIX):
            raise ValueError(f'FRLG tileset is not namespaced: {symbol}')
        name = symbol[len(self.TILESET_PREFIX):]
        try:
            return super().tileset_dir(name)
        except FileNotFoundError:
            # pokefirered splits a trailing digit run into its own folder segment (gTileset_SeviiIslands45 ->
            # sevii_islands_45), which gba.Repo.tileset_dir's capital-only split misses; retry with that rule so the
            # shared Hoenn reader stays untouched (this is the Kanto adapter's own naming difference).
            import re
            alt = re.sub(r'(?<=[a-zA-Z])(?=\d)', '_', re.sub(r'(?<!^)(?=[A-Z])', '_', name.replace('gTileset_', ''))).lower()
            for kind in ('primary', 'secondary'):
                p = f'{self.root}/data/tilesets/{kind}/{alt}'
                if os.path.isdir(p):
                    return p
            raise


def load_config(path=CONFIG):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def sha1(path):
    digest = hashlib.sha1()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def validate_source(repo_root, rom_path=None, config=None):
    """Validate the configured decomp revision inputs and prototype maps."""
    config = config or load_config()
    repo = FrlgRepo(repo_root)
    result = {'profile': config['profile'], 'maps': {}}
    if rom_path:
        actual = sha1(rom_path)
        expected = config['rom']['sha1']
        if actual != expected:
            raise ValueError(f'wrong {config["profile"]} ROM: expected SHA1 {expected}, got {actual}')
        result['rom_sha1'] = actual
    for name in config['prototype_maps']:
        source = repo.map_json(name)
        grid, layout = repo.layout_grid(source['layout'])
        result['maps'][name] = {
            'id': source['id'],
            'layout': source['layout'],
            'size': [int(grid.shape[1]), int(grid.shape[0])],
            'tilesets': [layout['primary_tileset'], layout['secondary_tileset']],
            'objects': len(source.get('object_events') or []),
            'warps': len(source.get('warp_events') or []),
            'connections': len(source.get('connections') or []),
        }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Validate and inventory an FRLG source checkout')
    parser.add_argument('repo', help='path to the pokefirered checkout')
    parser.add_argument('--rom', help='optional original ROM to verify against the configured SHA1')
    parser.add_argument('--output', help='optional JSON inventory output')
    args = parser.parse_args(argv)
    result = validate_source(os.path.abspath(args.repo), os.path.abspath(args.rom) if args.rom else None)
    encoded = json.dumps(result, indent=1)
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(encoded + '\n')
    print(encoded)


if __name__ == '__main__':
    try:
        main()
    except (FileNotFoundError, KeyError, ValueError) as error:
        print(f'error: {error}', file=sys.stderr)
        raise SystemExit(1)
